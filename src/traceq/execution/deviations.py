"""Deviation lifecycle: manual Deviations, Investigation versions, submit, close, and return
(ADR 0013, spec #270, #273).

Every write takes the per-Execution advisory lock (namespace 4) and re-checks Execution and
Deviation status inside the transaction.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.execution import lifecycle, results
from traceq.execution.results import (
    ATTEMPT_VERSIONS,
    ATTEMPTS,
    DEVIATION_EVENTS,
    DEVIATION_INVESTIGATIONS,
    DEVIATIONS,
    Deviation,
    DeviationClass,
    DeviationEvent,
    DeviationInvestigation,
    InvalidResult,
)

CLOSURE_NOTE = "a recorded status, not an Electronic Signature"


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OpenManualDeviationRequest(_Input):
    """Payload to open a manual Deviation linked to a Test Step row or to the Execution."""

    requirement: str | None = None
    description: str

    @field_validator("description")
    @classmethod
    def _non_blank_description(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("description must not be blank")
        return stripped


class InvestigationRequest(_Input):
    """Payload to record an immutable version of a Deviation's Investigation."""

    investigation: str
    deviation_class: DeviationClass
    capa: str | None = None
    reason_for_change: str | None = None

    @field_validator("investigation")
    @classmethod
    def _non_blank_investigation(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("investigation must not be blank")
        return stripped


class ReturnDeviationRequest(_Input):
    """Payload to return a Submitted Deviation to Open with a required reason."""

    reason: str

    @field_validator("reason")
    @classmethod
    def _non_blank_reason(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("reason must not be blank")
        return stripped


def _require_in_progress_execution(session: Session, execution_id: int) -> lifecycle.Execution:
    lifecycle.lock_execution(session, execution_id)
    ex = lifecycle.get(session, execution_id)
    if ex is None:
        raise lifecycle.NotFound(f"no Execution {execution_id}")
    if ex.status != "in_progress":
        raise lifecycle.Conflict(
            f"Execution {execution_id} is {ex.status}: Deviations can only be changed while"
            " In progress"
        )
    return ex


def _require_deviation(session: Session, execution_id: int, deviation_id: int) -> Deviation:
    for dev in results.deviations_of(session, execution_id):
        if dev.id == deviation_id:
            return dev
    raise lifecycle.NotFound(f"no Deviation {deviation_id} in Execution {execution_id}")


def open_manual_deviation(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    req: OpenManualDeviationRequest,
) -> Deviation:
    """Opens a manual Deviation on an ``in_progress`` Execution, linked to one Test Step row
    (refusing Vendor Reference rows) or to the Execution (``requirement=None``)."""
    ex = _require_in_progress_execution(session, execution_id)
    req_str = req.requirement.strip() if req.requirement is not None else None
    if req_str == "":
        req_str = None

    if req_str is not None:
        copy = results.frozen_copy(session, ex)
        row = next((r for r in copy.rows if r.requirement == req_str), None)
        if row is None:
            raise lifecycle.NotFound(f"no row {req_str} in Execution {execution_id}")
        if row.kind != "test_step":
            raise lifecycle.Conflict(f"row {req_str} is a Vendor Reference, not a Test Step")

    max_num: int = session.execute(
        select(func.coalesce(func.max(DEVIATIONS.c.deviation_number), 0)).where(
            DEVIATIONS.c.execution_id == execution_id
        )
    ).scalar_one()
    next_num = max_num + 1

    dev_row = (
        session.execute(
            insert(DEVIATIONS)
            .values(
                execution_id=execution_id,
                deviation_number=next_num,
                requirement=req_str,
                attempt_id=None,
                cause="manual",
                description=req.description,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DEVIATIONS.c)
        )
        .mappings()
        .one()
    )
    ev_row = (
        session.execute(
            insert(DEVIATION_EVENTS)
            .values(
                deviation_id=dev_row["id"],
                event="opened",
                reason=None,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DEVIATION_EVENTS.c)
        )
        .mappings()
        .one()
    )
    ev = results.deviation_event_from_row(ev_row)
    dev = Deviation(
        id=dev_row["id"],
        at=dev_row["at"],
        execution_id=execution_id,
        deviation_number=next_num,
        requirement=req_str,
        attempt_id=None,
        cause="manual",
        description=req.description,
        actor=audit.actor_of_row(dev_row),
        events=(ev,),
        investigations=(),
    )
    audit.append(
        session,
        actor,
        "deviation opened",
        "execution_deviation",
        f"{execution_id}/{next_num}",
        new={
            "execution_id": execution_id,
            "deviation_id": dev.id,
            "deviation_number": next_num,
            "requirement": req_str,
            "cause": "manual",
            "status": dev.status,
        },
    )
    return dev


def add_investigation(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    deviation_id: int,
    req: InvestigationRequest,
) -> DeviationInvestigation:
    """Adds an immutable Investigation version to an ``open`` Deviation."""
    _require_in_progress_execution(session, execution_id)
    dev = _require_deviation(session, execution_id, deviation_id)
    if dev.status != "open":
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} is {dev.status}: Investigation can only be written"
            " while Open"
        )

    version = len(dev.investigations) + 1
    reason = req.reason_for_change.strip() if req.reason_for_change is not None else None
    if reason == "":
        reason = None
    if version >= 2 and reason is None:
        raise InvalidResult("reason_for_change is required from Investigation version 2 onwards")

    capa = req.capa.strip() if req.capa is not None else None
    if capa == "":
        capa = None

    inv_row = (
        session.execute(
            insert(DEVIATION_INVESTIGATIONS)
            .values(
                deviation_id=deviation_id,
                version=version,
                investigation=req.investigation,
                deviation_class=req.deviation_class,
                capa=capa,
                reason_for_change=reason,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DEVIATION_INVESTIGATIONS.c)
        )
        .mappings()
        .one()
    )
    inv = results.deviation_investigation_from_row(inv_row)
    audit.append(
        session,
        actor,
        "deviation investigation recorded",
        "execution_deviation",
        f"{execution_id}/{dev.deviation_number}",
        new={
            "execution_id": execution_id,
            "deviation_id": deviation_id,
            "deviation_number": dev.deviation_number,
            "investigation_id": inv.id,
            "version": version,
            "deviation_class": inv.deviation_class,
            "reason_for_change": reason,
        },
    )
    return inv


