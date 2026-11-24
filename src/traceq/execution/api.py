"""The routes of Protocol Execution (ADR 0013, spec #270, #271): start an Execution of an
Approved Protocol, and read an Execution with its rows from the Protocol's frozen copy.

Every route needs a valid bearer token; starting needs ``qualification-executor``;
reading is open to any signed-in role. Errors: 401 without a token, 403 without the role, 404
unknown, 409 for a refused state change with the reason in words.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from traceq.assembly import lifecycle as assembly_lifecycle
from traceq.assembly import submission
from traceq.assembly.submission import FrozenRow, ProtocolCopy
from traceq.assembly.written import Acceptance
from traceq.db import transaction
from traceq.execution import lifecycle
from traceq.execution.lifecycle import EventKind, Status
from traceq.identity import Principal
from traceq.proposals.api import actor_of
from traceq.runs.schemas import Cite, EvidenceStep


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionEvent(_Model):
    """A status change of an Execution: what, who and when."""

    id: int
    event: EventKind
    status: Status
    subject: str
    issuer: str
    name: str
    at: datetime


class ExecutionTestStep(_Model):
    """The Test Step of a Test Step row, from the Approved Protocol's frozen copy."""

    origin: Literal["accepted_draft", "written"]
    description: str
    method: str
    instrument: str | None
    acceptance: Acceptance


class ExecutionRowView(_Model):
    """One row of the Execution, in the order of the Approved Protocol's frozen copy."""

    requirement: str
    text: str
    source: Cite
    kind: Literal["vendor_reference", "test_step"]
    evidence: tuple[EvidenceStep, ...]
    """For a Vendor Reference row: the vendor's Evidence steps."""
    test_step: ExecutionTestStep | None
    """For a Test Step row: its Test Step from the frozen copy."""


class ExecutionView(_Model):
    """An Execution of an Approved Protocol: its status, events, and rows from the frozen copy."""

    id: int
    protocol_id: int
    equipment: str
    run_id: str
    submission_event_id: int
    submission_hash: str
    status: Status
    events: list[ExecutionEvent]
    rows: list[ExecutionRowView]


def _event(e: lifecycle.Event) -> ExecutionEvent:
    return ExecutionEvent(
        id=e.id,
        event=e.event,
        status=e.status,
        subject=e.actor.subject,
        issuer=e.actor.issuer,
        name=e.actor.name,
        at=e.at,
    )


def _row(r: FrozenRow) -> ExecutionRowView:
    step = r.test_step
    return ExecutionRowView(
        requirement=r.requirement,
        text=r.text,
        source=r.source,
        kind=r.kind,
        evidence=r.evidence,
        test_step=None
        if step is None
        else ExecutionTestStep(
            origin=step.origin,
            description=step.description,
            method=step.method,
            instrument=step.instrument,
            acceptance=step.acceptance,
        ),
    )


def _frozen_copy(session: Session, ex: lifecycle.Execution) -> ProtocolCopy:
    for sub in submission.submissions_of(session, ex.protocol_id):
        if sub.event_id == ex.submission_event_id:
            return sub.copy
    raise lifecycle.NotFound(
        f"submission {ex.submission_event_id} of Protocol {ex.protocol_id} not found"
    )


def create_router(db: Engine | None, principal: Callable[..., Principal]) -> APIRouter:
    """``db``: the database as the application role; none with default settings, when
    ``principal`` refuses every request."""
    router = APIRouter()

    def database() -> Engine:
        if db is None:  # unreachable: without a database no token is accepted
            raise HTTPException(401, "no database is configured")
        return db

    def view(session: Session, ex: lifecycle.Execution) -> ExecutionView:
        copy = _frozen_copy(session, ex)
        return ExecutionView(
            id=ex.id,
            protocol_id=ex.protocol_id,
            equipment=copy.equipment,
            run_id=copy.run_id,
            submission_event_id=ex.submission_event_id,
            submission_hash=ex.submission_hash,
            status=ex.status,
            events=[_event(e) for e in ex.events],
            rows=[_row(r) for r in copy.rows],
        )

    @router.post(
        "/protocols/{protocol_id}/execution",
        operation_id="startExecution",
        status_code=201,
    )
    def start_execution(
        protocol_id: int, who: Annotated[Principal, Depends(principal)]
    ) -> ExecutionView:
        """Starts the Execution of an Approved Protocol in ``in_progress`` status, with its Audit
        Trail entry. Refused (409) unless the Protocol is Approved, and for a second Execution
        of the same Protocol. Needs the executing role."""
        if not who.may_execute:
            raise HTTPException(403, "starting an Execution needs the executing role")
        try:
            with transaction(database()) as session:
                started = lifecycle.start(session, actor_of(who), protocol_id)
                return view(session, started)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.get("/runs/{run_id}/execution", operation_id="getExecution")
    def get_execution(run_id: str, who: Annotated[Principal, Depends(principal)]) -> ExecutionView:
        """Reads the Execution of the run's Protocol: its status, events and rows from the
        Approved Protocol's frozen copy. Any signed-in role may read it."""
        with transaction(database()) as session:
            protocol = assembly_lifecycle.latest_of_run(session, run_id)
            if protocol is None:
                raise HTTPException(404, f"no Protocol was started from run {run_id}")
            found = lifecycle.of_protocol(session, protocol.id)
            if found is None:
                raise HTTPException(404, f"no Execution was started for Protocol {protocol.id}")
            return view(session, found)

    return router
