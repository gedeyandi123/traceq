"""Fast unit tests for Step 7: Qualification conclusion/counts, witness blocker,
pre-0017 backward compatibility, Typst PDF determinism, and demo_seed._needs_witness."""

from __future__ import annotations

from datetime import UTC, datetime

from traceq.assembly.submission import (
    Author,
    FrozenCoverage,
    FrozenDecision,
    FrozenRow,
    FrozenTestStep,
    ProtocolCopy,
)
from traceq.execution.completion import (
    Attempt,
    AttemptVersion,
    ExecutionCopy,
    FrozenAttempt,
    FrozenAttemptVersion,
    FrozenDeviation,
    FrozenExecutionRow,
    FrozenExecutionTestStep,
    InstrumentInput,
    WitnessConfirmation,
    _format_blockers,
    compute_blockers,
)
from traceq.execution.reports import compute_conclusion, compute_counts
from traceq.execution.results import NumberResultValue, PresentResultValue
from traceq.proposals.keys import digest
from traceq.reports import (
    QUALIFICATION_APPROVAL_NOTE,
    QualificationReportDeviation,
    QualificationReportRow,
    QualificationReportSnapshot,
    render_qualification_pdf,
)
from traceq.runs.schemas import Cite, EvidenceStep
from traceq.traceability.values import Present, Range

_T0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
_AUTHOR = Author(subject="ayu", issuer="https://issuer.local", name="Ayu")
_PERFORMER = Author(subject="budi", issuer="https://issuer.local", name="Budi")
_WITNESS = Author(subject="eko", issuer="https://issuer.local", name="Eko")


def _exec_row(
    req: str,
    *,
    kind: str = "test_step",
    stage: str | None = None,
    witness_required: bool = False,
    verdict: str = "pass",
) -> FrozenExecutionRow:
    if kind == "vendor_reference":
        cite = Cite(doc="FAT-1", rev=0, page=2, quote="Step 1")
        return FrozenExecutionRow(
            requirement=req,
            text=f"Requirement {req}",
            source=Cite(doc="URS-1", rev=0, page=1, quote=f"Req {req}"),
            kind="vendor_reference",
            evidence=(
                EvidenceStep(
                    doc="FAT-1",
                    rev=0,
                    stage="FAT",
                    step="1",
                    test="Check",
                    acceptance="Pass",
                    observed="Pass",
                    observed_value=None,
                    result="pass",
                    failure=None,
                    citation=cite,
                ),
            ),
            test_step=None,
            attempts=(),
        )
    return FrozenExecutionRow(
        requirement=req,
        text=f"Requirement {req}",
        source=Cite(doc="URS-1", rev=0, page=1, quote=f"Req {req}"),
        kind="test_step",
        evidence=(),
        test_step=FrozenExecutionTestStep(
            origin="written",
            description="Check temp",
            method="Measure",
            instrument=None,
            acceptance=Range(type="range", min=2.0, max=8.0, unit="C"),
            stage=stage,  # type: ignore[arg-type]
            witness_required=witness_required,
        ),
        attempts=(
            FrozenAttempt(
                id=1,
                attempt_number=1,
                performer=_PERFORMER,
                recorded_at=_T0,
                versions=(
                    FrozenAttemptVersion(
                        id=1,
                        version=1,
                        outcome_kind="value",
                        not_performable_reason=None,
                        value=NumberResultValue(type="number", value=5.0),
                        observation=None,
                        instruments=(
                            InstrumentInput(identifier="CAL-1", calibration_due_date=_T0.date()),
                        ),
                        no_calibrated_instrument_reason=None,
                        evidence_references=("LOG-1",),
                        verdict=verdict,  # type: ignore[arg-type]
                        version_hash="a" * 64,
                        performer=_PERFORMER,
                        recorded_at=_T0,
                        reason_for_change=None,
                        witness_confirmations=(),
                    ),
                ),
            ),
        ),
    )


def _exec_copy(
    rows: tuple[FrozenExecutionRow, ...],
    deviations: tuple[FrozenDeviation, ...] = (),
) -> ExecutionCopy:
    return ExecutionCopy(
        execution_id=10,
        protocol_id=5,
        equipment="TP-201",
        run_id="run-1",
        submission_event_id=2,
        submission_hash="b" * 64,
        completed_event_id=9,
        completed_at=_T0,
        completer=_PERFORMER,
        rows=rows,
        deviations=deviations,
    )