def submit_deviation(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    deviation_id: int,
) -> DeviationEvent:
    """Submits an ``open`` Deviation once an Investigation with a class is recorded."""
    _require_in_progress_execution(session, execution_id)
    dev = _require_deviation(session, execution_id, deviation_id)
    if dev.status != "open":
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} is {dev.status}: only an Open Deviation can be"
            " submitted"
        )
    if not dev.investigations or dev.deviation_class is None:
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} requires an Investigation with a class before"
            " submission"
        )

    ev_row = (
        session.execute(
            insert(DEVIATION_EVENTS)
            .values(
                deviation_id=deviation_id,
                event="submitted",
                reason=None,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DEVIATION_EVENTS.c)
        )
        .mappings()
        .one()
    )
    ev = results.deviation_event_from_row(ev_row)
    audit.append(
        session,
        actor,
        "deviation submitted",
        "execution_deviation",
        f"{execution_id}/{dev.deviation_number}",
        new={
            "execution_id": execution_id,
            "deviation_id": deviation_id,
            "deviation_number": dev.deviation_number,
            "event_id": ev.id,
            "status": ev.status,
            "deviation_class": dev.deviation_class,
        },
    )
    return ev


def _check_close_sod(session: Session, actor: audit.Actor, dev: Deviation) -> None:
    """4-way Separation of Duties (ADR 0013): closer must not be an Investigation author,
    the Performer of any attempt at the linked Test Step, or the opener of a manual Deviation."""
    closer = (actor.subject, actor.issuer)

    if any((inv.actor.subject, inv.actor.issuer) == closer for inv in dev.investigations):
        raise lifecycle.Conflict(
            "Separation of Duties: an author of this Deviation's Investigation cannot close it"
        )

    if dev.cause == "manual" and (dev.actor.subject, dev.actor.issuer) == closer:
        raise lifecycle.Conflict(
            "Separation of Duties: the opener of this manual Deviation cannot close it"
        )

    if dev.requirement is not None:
        attempt_performers = {
            (r["subject"], r["issuer"])
            for r in session.execute(
                select(ATTEMPTS.c.subject, ATTEMPTS.c.issuer).where(
                    ATTEMPTS.c.execution_id == dev.execution_id,
                    ATTEMPTS.c.requirement == dev.requirement,
                )
            ).mappings()
        }
        version_performers = {
            (r["subject"], r["issuer"])
            for r in session.execute(
                select(ATTEMPT_VERSIONS.c.subject, ATTEMPT_VERSIONS.c.issuer)
                .select_from(
                    ATTEMPT_VERSIONS.join(ATTEMPTS, ATTEMPT_VERSIONS.c.attempt_id == ATTEMPTS.c.id)
                )
                .where(
                    ATTEMPTS.c.execution_id == dev.execution_id,
                    ATTEMPTS.c.requirement == dev.requirement,
                )
            ).mappings()
        }
        if closer in (attempt_performers | version_performers):
            raise lifecycle.Conflict(
                f"Separation of Duties: the Performer of an attempt on {dev.requirement} cannot"
                " close its Deviation"
            )


