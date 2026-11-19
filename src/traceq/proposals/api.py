"""The database routes over runs: importing a run as Proposals, reading where they stand,
recording Proposal Decisions and counting them (spec #105), and the Protocol Draft of a Review
Package run with the decisions on its findings (spec #196).

Every route needs a valid bearer token; importing and deciding need the deciding role, so the
Audit Trail names who did it. Without a database (default settings) the routes answer 401.
One decision per request: there is no bulk route.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from traceq.audit import Actor
from traceq.db import transaction
from traceq.identity import Principal
from traceq.proposals import decisions
from traceq.proposals.decisions import State, Verdict
from traceq.proposals.keys import Kind
from traceq.proposals.store import RunFiles, import_run
from traceq.runs.api import (
    DRAFTS_FILE,
    FINDINGS_FILE,
    MATRIX_FILE,
    RUN_FILE,
    find_run,
    read_served,
)
from traceq.runs.protocol_draft import DRAFT_FILE
from traceq.runs.schemas import (
    DraftCheckFinding,
    DraftDocument,
    DraftedTestSteps,
    DraftTestStep,
    DraftTraceRow,
    Findings,
    Matrix,
    ProtocolDraft,
    VendorDocument,
)
from traceq.traceability.coverage import CoverageClass


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImportedRun(_Model):
    """A run imported as Proposals."""

    run_id: str
    equipment: str
    proposals: int
    """How many Proposals the run holds."""
    already_imported: bool
    """True when the run was imported before: nothing changed."""


class NewDecision(_Model):
    """A Proposal Decision on the content the run proposed.

    A Check Finding, AI Finding or drafted Test Step is ``accepted`` or ``rejected``; a
    Coverage row is ``accepted`` or ``edited`` to another class (only ``edited`` when the
    system proposed no class). A Reason for Change is required for ``rejected`` and
    ``edited``, and for any decision that replaces an earlier one on the same content."""

    decision: Verdict
    coverage: CoverageClass | None = None
    """For ``edited``: the class the Coverage row is changed to."""
    reason: str | None = None
    """The Reason for Change."""


class Decision(_Model):
    """A recorded Proposal Decision: what, who, when and why."""

    id: int
    decision: Verdict
    coverage: CoverageClass | None
    """For a Coverage row ``edited``: the class the person chose; ``null`` otherwise."""
    reason: str | None
    run_id: str
    """The run whose Proposal it was made on."""
    content_hash: str
    """The content it was made on."""
    subject: str
    issuer: str
    name: str
    """The name shown for the person at the time."""
    at: datetime


class Proposal(_Model):
    """A Proposal of a run, where it stands in the run's files, and its decision state."""

    id: int
    """Its identity across runs: the same subject gets the same id in every run."""
    kind: Kind
    """A Coverage row, or the layer of a finding (Check Finding, AI Finding); ``draft``: a
    Check Finding on the Protocol Draft of a Review Package run; ``test_step``: an IQ/OQ Test
    Step the run drafted (``drafts.json``)."""
    requirement: str | None
    """For a Coverage row or a drafted Test Step: the requirement id."""
    position: int | None
    """For a finding: its position in its layer's list in ``findings.json``, from 0; for a
    draft finding, in the findings of the Protocol Draft."""
    content_hash: str
    """What this run proposed about it, hashed as the content a decision rests on."""
    state: State
    """``decided``: a decision exists for this content, also one made on another run.
    ``changed``: decisions exist only for other content, so it is undecided again.
    ``undecided``: no decision exists."""
    decisions: list[Decision]
    """For ``decided``: every decision on this content, the current one first."""
    previous: Decision | None
    """For ``changed``: the latest decision, made on other content."""
    previous_class: CoverageClass | None
    """For a ``changed`` Coverage row: the class that latest decision settled on, the class
    proposed on its content when ``accepted``, the class chosen when ``edited``. ``null``
    otherwise."""


class KindCounts(_Model):
    """The Proposals of one kind in a run, by decision state. ``total`` is the sum of
    ``undecided``, ``changed`` and the current decisions ``accepted``, ``edited`` and
    ``rejected``."""

    total: int
    undecided: int
    """No decision exists."""
    accepted: int
    edited: int
    rejected: int
    changed: int
    """Changed since it was decided: undecided again."""
    decided_not_proposed: int
    """Decided earlier, not proposed by this run: Proposals of the run's Equipment with a
    decision that this run does not hold. Not in ``total``."""


