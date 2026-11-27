"""Starting and withdrawing a Protocol, and its status (spec #247, "The Protocol and its rows",
"Concurrency"; ADR 0012 "Statuses").

A Protocol belongs to one Equipment and is started from one imported run. Its status changes
are appended events, the current status the latest. One Protocol per Equipment may be open
(Draft or Submitted) at a time and none may be started once one is Approved, checked under a
per-Equipment lock in the start transaction; a status change takes a per-Protocol lock and
checks the status again inside it. Every event has its Audit Trail entry in the same
transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    RowMapping,
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.proposals.store import PROPOSALS, RUN_PROPOSALS, RUNS

type Status = Literal["draft", "submitted", "approved", "withdrawn"]
type EventKind = Literal["started", "submitted", "approved", "returned", "withdrawn"]

STATUS_AFTER: dict[EventKind, Status] = {
    "started": "draft",
    "submitted": "submitted",
    "approved": "approved",
    "returned": "draft",
    "withdrawn": "withdrawn",
}
OPEN: frozenset[Status] = frozenset({"draft", "submitted"})

# Advisory lock namespaces (the two-key form, apart from the one-key locks on Proposals).
_EQUIPMENT_LOCK = 1
_PROTOCOL_LOCK = 2
_REQUIREMENT_LOCK = 3

_META = MetaData()
PROTOCOLS = Table(
    "assembled_protocols",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("equipment", Text),
    Column("run_id", Text),
    Column("draft_doc", Text),
    Column("draft_rev", Integer),
    Column("draft_sha256", Text),
)
EVENTS = Table(
    "protocol_events",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("protocol_id", BigInteger),
    Column("event", Text),
    Column("reason", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
    Column("frozen_copy", JSONB(none_as_null=True)),
    Column("copy_hash", Text),
)
"""A ``submitted`` event also holds the frozen copy and its hash (``assembly.submission``)."""


class NotFound(Exception):
    """The run is not imported, or the Protocol does not exist."""


class Conflict(Exception):
    """The state change is refused in this state; the message says why in words."""


class Refused(Exception):
    """The request lacks what it needs (a reason)."""


@dataclass(frozen=True)
class Event:
    id: int
    at: datetime
    event: EventKind
    reason: str | None
    actor: audit.Actor

    @property
    def status(self) -> Status:
        """The status the Protocol has after this event."""
        return STATUS_AFTER[self.event]


@dataclass(frozen=True)
class DraftPin:
    """The Protocol Draft a Protocol was started from: its document, revision and hash. With
    the Protocol's run it is where the Protocol is pinned; it never re-syncs (ADR 0012)."""

    doc: str
    rev: int
    sha256: str


@dataclass(frozen=True)
class AssembledProtocol:
    id: int
    equipment: str
    run_id: str
    events: tuple[Event, ...]
    """Oldest first; never empty."""
    draft: DraftPin | None = None
    """For a Protocol started from the site's Protocol Draft: what it is pinned to; ``None``
    for one assembled from TraceQ's own drafted Test Steps."""

    @property
    def status(self) -> Status:
        return self.events[-1].status

    def after(self, event: Event) -> AssembledProtocol:
        """The Protocol once ``event`` is appended to it."""
        return replace(self, events=(*self.events, event))


def _event(m: RowMapping) -> Event:
    return Event(
        id=m["id"],
        at=m["at"],
        event=cast(EventKind, m["event"]),
        reason=m["reason"],
        actor=audit.actor_of_row(m),
    )


def _lock(session: Session, namespace: int, key: str) -> None:
    session.execute(select(func.pg_advisory_xact_lock(namespace, func.hashtext(key))))


def lock_protocol(session: Session, protocol_id: int) -> None:
    """Serialises every write and status change on one Protocol: take it, then check the
    status again inside the transaction."""
    _lock(session, _PROTOCOL_LOCK, str(protocol_id))