def test_compute_conclusion_and_counts() -> None:
    dev = FrozenDeviation(
        id=1,
        deviation_number=1,
        description="Temp excursion",
        deviation_class="minor",
        requirement="R-02",
        attempt_id=1,
        cause="failed",
        status="closed",
        opener=_PERFORMER,
        opened_at=_T0,
        investigations=(),
        events=(),
    )

    # All pass, no deviations -> qualified
    rows = (
        _exec_row("R-01", stage="IQ", verdict="pass"),
        _exec_row("R-02", stage="OQ", verdict="pass"),
        _exec_row("R-03", stage=None, verdict="pass"),
        _exec_row("R-04", kind="vendor_reference"),
    )
    copy_clean = _exec_copy(rows)
    assert compute_conclusion(copy_clean) == "qualified"
    counts = compute_counts(copy_clean)
    assert counts.iq_total == 1 and counts.iq_passed == 1 and counts.iq_failed == 0
    assert counts.oq_total == 1 and counts.oq_passed == 1 and counts.oq_failed == 0
    assert counts.unsplit_total == 1 and counts.unsplit_passed == 1 and counts.unsplit_failed == 0
    assert counts.vendor_reference_count == 1
    assert counts.total_rows == 4
    assert counts.total_deviations == 0

    # All pass, with deviation -> qualified_with_deviations
    copy_with_dev = _exec_copy(rows, deviations=(dev,))
    assert compute_conclusion(copy_with_dev) == "qualified_with_deviations"
    assert compute_counts(copy_with_dev).total_deviations == 1

    # Any test_step fail -> not_qualified
    copy_fail = _exec_copy(
        (
            _exec_row("R-01", stage="IQ", verdict="pass"),
            _exec_row("R-02", stage="OQ", verdict="fail"),
        ),
        deviations=(dev,),
    )
    assert compute_conclusion(copy_fail) == "not_qualified"
    assert compute_counts(copy_fail).oq_failed == 1

    # Guard empty test_step rows
    copy_empty = _exec_copy((_exec_row("R-04", kind="vendor_reference"),))
    assert compute_conclusion(copy_empty) == "qualified"


def test_witness_blocker_and_empty_attempts_guard() -> None:
    from traceq import audit

    actor_p = audit.Actor(subject="budi", issuer="https://issuer.local", name="Budi")
    actor_w = audit.Actor(subject="eko", issuer="https://issuer.local", name="Eko")

    proto_copy = ProtocolCopy(
        protocol_id=1,
        equipment="TP-201",
        run_id="run-1",
        preparer=_AUTHOR,
        rows=(
            FrozenRow(
                requirement="R-01",
                text="Req 1",
                source=Cite(doc="URS-1", rev=0, page=1, quote="Req 1"),
                coverage=FrozenCoverage(
                    coverage_class="partial",
                    decision=FrozenDecision(
                        id=1,
                        decision="accepted",
                        coverage=None,
                        reason=None,
                        author=_AUTHOR,
                        at=_T0,
                    ),
                ),
                kind="test_step",
                evidence=(),
                test_step=FrozenTestStep(
                    origin="written",
                    proposal_id=None,
                    version=1,
                    decision=None,
                    description="Check",
                    method="Observe",
                    instrument=None,
                    acceptance=Present(type="present"),
                    stage="OQ",
                    witness_required=True,
                ),
                drafts=(),
                written=(),
            ),
        ),
        urs=None,
    )

    # Empty attempts: in rows_without_result, NOT unconfirmed_witness_rows (no IndexError)
    b_empty = compute_blockers(proto_copy, {}, ())
    assert b_empty.blocked is True
    assert b_empty.rows_without_result.requirements == ("R-01",)
    assert b_empty.unconfirmed_witness_rows.count == 0

    # Attempt present, only voided witness -> blocked by unconfirmed_witness_rows
    ver_voided = AttemptVersion(
        id=1,
        at=_T0,
        attempt_id=1,
        version=1,
        outcome_kind="value",
        not_performable_reason=None,
        value=PresentResultValue(type="present", value=True),
        observation=None,
        instruments=(),
        no_calibrated_instrument_reason=None,
        evidence=(),
        verdict="pass",
        version_hash="c" * 64,
        reason_for_change=None,
        actor=actor_p,
        witness_confirmations=(
            WitnessConfirmation(
                id=1,
                at=_T0,
                version_id=1,
                version_hash="c" * 64,
                actor=actor_w,
                voided=True,
            ),
        ),
    )
    att_voided = Attempt(
        id=1,
        at=_T0,
        execution_id=1,
        requirement="R-01",
        attempt_number=1,
        actor=actor_p,
        versions=(ver_voided,),
    )
    b_voided = compute_blockers(proto_copy, {"R-01": (att_voided,)}, ())
    assert b_voided.blocked is True
    assert b_voided.unconfirmed_witness_rows.requirements == ("R-01",)
    assert "unconfirmed_witness_rows (1: R-01)" in _format_blockers(b_voided)

    # Active witness confirmation -> unblocked
    ver_active = AttemptVersion(
        id=1,
        at=_T0,
        attempt_id=1,
        version=1,
        outcome_kind="value",
        not_performable_reason=None,
        value=PresentResultValue(type="present", value=True),
        observation=None,
        instruments=(),
        no_calibrated_instrument_reason=None,
        evidence=(),
        verdict="pass",
        version_hash="c" * 64,
        reason_for_change=None,
        actor=actor_p,
        witness_confirmations=(
            WitnessConfirmation(
                id=2,
                at=_T0,
                version_id=1,
                version_hash="c" * 64,
                actor=actor_w,
                voided=False,
            ),
        ),
    )
    att_active = Attempt(
        id=1,
        at=_T0,
        execution_id=1,
        requirement="R-01",
        attempt_number=1,
        actor=actor_p,
        versions=(ver_active,),
    )
    b_ok = compute_blockers(proto_copy, {"R-01": (att_active,)}, ())
    assert b_ok.blocked is False
    assert b_ok.unconfirmed_witness_rows.count == 0