class DecisionCounts(_Model):
    """Stored decisions counted per kind of Proposal for one run. Counts, not a measure of
    quality."""

    run_id: str
    coverage: KindCounts
    check: KindCounts
    ai: KindCounts
    draft: KindCounts
    """Findings on the Protocol Draft of a Review Package run; all zero for another run."""
    test_step: KindCounts
    """Drafted IQ/OQ Test Steps; all zero for a run imported without ``drafts.json``."""


class DraftFindingView(_Model):
    """A finding on the Protocol Draft and the Proposal it was imported as."""

    finding: DraftCheckFinding
    proposal: Proposal | None
    """``null`` until the run is imported. Accepted means "real, will be fixed": it creates
    no task or revision."""


class ProtocolDraftView(_Model):
    """The Protocol Draft of a Review Package run: its Test Steps in draft order, its
    traceability rows and its findings, each with its decision state."""

    run_id: str
    imported: bool
    """Whether the run is imported: only then do its findings carry a Proposal."""
    package: str
    document: DraftDocument
    test_steps: tuple[DraftTestStep, ...]
    trace_rows: tuple[DraftTraceRow, ...]
    findings: list[DraftFindingView]
    vendor_documents: tuple[VendorDocument, ...]
    """The vendor documents beside each Test Step: each shows its facts or "none"."""


def _decision(d: decisions.Decision) -> Decision:
    return Decision(
        id=d.id,
        decision=d.decision,
        coverage=d.coverage,
        reason=d.reason,
        run_id=d.run_id,
        content_hash=d.content_hash,
        subject=d.actor.subject,
        issuer=d.actor.issuer,
        name=d.actor.name,
        at=d.at,
    )


def proposal_view(s: decisions.Standing) -> Proposal:
    return Proposal(
        id=s.proposal_id,
        kind=s.kind,
        requirement=s.requirement,
        position=s.position,
        content_hash=s.content_hash,
        state=s.state,
        decisions=[_decision(d) for d in s.decisions],
        previous=None if s.previous is None else _decision(s.previous),
        previous_class=s.previous_class,
    )


def actor_of(who: Principal) -> Actor:
    return Actor(subject=who.subject, issuer=who.issuer, name=who.name)


