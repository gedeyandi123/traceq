"""The routes of the Protocol assembled in TraceQ (spec #247, "API"): start the Protocol of a
run's Equipment, read the Protocol of a run, withdraw a Protocol in Draft status.

Every route needs a valid bearer token; starting and withdrawing need the deciding role, so the
Audit Trail names who did it. Reading is open to any signed-in role. Accepting and rejecting a
drafted Test Step go through ``recordDecision``. Errors: 401 without a token, 403 without the
role, 404 unknown, 409 for a refused state change with the reason in words.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from traceq.assembly import lifecycle
from traceq.assembly.lifecycle import EventKind, Status
from traceq.assembly.rows import Blocker, DraftOfRow, ProtocolRow, RowKind, rows_of
from traceq.db import transaction
from traceq.identity import Principal
from traceq.proposals.api import Proposal, actor_of, proposal_view
from traceq.runs.api import DRAFTS_FILE, find_run
from traceq.runs.schemas import Cite, DraftedTestStep, EvidenceStep
from traceq.traceability.coverage import CoverageClass
from traceq.traceability.values import Value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProtocolEvent(_Model):
    """A status change of a Protocol: what, who, when and why."""

    id: int
    event: EventKind
    status: Status
    """The status after it: ``started`` and ``returned`` give ``draft``."""
    reason: str | None
    """For a return or a withdrawal: the reason given."""
    subject: str
    issuer: str
    name: str
    """The name shown for the person at the time."""
    at: datetime


class RowDraft(_Model):
    """A drafted Test Step of the row's requirement, as the run drafted it, and the Proposal it
    was imported as, decided with ``recordDecision`` (accepted or rejected)."""

    draft: DraftedTestStep
    proposal: Proposal


class RowTestStep(_Model):
    """The one Test Step of a Test Step row."""

    origin: Literal["accepted_draft"] = "accepted_draft"
    """``accepted_draft``: a drafted Test Step accepted as drafted."""
    proposal_id: int | None
    """The drafted Test Step's Proposal."""
    description: str
    method: str
    instrument: str | None
    acceptance: Value | None
    """The Acceptance Criterion; ``null`` while it is "to be set by a human"."""
    acceptance_flag: str | None


class ProtocolRowView(_Model):
    """One requirement of the run and what the Protocol holds for it."""

    requirement: str
    text: str
    source: Cite
    """Where the requirement is printed in the URS."""
    coverage: Proposal
    """The requirement's Coverage row and where it stands."""
    decided_class: CoverageClass | None
    """The class a human decided on this run's content; ``null`` while undecided or changed
    since it was decided."""
    kind: RowKind
    """``undecided``: Coverage not decided on this run's content, so the kind is unknown.
    ``vendor_reference``: decided ``covered_by_vendor`` with no accepted draft, proven by the
    vendor's Evidence and not tested again on site. ``test_step``: needs one Test Step."""
    evidence: tuple[EvidenceStep, ...]
    """For a Vendor Reference: the vendor's Evidence steps (document, revision, step)."""
    test_step: RowTestStep | None
    """For a Test Step row: its Test Step, ``null`` while it has none."""
    drafts: list[RowDraft]
    """The drafted Test Steps of the requirement, with their decision state."""
    blockers: list[Blocker]
    """What blocks this row: ``coverage_undecided``, ``no_test_step``."""


class ProtocolView(_Model):
    """A Protocol assembled in TraceQ, for one Equipment, started from one imported run. Not
    a Protocol Draft: that is the site's document under Pre-review."""

    id: int
    equipment: str
    run_id: str
    """The run it was started from."""
    status: Status
    """The latest event's status."""
    events: list[ProtocolEvent]
    """Every status change, oldest first."""
    rows: list[ProtocolRowView] | None
    """In Draft status: one row per requirement of the run, in requirement order, computed
    from the current decisions. ``null`` in any other status."""


class Withdrawal(_Model):
    reason: str
    """Why the Protocol is given up."""