def lock_requirement(session: Session, equipment: str, requirement: str) -> None:
    """Serialises accepting a drafted Test Step and writing one for the same requirement of an
    Equipment, so a row never holds two Test Steps."""
    _lock(session, _REQUIREMENT_LOCK, f"{equipment}/{requirement}")


def _load(session: Session, ids: list[int]) -> list[AssembledProtocol]:
    """The Protocols of ``ids``, in that order, with their events."""
    if not ids:
        return []
    events: dict[int, list[Event]] = {}
    for m in session.execute(
        select(EVENTS).where(EVENTS.c.protocol_id.in_(ids)).order_by(EVENTS.c.id)
    ).mappings():
        events.setdefault(m["protocol_id"], []).append(_event(m))
    found = {
        r.id: r
        for r in session.execute(
            select(
                PROTOCOLS.c.id,
                PROTOCOLS.c.equipment,
                PROTOCOLS.c.run_id,
                PROTOCOLS.c.draft_doc,
                PROTOCOLS.c.draft_rev,
                PROTOCOLS.c.draft_sha256,
            ).where(PROTOCOLS.c.id.in_(ids))
        )
    }
    return [
        AssembledProtocol(
            id=i,
            equipment=found[i].equipment,
            run_id=found[i].run_id,
            events=tuple(events[i]),
            draft=None
            if found[i].draft_doc is None
            else DraftPin(found[i].draft_doc, found[i].draft_rev, found[i].draft_sha256),
        )
        for i in ids
        if i in found
    ]


def get(session: Session, protocol_id: int) -> AssembledProtocol | None:
    got = _load(session, [protocol_id])
    return got[0] if got else None


def latest_of_run(session: Session, run_id: str) -> AssembledProtocol | None:
    """The Protocol most recently started from the run, whatever its status."""
    latest = session.execute(
        select(func.max(PROTOCOLS.c.id)).where(PROTOCOLS.c.run_id == run_id)
    ).scalar_one()
    return None if latest is None else get(session, latest)


def locked(session: Session, protocol_id: int, status: Status, refused: str) -> AssembledProtocol:
    """The Protocol under its per-Protocol lock, its status read inside it: ``NotFound`` when
    there is none, ``Conflict`` unless it is in ``status`` (``refused`` says what is refused)."""
    lock_protocol(session, protocol_id)
    found = get(session, protocol_id)
    if found is None:
        raise NotFound(f"no Protocol {protocol_id}")
    if found.status != status:
        raise Conflict(f"Protocol {protocol_id} is {found.status}: {refused}")
    return found


def of_equipment(session: Session, equipment: str) -> list[AssembledProtocol]:
    """Every Protocol of the Equipment, oldest first."""
    ids = session.execute(
        select(PROTOCOLS.c.id).where(PROTOCOLS.c.equipment == equipment).order_by(PROTOCOLS.c.id)
    ).scalars()
    return _load(session, list(ids))


def append(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    event: EventKind,
    reason: str | None,
    *,
    frozen_copy: dict[str, Any] | None = None,
    copy_hash: str | None = None,
) -> Event:
    """Adds a status event; the caller holds the per-Protocol lock and writes the Audit Trail
    entry. ``frozen_copy`` and ``copy_hash``: for ``submitted`` only."""
    return _event(
        session.execute(
            insert(EVENTS)
            .values(
                protocol_id=protocol_id,
                event=event,
                reason=reason,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
                frozen_copy=frozen_copy,
                copy_hash=copy_hash,
            )
            .returning(*EVENTS.c)
        )
        .mappings()
        .one()
    )


def draft_pin_of_run(session: Session, run_id: str) -> DraftPin | None:
    """The Protocol Draft a Review Package run read, from its draft Test Step Proposals;
    ``None`` for a run that holds none."""
    proposed = session.execute(
        select(RUN_PROPOSALS.c.proposed)
        .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
        .where(RUN_PROPOSALS.c.run_id == run_id, PROPOSALS.c.kind == "draft_step")
        .order_by(RUN_PROPOSALS.c.seq)
        .limit(1)
    ).scalar_one_or_none()
    if proposed is None:
        return None
    doc = proposed["document"]
    return DraftPin(str(doc["doc_id"]), int(doc["rev"]), str(doc["sha256"]))


