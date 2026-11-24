"""Starting an Execution of an Approved Protocol, and its status (ADR 0013, spec #270, #271).

One Execution per Approved Protocol, started under the per-Protocol advisory lock and bound to
the Approved Protocol's ``submitted`` event id and frozen-copy hash. Later writes take a
per-Execution advisory lock in namespace 4 (beside the 3 namespaces of ``traceq.assembly``)
and re-check status inside it. Every event has its Audit Trail entry in the same transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import BigInteger, Column, DateTime, MetaData, RowMapping, Table, Text, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle as assembly_lifecycle
from traceq.assembly import submission

type Status = Literal["in_progress", "completed"]
type EventKind = Literal["started", "completed"]

STATUS_AFTER: dict[EventKind, Status] = {
    "started": "in_progress",
    "completed": "completed",
}

# Advisory lock namespace 4, beside namespaces 1..3 in traceq.assembly.lifecycle.
_EXECUTION_LOCK = 4

_META = MetaData()
EXECUTIONS = Table(
    "protocol_executions",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("protocol_id", BigInteger),
    Column("submission_event_id", BigInteger),
    Column("submission_hash", Text),
)
EVENTS = Table(
    "execution_events",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("execution_id", BigInteger),
    Column("event", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)


class NotFound(Exception):
    """The Protocol or Execution does not exist."""


class Conflict(Exception):
    """The state change is refused in this state; the message says why in words."""


@dataclass(frozen=True)
class Event:
    """A status change of an Execution: what, who and when."""

    id: int
    at: datetime
    event: EventKind
    actor: audit.Actor

    @property
    def status(self) -> Status:
        """The status the Execution has after this event."""
        return STATUS_AFTER[self.event]


@dataclass(frozen=True)
class Execution:
    """One Execution of an Approved Protocol, bound to its frozen submission."""

    id: int
    protocol_id: int
    submission_event_id: int
    submission_hash: str
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
        actor=audit.actor_of_row(m),
    )


def lock_execution(session: Session, execution_id: int) -> None:
    """Serialises every write and status change on one Execution (namespace 4)."""
    session.execute(
        select(func.pg_advisory_xact_lock(_EXECUTION_LOCK, func.hashtext(str(execution_id))))
    )


def get(session: Session, execution_id: int) -> Execution | None:
    """The Execution by id, or ``None``."""
    row = session.execute(
        select(
            EXECUTIONS.c.id,
            EXECUTIONS.c.protocol_id,
            EXECUTIONS.c.submission_event_id,
            EXECUTIONS.c.submission_hash,
        ).where(EXECUTIONS.c.id == execution_id)
    ).one_or_none()
    if row is None:
        return None
    events = tuple(
        _event(m)
        for m in session.execute(
            select(EVENTS).where(EVENTS.c.execution_id == execution_id).order_by(EVENTS.c.id)
        ).mappings()
    )
    return Execution(
        id=row.id,
        protocol_id=row.protocol_id,
        submission_event_id=row.submission_event_id,
        submission_hash=row.submission_hash,
        events=events,
    )


def of_protocol(session: Session, protocol_id: int) -> Execution | None:
    """The Execution of ``protocol_id``, or ``None`` if not started."""
    eid = session.execute(
        select(EXECUTIONS.c.id).where(EXECUTIONS.c.protocol_id == protocol_id)
    ).scalar_one_or_none()
    return None if eid is None else get(session, eid)


def start(session: Session, actor: audit.Actor, protocol_id: int) -> Execution:
    """Starts the Execution of an Approved Protocol in ``in_progress`` status, under the
    per-Protocol advisory lock, with an Audit Trail entry in the same transaction."""
    assembly_lifecycle.lock_protocol(session, protocol_id)
    protocol = assembly_lifecycle.get(session, protocol_id)
    if protocol is None:
        raise NotFound(f"no Protocol {protocol_id}")
    if protocol.status != "approved":
        raise Conflict(
            f"Protocol {protocol_id} is {protocol.status}: only an Approved Protocol can be"
            " executed"
        )
    existing = of_protocol(session, protocol_id)
    if existing is not None:
        raise Conflict(
            f"Protocol {protocol_id} already has Execution {existing.id}: one Execution per"
            " Protocol"
        )
    submissions = submission.submissions_of(session, protocol_id)
    if not submissions:
        raise Conflict(f"Protocol {protocol_id} has no frozen submission")
    sub = submissions[-1]
    execution_id: int = session.execute(
        insert(EXECUTIONS)
        .values(
            protocol_id=protocol_id,
            submission_event_id=sub.event_id,
            submission_hash=sub.hash,
        )
        .returning(EXECUTIONS.c.id)
    ).scalar_one()
    started = _event(
        session.execute(
            insert(EVENTS)
            .values(
                execution_id=execution_id,
                event="started",
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*EVENTS.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "execution started",
        "execution",
        str(execution_id),
        new={
            "execution_id": execution_id,
            "protocol_id": protocol_id,
            "submission_event_id": sub.event_id,
            "submission_hash": sub.hash,
            "event_id": started.id,
            "status": started.status,
        },
    )
    return Execution(
        id=execution_id,
        protocol_id=protocol_id,
        submission_event_id=sub.event_id,
        submission_hash=sub.hash,
        events=(started,),
    )