def test_pre_0017_frozen_copies_validate_and_preserve_raw_digest() -> None:
    raw_proto = {
        "protocol_id": 1,
        "equipment": "TP-201",
        "run_id": "run-old",
        "preparer": {"subject": "ayu", "issuer": "https://issuer.local", "name": "Ayu"},
        "rows": [
            {
                "requirement": "R-01",
                "text": "Old req",
                "source": {"doc": "URS-1", "rev": 0, "page": 1, "quote": "Old req"},
                "coverage": {
                    "coverage_class": "partial",
                    "decision": {
                        "id": 1,
                        "decision": "accepted",
                        "coverage": None,
                        "reason": None,
                        "author": {
                            "subject": "ayu",
                            "issuer": "https://issuer.local",
                            "name": "Ayu",
                        },
                        "at": "2026-06-01T12:00:00Z",
                    },
                },
                "kind": "test_step",
                "evidence": [],
                "test_step": {
                    "origin": "written",
                    "proposal_id": None,
                    "version": 1,
                    "decision": None,
                    "description": "Check",
                    "method": "Observe",
                    "instrument": None,
                    "acceptance": {"type": "present", "value": None},
                },
                "drafts": [],
                "written": [],
            }
        ],
        "urs": None,
    }
    raw_hash = digest(raw_proto)
    validated = ProtocolCopy.model_validate(raw_proto)
    assert validated.rows[0].step_attributes == ()
    assert validated.rows[0].test_step is not None
    assert validated.rows[0].test_step.stage is None
    assert validated.rows[0].test_step.witness_required is False
    assert digest(raw_proto) == raw_hash


def test_qualification_pdf_is_deterministic() -> None:
    copy = _exec_copy((_exec_row("R-01", stage="IQ", verdict="pass"),))
    snap = QualificationReportSnapshot(
        generated_at=_T0,
        equipment="TP-201",
        run_id="run-1",
        protocol_id=5,
        execution_id=10,
        revision_number=1,
        protocol_submission_hash="b" * 64,
        execution_copy_hash="d" * 64,
        completed_at=_T0,
        completer_name="Budi",
        approver_name="Dewi",
        approver_subject="dewi",
        approver_issuer="https://issuer.local",
        approval_note=QUALIFICATION_APPROVAL_NOTE,
        technical_conclusion="qualified",
        conclusion_note="All IQ/OQ checks passed.",
        next_requalification_date=None,
        counts=compute_counts(copy),
        rows=(
            QualificationReportRow(
                requirement="R-01",
                text="Requirement R-01",
                kind="test_step",
                stage_label="IQ",
                witness_required=False,
                latest_verdict="pass",
                attempt_count=1,
                witness_names=(),
            ),
        ),
        deviations=(
            QualificationReportDeviation(
                deviation_number=1,
                requirement="R-01",
                cause="manual",
                deviation_class="minor",
                status="closed",
                description="Note",
            ),
        ),
    )
    pdf1 = render_qualification_pdf(snap)
    pdf2 = render_qualification_pdf(snap)
    assert pdf1.startswith(b"%PDF-")
    assert pdf1 == pdf2


def test_demo_seed_needs_witness_checks_voided() -> None:
    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import demo_seed  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    assert demo_seed._needs_witness({"witness_confirmations": []}) is True
    assert demo_seed._needs_witness({"witness_confirmations": [{"voided": True}]}) is True
    assert demo_seed._needs_witness({"witness_confirmations": [{"voided": False}]}) is False
