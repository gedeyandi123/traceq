"""The routes of Protocol Execution (ADR 0013, spec #270, #271): start an Execution of an
Approved Protocol, and read an Execution with its rows from the Protocol's frozen copy.

Every route needs a valid bearer token; starting needs ``qualification-executor``;
reading is open to any signed-in role. Errors: 401 without a token, 403 without the role, 404
unknown, 409 for a refused state change with the reason in words.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from traceq.assembly import lifecycle as assembly_lifecycle
from traceq.assembly import submission
from traceq.assembly.attributes import Stage
from traceq.assembly.submission import FrozenRow, ProtocolCopy
from traceq.assembly.written import Acceptance
from traceq.db import transaction
from traceq.execution import completion, deviations, lifecycle, reports, results
from traceq.execution.completion import CompletionBlockers, ExecutionCopy, compute_blockers
from traceq.execution.deviations import (
    CLOSURE_NOTE,
    InvestigationRequest,
    OpenManualDeviationRequest,
    ReturnDeviationRequest,
)
from traceq.execution.lifecycle import EventKind, Status
from traceq.execution.results import (
    WITNESS_NOTE,
    ConfirmWitnessRequest,
    CorrectAttemptRequest,
    DeviationCause,
    DeviationClass,
    DeviationEventKind,
    DeviationStatus,
    InstrumentInput,
    OutcomeKind,
    RecordAttemptRequest,
    ResultValue,
    RetestRowRequest,
    Verdict,
)
from traceq.identity import Principal
from traceq.proposals.api import actor_of
from traceq.reports import QUALIFICATION_APPROVAL_NOTE, QualificationCounts, TechnicalConclusion
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
    stage: Stage | None = None
    witness_required: bool = False


class WitnessConfirmationView(_Model):
    """One Witness confirmation bound to an attempt version's hash."""

    id: int
    at: datetime
    version_id: int
    version_hash: str
    subject: str
    issuer: str
    name: str
    voided: bool
    note: str


class AttemptVersionView(_Model):
    """One immutable version of an attempt's Result."""

    id: int
    at: datetime
    version: int
    outcome_kind: OutcomeKind
    not_performable_reason: str | None
    value: ResultValue | None
    observation: str | None
    instruments: list[InstrumentInput]
    no_calibrated_instrument_reason: str | None
    evidence: list[str]
    verdict: Verdict
    version_hash: str
    reason_for_change: str | None
    subject: str
    issuer: str
    name: str
    witness_confirmations: list[WitnessConfirmationView] = []


class AttemptView(_Model):
    """One attempt on a Test Step row, with its versions oldest first."""

    id: int
    at: datetime
    attempt_number: int
    requirement: str
    subject: str
    issuer: str
    name: str
    versions: list[AttemptVersionView]
    latest: AttemptVersionView
    retest_deviation_id: int | None = None
    retest_reason: str | None = None


class DeviationEventView(_Model):
    """One status event on a Deviation."""

    id: int
    at: datetime
    event: DeviationEventKind
    status: DeviationStatus
    reason: str | None
    subject: str
    issuer: str
    name: str


class DeviationInvestigationView(_Model):
    """One immutable version of a Deviation's Investigation."""

    id: int
    at: datetime
    version: int
    investigation: str
    deviation_class: DeviationClass
    capa: str | None
    reason_for_change: str | None
    subject: str
    issuer: str
    name: str


class DeviationView(_Model):
    """One Deviation on an Execution."""

    id: int
    at: datetime
    deviation_number: int
    requirement: str | None
    attempt_id: int | None
    cause: DeviationCause
    status: DeviationStatus
    deviation_class: DeviationClass | None
    description: str
    subject: str
    issuer: str
    name: str
    events: list[DeviationEventView]
    investigations: list[DeviationInvestigationView]
    closure_note: str | None = None


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
    attempts: list[AttemptView]
    """Attempts recorded on this Test Step row, in attempt_number order."""


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
    deviations: list[DeviationView]
    completion_blockers: CompletionBlockers
    frozen_copy: ExecutionCopy | None = None
    copy_hash: str | None = None


class ApproveQualificationReportRequest(_Model):
    """Payload to approve a Qualification Report for a completed Execution."""

    conclusion_note: str | None = None
    next_requalification_date: date | None = None


class QualificationExportView(_Model):
    """One immutable Qualification Report export."""

    id: int
    revision_number: int
    technical_conclusion: TechnicalConclusion
    conclusion_note: str | None
    next_requalification_date: date | None
    approval_note: str
    snapshot_hash: str
    pdf_sha256: str
    template_version: str
    typst_version: str
    subject: str
    issuer: str
    name: str
    at: datetime


