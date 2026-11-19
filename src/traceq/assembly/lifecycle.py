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

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    RowMapping,
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import insert
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

_META = MetaData()
PROTOCOLS = Table(
    "assembled_protocols",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("equipment", Text),
    Column("run_id", Text),
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
)


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
class AssembledProtocol:
    id: int
    equipment: str
    run_id: str
    events: tuple[Event, ...]
    """Oldest first; never empty."""

    @property
    def status(self) -> Status:
        return self.events[-1].status


def _event(m: RowMapping) -> Event:
    return Event(
        id=m["id"],
        at=m["at"],
        event=cast(EventKind, m["event"]),
        reason=m["reason"],
        actor=audit.Actor(subject=m["subject"], issuer=m["issuer"], name=m["name"]),
    )


def _lock(session: Session, namespace: int, key: str) -> None:
    session.execute(select(func.pg_advisory_xact_lock(namespace, func.hashtext(key))))


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
            select(PROTOCOLS.c.id, PROTOCOLS.c.equipment, PROTOCOLS.c.run_id).where(
                PROTOCOLS.c.id.in_(ids)
            )
        )
    }
    return [
        AssembledProtocol(
            id=i,
            equipment=found[i].equipment,
            run_id=found[i].run_id,
            events=tuple(events[i]),
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


def _of_equipment(session: Session, equipment: str) -> list[AssembledProtocol]:
    ids = session.execute(
        select(PROTOCOLS.c.id).where(PROTOCOLS.c.equipment == equipment).order_by(PROTOCOLS.c.id)
    ).scalars()
    return _load(session, list(ids))


def _append(
    session: Session, actor: audit.Actor, protocol_id: int, event: EventKind, reason: str | None
) -> Event:
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
            )
            .returning(*EVENTS.c)
        )
        .mappings()
        .one()
    )


def start(session: Session, actor: audit.Actor, run_id: str, *, drafted: bool) -> AssembledProtocol:
    """Starts the Protocol of the run's Equipment from the run, in Draft status.

    ``drafted``: the run folder holds ``drafts.json``. Such a run imported before drafted Test
    Steps became Proposals holds none, and is refused rather than shown without its drafts."""
    equipment = session.execute(
        select(RUNS.c.equipment).where(RUNS.c.run_id == run_id)
    ).scalar_one_or_none()
    if equipment is None:
        raise NotFound(f"run {run_id} is not imported")
    _lock(session, _EQUIPMENT_LOCK, equipment)
    for p in _of_equipment(session, equipment):
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
    protocol_id: int = session.execute(
        insert(PROTOCOLS).values(equipment=equipment, run_id=run_id).returning(PROTOCOLS.c.id)
    ).scalar_one()
    started = _append(session, actor, protocol_id, "started", None)
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
        },
    )
    return AssembledProtocol(protocol_id, equipment, run_id, (started,))


def withdraw(
    session: Session, actor: audit.Actor, protocol_id: int, reason: str
) -> AssembledProtocol:
    """Gives up a Protocol in Draft status, with a reason, so a newer run can get one."""
    reason = reason.strip()
    if not reason:
        raise Refused("withdrawing a Protocol needs a reason")
    _lock(session, _PROTOCOL_LOCK, str(protocol_id))
    current = get(session, protocol_id)
    if current is None:
        raise NotFound(f"no Protocol {protocol_id}")
    if current.status != "draft":
        raise Conflict(
            f"Protocol {protocol_id} is {current.status}: only a Protocol in Draft status can"
            " be withdrawn"
        )
    done = _append(session, actor, protocol_id, "withdrawn", reason)
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
    return AssembledProtocol(current.id, current.equipment, current.run_id, (*current.events, done))
