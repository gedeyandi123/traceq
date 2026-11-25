"""The database routes for review rounds and pre-review report exports (Step 6, #319).

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine

from traceq.audit import Actor
from traceq.db import transaction
from traceq.identity import Principal
from traceq.rounds import store
from traceq.rounds.diff import RoundDiff
from traceq.rounds.store import (
    CloseOutcome,
    Conflict,
    DocumentVersion,
    NotFound,
    Refused,
    ReportExport,
    ReviewRound,
    RoundEvent,
    RoundEventKind,
    RoundStatus,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DocumentVersionView(_Model):
    id: int
    equipment: str
    doc_id: str
    rev: int
    doc_type: str | None
    source: str
    sha256: str
    first_seen_run_id: str
    at: datetime


class ReviewRoundEventView(_Model):
    id: int
    round_id: int
    event: RoundEventKind
    reason: str | None
    at: datetime
    subject: str
    issuer: str
    name: str


class ReportExportView(_Model):
    id: int
    round_id: int
    report_kind: str
    at: datetime
    subject: str
    issuer: str
    name: str
    snapshot_hash: str
    pdf_sha256: str
    template_version: str
    typst_version: str


class ReviewRoundView(_Model):
    id: int
    equipment: str
    round_number: int
    run_id: str
    previous_round_id: int | None
    at: datetime
    status: RoundStatus
    documents: list[DocumentVersionView]
    events: list[ReviewRoundEventView]
    exports: list[ReportExportView]


class RoundDiffView(_Model):
    previous_round_number: int
    previous_run_id: str
    documents_added: tuple[str, ...]
    documents_revised: tuple[str, ...]
    documents_unchanged: tuple[str, ...]
    documents_removed: tuple[str, ...]
    findings_resolved: int
    findings_persisted: int
    findings_new: int
    decisions_carried_forward: int
    decisions_changed: int
    decisions_undecided: int


class RunRoundsView(_Model):
    equipment: str
    current_round_id: int
    rounds: list[ReviewRoundView]
    diff: RoundDiffView | None


class CloseRoundRequest(_Model):
    outcome: CloseOutcome
    reason: str | None = None


def _actor_of(who: Principal) -> Actor:
    return Actor(subject=who.subject, issuer=who.issuer, name=who.name)


def _doc_view(d: DocumentVersion) -> DocumentVersionView:
    return DocumentVersionView(
        id=d.id,
        equipment=d.equipment,
        doc_id=d.doc_id,
        rev=d.rev,
        doc_type=d.doc_type,
        source=d.source,
        sha256=d.sha256,
        first_seen_run_id=d.first_seen_run_id,
        at=d.at,
    )


def _event_view(e: RoundEvent) -> ReviewRoundEventView:
    return ReviewRoundEventView(
        id=e.id,
        round_id=e.round_id,
        event=e.event,
        reason=e.reason,
        at=e.at,
        subject=e.actor.subject,
        issuer=e.actor.issuer,
        name=e.actor.name,
    )


def _export_view(x: ReportExport) -> ReportExportView:
    if x.round_id is None:
        raise ValueError(f"export {x.id} has no round_id")
    return ReportExportView(
        id=x.id,
        round_id=x.round_id,
        report_kind=x.report_kind,
        at=x.at,
        subject=x.actor.subject,
        issuer=x.actor.issuer,
        name=x.actor.name,
        snapshot_hash=x.snapshot_hash,
        pdf_sha256=x.pdf_sha256,
        template_version=x.template_version,
        typst_version=x.typst_version,
    )


def _round_view(r: ReviewRound) -> ReviewRoundView:
    return ReviewRoundView(
        id=r.id,
        equipment=r.equipment,
        round_number=r.round_number,
        run_id=r.run_id,
        previous_round_id=r.previous_round_id,
        at=r.at,
        status=r.status,
        documents=[_doc_view(d) for d in r.documents],
        events=[_event_view(e) for e in r.events],
        exports=[_export_view(x) for x in r.exports],
    )


def _diff_view(d: RoundDiff) -> RoundDiffView:
    return RoundDiffView(
        previous_round_number=d.previous_round_number,
        previous_run_id=d.previous_run_id,
        documents_added=d.documents_added,
        documents_revised=d.documents_revised,
        documents_unchanged=d.documents_unchanged,
        documents_removed=d.documents_removed,
        findings_resolved=d.findings_resolved,
        findings_persisted=d.findings_persisted,
        findings_new=d.findings_new,
        decisions_carried_forward=d.decisions_carried_forward,
        decisions_changed=d.decisions_changed,
        decisions_undecided=d.decisions_undecided,
    )


def create_router(
    runs: Path,
    db: Engine | None,
    principal: Callable[..., Principal],
) -> APIRouter:
    router = APIRouter()

    def database() -> Engine:
        if db is None:
            raise HTTPException(401, "no database is configured")
        return db

    @router.get("/runs/{run_id}/rounds", operation_id="getRunRounds")
    def get_run_rounds(run_id: str, who: Annotated[Principal, Depends(principal)]) -> RunRoundsView:
        """Review rounds for the run's Equipment, and diff vs the previous round."""
        try:
            with transaction(database()) as session:
                current, all_rounds, diff = store.rounds_for_run(session, run_id)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        return RunRoundsView(
            equipment=current.equipment,
            current_round_id=current.id,
            rounds=[_round_view(r) for r in all_rounds],
            diff=None if diff is None else _diff_view(diff),
        )

    @router.post("/rounds/{round_id}/close", operation_id="closeReviewRound")
    def close_review_round(
        round_id: int,
        body: CloseRoundRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ReviewRoundView:
        """Closes an open review round. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "closing a review round needs the deciding role")
        try:
            with transaction(database()) as session:
                updated = store.close_round(
                    session, _actor_of(who), round_id, body.outcome, body.reason
                )
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        except Conflict as e:
            raise HTTPException(409, str(e)) from e
        except Refused as e:
            raise HTTPException(422, str(e)) from e
        return _round_view(updated)

    @router.post(
        "/rounds/{round_id}/exports",
        operation_id="exportPreReviewReport",
        status_code=201,
    )
    def export_pre_review_report(
        round_id: int,
        who: Annotated[Principal, Depends(principal)],
    ) -> ReportExportView:
        """Generates and stores an immutable Pre-Review Report PDF export."""
        if not (who.may_decide or who.may_approve):
            raise HTTPException(
                403, "exporting a pre-review report needs the deciding or approving role"
            )
        try:
            with transaction(database()) as session:
                export = store.export_pre_review(session, _actor_of(who), runs, round_id)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        return _export_view(export)

    @router.get(
        "/rounds/{round_id}/exports/{export_id}/pdf",
        operation_id="downloadPreReviewReportPdf",
        responses={200: {"content": {"application/pdf": {}}}},
    )
    def download_pre_review_report_pdf(
        round_id: int,
        export_id: int,
        who: Annotated[Principal, Depends(principal)],
    ) -> Response:
        """Re-renders and returns the stored Pre-Review Report PDF without DB writes."""
        try:
            with transaction(database()) as session:
                pdf_bytes = store.render_stored_export_pdf(session, round_id, export_id)
        except NotFound as e:
            raise HTTPException(404, str(e)) from e
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="pre-review-{round_id}-{export_id}.pdf"'
                )
            },
        )

    return router