class QualificationReportView(_Model):
    """Qualification Report state for a completed Execution."""

    execution_id: int
    protocol_id: int
    equipment: str
    run_id: str
    execution_copy_hash: str
    completed_at: datetime
    technical_conclusion: TechnicalConclusion
    counts: QualificationCounts
    approval_note: str
    latest_export: QualificationExportView | None = None
    exports: list[QualificationExportView] = []


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


def _attempt_version(v: results.AttemptVersion) -> AttemptVersionView:
    return AttemptVersionView(
        id=v.id,
        at=v.at,
        version=v.version,
        outcome_kind=v.outcome_kind,
        not_performable_reason=v.not_performable_reason,
        value=v.value,
        observation=v.observation,
        instruments=list(v.instruments),
        no_calibrated_instrument_reason=v.no_calibrated_instrument_reason,
        evidence=list(v.evidence),
        verdict=v.verdict,
        version_hash=v.version_hash,
        reason_for_change=v.reason_for_change,
        subject=v.actor.subject,
        issuer=v.actor.issuer,
        name=v.actor.name,
        witness_confirmations=[
            WitnessConfirmationView(
                id=w.id,
                at=w.at,
                version_id=w.version_id,
                version_hash=w.version_hash,
                subject=w.actor.subject,
                issuer=w.actor.issuer,
                name=w.actor.name,
                voided=w.voided,
                note=WITNESS_NOTE,
            )
            for w in v.witness_confirmations
        ],
    )


def _attempt(a: results.Attempt) -> AttemptView:
    versions = [_attempt_version(v) for v in a.versions]
    return AttemptView(
        id=a.id,
        at=a.at,
        attempt_number=a.attempt_number,
        requirement=a.requirement,
        subject=a.actor.subject,
        issuer=a.actor.issuer,
        name=a.actor.name,
        versions=versions,
        latest=versions[-1],
        retest_deviation_id=a.retest_deviation_id,
        retest_reason=a.retest_reason,
    )


def _deviation(d: results.Deviation) -> DeviationView:
    return DeviationView(
        id=d.id,
        at=d.at,
        deviation_number=d.deviation_number,
        requirement=d.requirement,
        attempt_id=d.attempt_id,
        cause=d.cause,
        status=d.status,
        deviation_class=d.deviation_class,
        description=d.description,
        subject=d.actor.subject,
        issuer=d.actor.issuer,
        name=d.actor.name,
        events=[
            DeviationEventView(
                id=e.id,
                at=e.at,
                event=e.event,
                status=e.status,
                reason=e.reason,
                subject=e.actor.subject,
                issuer=e.actor.issuer,
                name=e.actor.name,
            )
            for e in d.events
        ],
        investigations=[
            DeviationInvestigationView(
                id=inv.id,
                at=inv.at,
                version=inv.version,
                investigation=inv.investigation,
                deviation_class=inv.deviation_class,
                capa=inv.capa,
                reason_for_change=inv.reason_for_change,
                subject=inv.actor.subject,
                issuer=inv.actor.issuer,
                name=inv.actor.name,
            )
            for inv in d.investigations
        ],
        closure_note=CLOSURE_NOTE if d.status == "closed" else None,
    )