def close_deviation(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    deviation_id: int,
) -> DeviationEvent:
    """Closes a ``submitted`` Deviation (recorded status, not an Electronic Signature) after
    enforcing 4-way Separation of Duties."""
    _require_in_progress_execution(session, execution_id)
    dev = _require_deviation(session, execution_id, deviation_id)
    if dev.status != "submitted":
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} is {dev.status}: only a Submitted Deviation can be"
            " closed"
        )
    _check_close_sod(session, actor, dev)

    ev_row = (
        session.execute(
            insert(DEVIATION_EVENTS)
            .values(
                deviation_id=deviation_id,
                event="closed",
                reason=None,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DEVIATION_EVENTS.c)
        )
        .mappings()
        .one()
    )
    ev = results.deviation_event_from_row(ev_row)
    audit.append(
        session,
        actor,
        "deviation closed",
        "execution_deviation",
        f"{execution_id}/{dev.deviation_number}",
        new={
            "execution_id": execution_id,
            "deviation_id": deviation_id,
            "deviation_number": dev.deviation_number,
            "event_id": ev.id,
            "status": ev.status,
            "note": CLOSURE_NOTE,
        },
    )
    return ev


def return_deviation(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    deviation_id: int,
    req: ReturnDeviationRequest,
) -> DeviationEvent:
    """Returns a ``submitted`` Deviation to ``open`` with a required reason."""
    _require_in_progress_execution(session, execution_id)
    dev = _require_deviation(session, execution_id, deviation_id)
    if dev.status != "submitted":
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} is {dev.status}: only a Submitted Deviation can be"
            " returned to Open"
        )

    ev_row = (
        session.execute(
            insert(DEVIATION_EVENTS)
            .values(
                deviation_id=deviation_id,
                event="returned",
                reason=req.reason,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DEVIATION_EVENTS.c)
        )
        .mappings()
        .one()
    )
    ev = results.deviation_event_from_row(ev_row)
    audit.append(
        session,
        actor,
        "deviation returned",
        "execution_deviation",
        f"{execution_id}/{dev.deviation_number}",
        new={
            "execution_id": execution_id,
            "deviation_id": deviation_id,
            "deviation_number": dev.deviation_number,
            "event_id": ev.id,
            "status": ev.status,
            "reason": req.reason,
        },
    )
    return ev