def _event(e: lifecycle.Event) -> ProtocolEvent:
    return ProtocolEvent(
        id=e.id,
        event=e.event,
        status=e.status,
        reason=e.reason,
        subject=e.actor.subject,
        issuer=e.actor.issuer,
        name=e.actor.name,
        at=e.at,
    )


def _draft(d: DraftOfRow) -> RowDraft:
    return RowDraft(draft=d.draft, proposal=proposal_view(d.standing))


def _test_step(d: DraftOfRow) -> RowTestStep:
    s = d.draft
    return RowTestStep(
        proposal_id=d.standing.proposal_id,
        description=s.description,
        method=s.method,
        instrument=s.instrument,
        acceptance=s.acceptance,
        acceptance_flag=s.acceptance_flag,
    )


def _row(r: ProtocolRow) -> ProtocolRowView:
    req = r.requirement
    return ProtocolRowView(
        requirement=req.id,
        text=req.text,
        source=req.source,
        coverage=proposal_view(r.coverage),
        decided_class=r.decided_class,
        kind=r.kind,
        evidence=req.evidence if r.kind == "vendor_reference" else (),
        test_step=None if r.test_step is None else _test_step(r.test_step),
        drafts=[_draft(d) for d in r.drafts],
        blockers=list(r.blockers),
    )


def create_router(runs: Path, db: Engine | None, principal: Callable[..., Principal]) -> APIRouter:
    """``db``: the database as the application role; none with default settings, when
    ``principal`` refuses every request."""
    router = APIRouter()

    def database() -> Engine:
        if db is None:  # unreachable: without a database no token is accepted
            raise HTTPException(401, "no database is configured")
        return db

    def view(session: Session, p: lifecycle.AssembledProtocol) -> ProtocolView:
        rows = rows_of(session, p.run_id) if p.status == "draft" else None
        return ProtocolView(
            id=p.id,
            equipment=p.equipment,
            run_id=p.run_id,
            status=p.status,
            events=[_event(e) for e in p.events],
            rows=None if rows is None else [_row(r) for r in rows],
        )

    @router.post("/runs/{run_id}/protocol", operation_id="startProtocol", status_code=201)
    def start_protocol(run_id: str, who: Annotated[Principal, Depends(principal)]) -> ProtocolView:
        """Starts the Protocol of the run's Equipment from this imported run, in Draft status,
        with its Audit Trail entry. Refused (409) while a Protocol of the Equipment is open
        (Draft or Submitted), once one is approved, and for a run whose folder has
        ``drafts.json`` but which holds no drafted Test Step Proposals. Needs the deciding
        role."""
        if not who.may_decide:
            raise HTTPException(403, "starting a Protocol needs the deciding role")
        folder = find_run(runs, run_id)
        if folder is None:
            raise HTTPException(404, f"no run {run_id}")
        try:
            with transaction(database()) as session:
                started = lifecycle.start(
                    session, actor_of(who), run_id, drafted=(folder / DRAFTS_FILE).is_file()
                )
                return view(session, started)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.get("/runs/{run_id}/protocol", operation_id="getProtocol")
    def get_protocol(run_id: str, who: Annotated[Principal, Depends(principal)]) -> ProtocolView:
        """The Protocol most recently started from this run: its status and every status
        change, and in Draft status its rows computed from the current decisions. Any
        signed-in role may read it."""
        with transaction(database()) as session:
            found = lifecycle.latest_of_run(session, run_id)
            if found is None:
                raise HTTPException(404, f"no Protocol was started from run {run_id}")
            return view(session, found)

    @router.post("/protocols/{protocol_id}/withdraw", operation_id="withdrawProtocol")
    def withdraw_protocol(
        protocol_id: int, body: Withdrawal, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolView:
        """Withdraws a Protocol in Draft status, with a reason and its Audit Trail entry, so
        a new Protocol of the Equipment can be started. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "withdrawing a Protocol needs the deciding role")
        try:
            with transaction(database()) as session:
                done = lifecycle.withdraw(session, actor_of(who), protocol_id, body.reason)
                return view(session, done)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Refused as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    return router