def _row(r: FrozenRow, attempts: tuple[results.Attempt, ...]) -> ExecutionRowView:
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
            stage=step.stage,
            witness_required=step.witness_required,
        ),
        attempts=[_attempt(a) for a in attempts],
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
        attempts_by_req = results.attempts_of(session, ex.id)
        deviations_list = results.deviations_of(session, ex.id)
        blockers = compute_blockers(copy, attempts_by_req, deviations_list)
        comp = completion.get_completion(session, ex.id) if ex.status == "completed" else None
        return ExecutionView(
            id=ex.id,
            protocol_id=ex.protocol_id,
            equipment=copy.equipment,
            run_id=copy.run_id,
            submission_event_id=ex.submission_event_id,
            submission_hash=ex.submission_hash,
            status=ex.status,
            events=[_event(e) for e in ex.events],
            rows=[_row(r, attempts_by_req.get(r.requirement, ())) for r in copy.rows],
            deviations=[_deviation(d) for d in deviations_list],
            completion_blockers=blockers,
            frozen_copy=None if comp is None else comp.copy,
            copy_hash=None if comp is None else comp.copy_hash,
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

    @router.post(
        "/executions/{execution_id}/rows/{requirement}/attempts",
        operation_id="recordAttempt",
        status_code=201,
    )
    def record_attempt(
        execution_id: int,
        requirement: str,
        body: RecordAttemptRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Records the first attempt on a Test Step row of an ``in_progress`` Execution, judged
        by code, with instruments and automatic Deviations in the same transaction."""
        if not who.may_execute:
            raise HTTPException(403, "recording a Result needs the executing role")
        try:
            with transaction(database()) as session:
                results.record_attempt(session, actor_of(who), execution_id, requirement, body)
                updated = lifecycle.get(session, execution_id)
                if updated is None:
                    raise lifecycle.NotFound(f"no Execution {execution_id}")
                return view(session, updated)
        except results.InvalidResult as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.post(
        "/executions/{execution_id}/rows/{requirement}/attempts/{attempt_number}/corrections",
        operation_id="correctAttempt",
        status_code=201,
    )
    def correct_attempt(
        execution_id: int,
        requirement: str,
        attempt_number: int,
        body: CorrectAttemptRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Adds a new version to an existing attempt with a required Reason for Change,
        enforcing Performer ownership and Deviation status lock."""
        if not who.may_execute:
            raise HTTPException(403, "correcting a Result needs the executing role")
        return run_execution_write(
            execution_id,
            lambda s: results.correct_attempt(
                s, actor_of(who), execution_id, requirement, attempt_number, body
            ),
        )

    @router.post(
        "/executions/{execution_id}/rows/{requirement}/retests",
        operation_id="retestRow",
        status_code=201,
    )
    def retest_row(
        execution_id: int,
        requirement: str,
        body: RetestRowRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Records a new attempt (Retest) on a failed Test Step row, naming an Open Deviation
        linked to that Test Step."""
        if not who.may_execute:
            raise HTTPException(403, "retesting a Test Step needs the executing role")
        return run_execution_write(
            execution_id,
            lambda s: results.retest_row(s, actor_of(who), execution_id, requirement, body),
        )

    def run_execution_write(execution_id: int, fn: Callable[[Session], object]) -> ExecutionView:
        try:
            with transaction(database()) as session:
                fn(session)
                updated = lifecycle.get(session, execution_id)
                if updated is None:
                    raise lifecycle.NotFound(f"no Execution {execution_id}")
                return view(session, updated)
        except results.InvalidResult as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.post(
        "/executions/{execution_id}/deviations",
        operation_id="openManualDeviation",
        status_code=201,
    )
    def open_manual_deviation(
        execution_id: int,
        body: OpenManualDeviationRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Opens a manual Deviation on an ``in_progress`` Execution, linked to one Test Step row
        or to the Execution."""
        if not who.may_execute:
            raise HTTPException(403, "opening a manual Deviation needs the executing role")
        return run_execution_write(
            execution_id,
            lambda s: deviations.open_manual_deviation(s, actor_of(who), execution_id, body),
        )

    @router.post(
        "/executions/{execution_id}/deviations/{deviation_id}/investigations",
        operation_id="addDeviationInvestigation",
        status_code=201,
    )
    def add_deviation_investigation(
        execution_id: int,
        deviation_id: int,
        body: InvestigationRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Records an immutable Investigation version on an ``open`` Deviation."""
        if not who.may_execute:
            raise HTTPException(403, "writing a Deviation Investigation needs the executing role")
        return run_execution_write(
            execution_id,
            lambda s: deviations.add_investigation(
                s, actor_of(who), execution_id, deviation_id, body
            ),
        )

    @router.post(
        "/executions/{execution_id}/deviations/{deviation_id}/submit",
        operation_id="submitDeviation",
    )
    def submit_deviation(
        execution_id: int,
        deviation_id: int,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Submits an ``open`` Deviation once an Investigation with a class is recorded."""
        if not who.may_execute:
            raise HTTPException(403, "submitting a Deviation needs the executing role")
        return run_execution_write(
            execution_id,
            lambda s: deviations.submit_deviation(s, actor_of(who), execution_id, deviation_id),
        )

    @router.post(
        "/executions/{execution_id}/deviations/{deviation_id}/close",
        operation_id="closeDeviation",
    )
    def close_deviation(
        execution_id: int,
        deviation_id: int,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Closes a ``submitted`` Deviation (a recorded status, not an Electronic Signature),
        enforcing 4-way Separation of Duties."""
        if not who.may_approve:
            raise HTTPException(403, "closing a Deviation needs the approving role")
        return run_execution_write(
            execution_id,
            lambda s: deviations.close_deviation(s, actor_of(who), execution_id, deviation_id),
        )

    @router.post(
        "/executions/{execution_id}/deviations/{deviation_id}/return",
        operation_id="returnDeviation",
    )
    def return_deviation(
        execution_id: int,
        deviation_id: int,
        body: ReturnDeviationRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Returns a ``submitted`` Deviation to ``open`` with a required reason."""
        if not who.may_approve:
            raise HTTPException(403, "returning a Deviation needs the approving role")
        return run_execution_write(
            execution_id,
            lambda s: deviations.return_deviation(
                s, actor_of(who), execution_id, deviation_id, body
            ),
        )

    @router.post(
        "/executions/{execution_id}/rows/{requirement}/attempts/{attempt_number}/witness",
        operation_id="confirmWitness",
        status_code=201,
    )
    def confirm_witness(
        execution_id: int,
        requirement: str,
        attempt_number: int,
        body: ConfirmWitnessRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Records a Witness confirmation bound to the latest version's ``version_hash``
        (a recorded status, not an Electronic Signature (ADR 0007 phase 2))."""
        if not who.may_witness:
            raise HTTPException(403, "confirming a Result as Witness needs the witnessing role")
        return run_execution_write(
            execution_id,
            lambda s: results.confirm_witness(
                s, actor_of(who), execution_id, requirement, attempt_number, body
            ),
        )

    @router.post(
        "/executions/{execution_id}/complete",
        operation_id="completeExecution",
    )
    def complete_execution(
        execution_id: int,
        who: Annotated[Principal, Depends(principal)],
    ) -> ExecutionView:
        """Completes an ``in_progress`` Execution once every Test Step row has a Result and every
        Deviation is Closed, freezing its copy and SHA-256 hash."""
        if not who.may_execute:
            raise HTTPException(403, "completing an Execution needs the executing role")
        return run_execution_write(
            execution_id,
            lambda s: completion.complete_execution(s, actor_of(who), execution_id),
        )

    def _qual_export_view(exp: reports.QualificationExport) -> QualificationExportView:
        return QualificationExportView(
            id=exp.id,
            revision_number=exp.revision_number,
            technical_conclusion=exp.technical_conclusion,
            conclusion_note=exp.conclusion_note,
            next_requalification_date=exp.next_requalification_date,
            approval_note=exp.approval_note,
            snapshot_hash=exp.snapshot_hash,
            pdf_sha256=exp.pdf_sha256,
            template_version=exp.template_version,
            typst_version=exp.typst_version,
            subject=exp.actor.subject,
            issuer=exp.actor.issuer,
            name=exp.actor.name,
            at=exp.at,
        )

    def _qual_report_view(
        comp: completion.Completion, exports: list[reports.QualificationExport]
    ) -> QualificationReportView:
        export_views = [_qual_export_view(e) for e in exports]
        return QualificationReportView(
            execution_id=comp.execution_id,
            protocol_id=comp.copy.protocol_id,
            equipment=comp.copy.equipment,
            run_id=comp.copy.run_id,
            execution_copy_hash=comp.copy_hash,
            completed_at=comp.copy.completed_at,
            technical_conclusion=reports.compute_conclusion(comp.copy),
            counts=reports.compute_counts(comp.copy),
            approval_note=QUALIFICATION_APPROVAL_NOTE,
            latest_export=export_views[-1] if export_views else None,
            exports=export_views,
        )

    @router.get(
        "/runs/{run_id}/qualification-report",
        operation_id="getQualificationReport",
    )
    def get_qualification_report(
        run_id: str,
        who: Annotated[Principal, Depends(principal)],
    ) -> QualificationReportView:
        """Reads the Qualification Report state of a run's completed Execution. 404 if no
        Execution exists or it is not completed. Open to any signed-in role."""
        try:
            with transaction(database()) as session:
                _ex, comp, exports = reports.get_completed_for_run(session, run_id)
                return _qual_report_view(comp, exports)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e

    @router.post(
        "/executions/{execution_id}/qualification-reports",
        operation_id="approveQualificationReport",
        status_code=201,
    )
    def approve_qualification_report(
        execution_id: int,
        body: ApproveQualificationReportRequest,
        who: Annotated[Principal, Depends(principal)],
    ) -> QualificationReportView:
        """Approves and exports a Qualification Report PDF for a completed Execution. Needs the
        approving role and enforces Separation of Duties against Performers, Completer,
        Investigation authors, manual Deviation openers, Deviation submitters, and Witnesses."""
        if not who.may_approve:
            raise HTTPException(403, "approving a Qualification Report needs the approving role")
        try:
            with transaction(database()) as session:
                comp, exports = reports.approve_qualification_report(
                    session,
                    actor_of(who),
                    execution_id,
                    conclusion_note=body.conclusion_note,
                    next_requalification_date=body.next_requalification_date,
                )
                return _qual_report_view(comp, exports)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e
        except reports.Refused as e:
            raise HTTPException(422, str(e)) from e

    @router.get(
        "/executions/{execution_id}/qualification-reports/{export_id}/pdf",
        operation_id="downloadQualificationReportPdf",
        response_class=Response,
        responses={200: {"content": {"application/pdf": {}}}},
    )
    def download_qualification_report_pdf(
        execution_id: int,
        export_id: int,
        who: Annotated[Principal, Depends(principal)],
    ) -> Response:
        """Re-renders and downloads a stored Qualification Report PDF (zero DB writes)."""
        try:
            with transaction(database()) as session:
                pdf_bytes, rev = reports.render_stored_qualification_pdf(
                    session, execution_id, export_id
                )
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'inline; filename="qualification-report-{execution_id}-rev{rev}.pdf"'
                )
            },
        )

    return router