def start(
    session: Session,
    actor: audit.Actor,
    run_id: str,
    *,
    drafted: bool,
    from_draft: bool = False,
) -> AssembledProtocol:
    """Starts the Protocol of the run's Equipment from the run, in Draft status.

    ``drafted``: the run folder holds ``drafts.json``. Such a run imported before drafted Test
    Steps became Proposals holds none, and is refused rather than shown without its drafts.
    ``from_draft``: start from the site's Protocol Draft the run read (ADR 0012, amended 26
    November 2026): the Protocol is pinned to the run, the draft's document, revision and hash,
    and never re-synced; refused for a run that read no draft."""
    equipment = session.execute(
        select(RUNS.c.equipment).where(RUNS.c.run_id == run_id)
    ).scalar_one_or_none()
    if equipment is None:
        raise NotFound(f"run {run_id} is not imported")
    _lock(session, _EQUIPMENT_LOCK, equipment)
    for p in of_equipment(session, equipment):
        if p.status == "approved":
            raise Conflict(
                f"Protocol {p.id} of {equipment} is approved: a new version of an approved"
                " Protocol is step 6, not yet built"
            )
        if p.status in OPEN:
            raise Conflict(
                f"Protocol {p.id} of {equipment} is open ({p.status} status, started from run"
                f" {p.run_id}): one Protocol per Equipment may be open; withdraw it first"
            )
    if drafted:
        held = session.execute(
            select(func.count())
            .select_from(RUN_PROPOSALS)
            .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
            .where(RUN_PROPOSALS.c.run_id == run_id, PROPOSALS.c.kind == "test_step")
        ).scalar_one()
        if held == 0:
            raise Conflict(
                f"run {run_id} has a drafts.json but holds no drafted Test Step Proposals: it"
                " was imported before drafts were imported; import a new run of the Equipment"
            )
    pin: DraftPin | None = None
    if from_draft:
        pin = draft_pin_of_run(session, run_id)
        if pin is None:
            raise Conflict(
                f"run {run_id} read no Protocol Draft (or was imported before draft Test Steps"
                " became Proposals): a Protocol cannot start from the draft"
            )
    protocol_id: int = session.execute(
        insert(PROTOCOLS)
        .values(
            equipment=equipment,
            run_id=run_id,
            draft_doc=None if pin is None else pin.doc,
            draft_rev=None if pin is None else pin.rev,
            draft_sha256=None if pin is None else pin.sha256,
        )
        .returning(PROTOCOLS.c.id)
    ).scalar_one()
    started = append(session, actor, protocol_id, "started", None)
    audit.append(
        session,
        actor,
        "protocol started",
        "protocol",
        str(protocol_id),
        new={
            "protocol_id": protocol_id,
            "equipment": equipment,
            "run_id": run_id,
            "event_id": started.id,
            "status": started.status,
            **(
                {}
                if pin is None
                else {"draft": {"doc": pin.doc, "rev": pin.rev, "sha256": pin.sha256}}
            ),
        },
    )
    return AssembledProtocol(protocol_id, equipment, run_id, (started,), pin)


def withdraw(
    session: Session, actor: audit.Actor, protocol_id: int, reason: str
) -> AssembledProtocol:
    """Gives up a Protocol in Draft status, with a reason, so a newer run can get one."""
    reason = reason.strip()
    if not reason:
        raise Refused("withdrawing a Protocol needs a reason")
    current = locked(
        session, protocol_id, "draft", "only a Protocol in Draft status can be withdrawn"
    )
    done = append(session, actor, protocol_id, "withdrawn", reason)
    audit.append(
        session,
        actor,
        "protocol withdrawn",
        "protocol",
        str(protocol_id),
        old={"status": current.status},
        new={"status": done.status, "event_id": done.id},
        reason=reason,
    )
    return current.after(done)