def create_router(
    runs: Path,
    db: Engine | None,
    principal: Callable[..., Principal],
    before_accepting: Callable[[Session, str, int], None] | None = None,
) -> APIRouter:
    """``db``: the database as the application role; none with default settings, when
    ``principal`` refuses every request. ``before_accepting``: called with the session, run id
    and Proposal id before an ``accepted`` decision is recorded, in its transaction; it raises
    ``decisions.Conflict`` to refuse it (the assembled Protocol's one-Test-Step rule)."""
    router = APIRouter()

    def database() -> Engine:
        if db is None:  # unreachable: without a database no token is accepted
            raise HTTPException(401, "no database is configured")
        return db

    @router.post("/runs/{run_id}/import", operation_id="importRun")
    def import_(run_id: str, who: Annotated[Principal, Depends(principal)]) -> ImportedRun:
        """Imports a run folder as Proposals, in one transaction. Importing a run already
        imported changes nothing. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "importing a run needs the deciding role")
        folder = find_run(runs, run_id)
        if folder is None:
            raise HTTPException(404, f"no run {run_id}")
        try:
            meta: dict[str, Any] = read_served(folder / RUN_FILE)
            draft = folder / DRAFT_FILE
            drafted = folder / DRAFTS_FILE
            files = RunFiles(
                meta=meta,
                matrix=Matrix.model_validate(read_served(folder / MATRIX_FILE)),
                findings=Findings.model_validate(read_served(folder / FINDINGS_FILE)),
                draft=ProtocolDraft.model_validate(read_served(draft)) if draft.is_file() else None,
                drafted=DraftedTestSteps.model_validate(read_served(drafted))
                if drafted.is_file()
                else None,
            )
        except (OSError, ValueError, ValidationError) as e:
            raise HTTPException(422, f"{run_id} is not a run folder that can be imported") from e
        if meta.get("run_id") != run_id:
            raise HTTPException(422, f"the run folder {run_id} names another run id")
        with transaction(database()) as session:
            done = import_run(session, actor_of(who), files)
        return ImportedRun(
            run_id=done.run_id,
            equipment=done.equipment,
            proposals=done.proposals,
            already_imported=done.already_imported,
        )

    @router.get("/runs/{run_id}/proposals", operation_id="listProposals")
    def list_proposals(
        run_id: str, who: Annotated[Principal, Depends(principal)]
    ) -> list[Proposal]:
        """The Proposals of an imported run, in the order of its files, with their decision
        state and decisions."""
        with transaction(database()) as session:
            stood = decisions.standings(session, run_id)
        if stood is None:
            raise HTTPException(404, f"run {run_id} is not imported")
        return [proposal_view(s) for s in stood]

    @router.get("/runs/{run_id}/protocol-draft", operation_id="getProtocolDraft")
    def get_protocol_draft(
        run_id: str, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolDraftView:
        """The Protocol Draft a Review Package run read: its Test Steps in draft order, its
        traceability rows and its findings, each with its decision state once the run is
        imported. Any role may read it; deciding goes through ``recordDecision``."""
        folder = find_run(runs, run_id)
        if folder is None:
            raise HTTPException(404, f"no run {run_id}")
        path = folder / DRAFT_FILE
        if not path.is_file():
            raise HTTPException(404, f"{run_id} is not a Review Package run")
        try:
            draft = ProtocolDraft.model_validate(read_served(path))
        except (OSError, ValueError, ValidationError) as e:
            raise HTTPException(422, f"{run_id}: the Protocol Draft cannot be read") from e
        with transaction(database()) as session:
            stood = decisions.standings(session, run_id)
        by_position = {s.position: proposal_view(s) for s in (stood or []) if s.kind == "draft"}
        return ProtocolDraftView(
            run_id=run_id,
            imported=stood is not None,
            package=draft.package,
            document=draft.document,
            test_steps=draft.test_steps,
            trace_rows=draft.trace_rows,
            findings=[
                DraftFindingView(finding=f, proposal=by_position.get(i))
                for i, f in enumerate(draft.findings)
            ],
            vendor_documents=draft.vendor_documents,
        )

    @router.post(
        "/runs/{run_id}/proposals/{proposal_id}/decisions",
        operation_id="recordDecision",
        status_code=201,
    )
    def record_decision(
        run_id: str,
        proposal_id: int,
        body: NewDecision,
        who: Annotated[Principal, Depends(principal)],
    ) -> Decision:
        """Records one Proposal Decision on the content this run proposed, with its Audit
        Trail entry. Earlier decisions stay. Accepting a drafted Test Step is refused (409)
        while the open Protocol of its Equipment holds a written Test Step for its
        requirement; ``edited`` on a drafted Test Step goes through ``editDraftedTestStep``.
        Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "recording a decision needs the deciding role")
        try:
            with transaction(database()) as session:
                if body.decision == "accepted" and before_accepting is not None:
                    before_accepting(session, run_id, proposal_id)
                made = decisions.record(
                    session,
                    actor_of(who),
                    run_id,
                    proposal_id,
                    body.decision,
                    body.coverage,
                    body.reason,
                )
        except decisions.NotInRun as e:
            raise HTTPException(404, str(e)) from e
        except decisions.Refused as e:
            raise HTTPException(422, str(e)) from e
        except decisions.Conflict as e:
            raise HTTPException(409, str(e)) from e
        return _decision(made)

    @router.get("/runs/{run_id}/decision-counts", operation_id="decisionCounts")
    def decision_counts(
        run_id: str, who: Annotated[Principal, Depends(principal)]
    ) -> DecisionCounts:
        """Per kind of Proposal of an imported run: how many there are and where they stand."""
        with transaction(database()) as session:
            got = decisions.counts(session, run_id)
        if got is None:
            raise HTTPException(404, f"run {run_id} is not imported")

        def kind(k: decisions.KindCounts) -> KindCounts:
            return KindCounts(
                total=k.total,
                undecided=k.undecided,
                accepted=k.accepted,
                edited=k.edited,
                rejected=k.rejected,
                changed=k.changed,
                decided_not_proposed=k.decided_not_proposed,
            )

        return DecisionCounts(
            run_id=run_id,
            coverage=kind(got["coverage"]),
            check=kind(got["check"]),
            ai=kind(got["ai"]),
            draft=kind(got["draft"]),
            test_step=kind(got["test_step"]),
        )

    return router
