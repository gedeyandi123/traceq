"""Unit tests for the Indonesian Typst Pre-Review Report renderer (Step 6, #319)."""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime

import pypdfium2 as pdfium

from traceq.reports import (
    TEMPLATE_VERSION,
    TEMPLATE_VERSION_V1,
    TYPST_VERSION,
    PreReviewReportSnapshot,
    PreReviewReportSnapshotV2,
    ReportDocument,
    ReportDroppedClaim,
    ReportFinding,
    ReportFindingV2,
    ReportKindSummary,
    ReportMissingDocument,
    ReportRoundDiff,
    ReportRoundDiffV2,
    ReportUrsCompleteness,
    render_pre_review_pdf,
    snapshot_hash,
)


def _sample_snapshot() -> PreReviewReportSnapshot:
    return PreReviewReportSnapshot(
        generated_at=datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC),
        equipment="TP-201",
        run_id="20261113T090000Z-f1a2b3",
        round_number=2,
        round_status="open",
        documents=(
            ReportDocument(
                doc_id="URS-TP201",
                rev=1,
                doc_type="URS",
                source="corpus",
                sha256="a" * 64,
            ),
            ReportDocument(
                doc_id="DRAFT-TP201",
                rev=1,
                doc_type="protocol_draft",
                source="review_package_draft",
                sha256="b" * 64,
            ),
        ),
        coverage=ReportKindSummary(
            total=10, decided=8, accepted=6, edited=2, rejected=0, undecided=1, changed=1
        ),
        findings_summary=ReportKindSummary(
            total=3, decided=2, accepted=1, edited=0, rejected=1, undecided=1, changed=0
        ),
        check_findings=(
            ReportFinding(
                position=0,
                finding_type="missing_tolerance",
                doc="URS-TP201",
                detail="Toleransi tidak dicantumkan pada dokumen.",
                citations=("URS-TP201 rev 1 p.2",),
                state="decided",
                decision="accepted",
                decided_by="Ayu",
                decided_at=datetime(2026, 11, 25, 11, 30, 0, tzinfo=UTC),
            ),
        ),
        ai_findings=(
            ReportFinding(
                position=0,
                finding_type="contradiction",
                detail="Nilai kecepatan berbeda antara URS dan FAT.",
                citations=("URS-TP201 rev 1 p.3", "FAT-TP201 rev 0 p.5"),
                state="decided",
                decision="rejected",
                reason="FAT menguji rentang tambahan sesuai SOP.",
                decided_by="Ayu",
                decided_at=datetime(2026, 11, 25, 11, 35, 0, tzinfo=UTC),
            ),
        ),
        draft_findings=(
            ReportFinding(
                position=0,
                finding_type="limit_mismatch",
                doc="DRAFT-TP201",
                detail="Batas atas pada draf melebihi batas URS.",
                citations=("DRAFT-TP201 rev 1 p.4",),
                state="undecided",
            ),
        ),
        missing_documents=(
            ReportMissingDocument(
                doc_id="SAT-TP201",
                doc_type="SAT",
                stage="SAT",
                citation="VMP-01 rev 0 p.4",
            ),
        ),
        dropped_claims=(
            ReportDroppedClaim(
                claim="value",
                id="URS-TP201-005",
                reason="quote not on page or value not in it",
            ),
        ),
        completeness=(
            ReportUrsCompleteness(
                doc="URS-TP201",
                rev=1,
                numbers="checked",
                found=10,
                missed_count=1,
                unquoted_count=2,
            ),
        ),
        round_diff=ReportRoundDiff(
            previous_round_number=1,
            previous_run_id="20261112T090000Z-000001",
            documents_added=("DRAFT-TP201",),
            documents_revised=("URS-TP201",),
            documents_unchanged=(),
            documents_removed=(),
            findings_resolved=1,
            findings_persisted=1,
            findings_new=1,
            decisions_carried_forward=1,
            decisions_changed=1,
            decisions_undecided=1,
        ),
    )


def test_render_pre_review_pdf_is_deterministic_and_warning_free() -> None:
    snap = _sample_snapshot()
    pdf_a = render_pre_review_pdf(snap)
    pdf_b = render_pre_review_pdf(snap)
    assert pdf_a.startswith(b"%PDF-")
    assert pdf_a == pdf_b
    assert len(snapshot_hash(snap)) == 64
    assert TEMPLATE_VERSION
    assert TYPST_VERSION


def test_snapshot_hash_changes_when_content_changes() -> None:
    snap_a = _sample_snapshot()
    snap_b = snap_a.model_copy(update={"round_status": "ready_for_protocol"})
    assert snapshot_hash(snap_a) != snapshot_hash(snap_b)


def _text(pdf: bytes) -> str:
    doc = pdfium.PdfDocument(io.BytesIO(pdf))
    pages = [doc[i].get_textpage().get_text_bounded() for i in range(len(doc))]
    return " ".join(" ".join(pages).split())


def _v2_snapshot() -> PreReviewReportSnapshotV2:
    v1 = _sample_snapshot().model_dump()
    findings = tuple(
        ReportFindingV2(
            position=i,
            finding_type=t,
            doc="OQ-TP201",
            detail=f"detail {t}",
            state="undecided",
            label="not reviewed by a practitioner"
            if t in {"ac_outside_documented_capability", "unit_error", "outdated_reference"}
            else None,
            change=c,
        )
        for i, (t, c) in enumerate(
            [
                ("ac_deviates_from_urs", "resolved"),
                ("requirement_not_tested", "persisted"),
                ("ac_outside_documented_capability", "persisted_changed"),
                ("unit_error", "new"),
                ("outdated_reference", "new"),
            ]
        )
    )
    v1.update(
        draft_findings=findings,
        round_diff=ReportRoundDiffV2(
            **{**_sample_snapshot().round_diff.model_dump(), "findings_persisted_changed": 1}  # type: ignore[union-attr]
        ),
    )
    return PreReviewReportSnapshotV2.model_validate(v1)


def test_template_v2_is_current_and_v1_stays_available() -> None:
    assert TEMPLATE_VERSION == "2.0.0" and TEMPLATE_VERSION_V1 == "1.0.0"
    snap = _v2_snapshot()
    assert render_pre_review_pdf(snap) == render_pre_review_pdf(snap, template_version="2.0.0")


def test_template_v2_prints_the_five_types_the_labels_and_the_round_states() -> None:
    text = _text(render_pre_review_pdf(_v2_snapshot()))
    # Once in the notice at the top, then on each of the three findings of the new types.
    assert text.count("not reviewed by a practitioner") == 1 + 3
    assert "dev only" in text
    assert "\\n" not in text  # no literal escape printed in the notice
    for state in ("resolved", "persisted", "persisted-but-changed", "new"):
        # A whole word: "persisted" is not met by "persisted-but-changed".
        assert re.search(rf"(?<![\w-]){re.escape(state)}(?![\w-])", text), state
    for kind in (
        "ac_deviates_from_urs",
        "requirement_not_tested",
        "ac_outside_documented_capability",
        "unit_error",
        "outdated_reference",
    ):
        assert kind in text
    assert not re.search(r"(?<!non-)\bcompliant\b|\bsaved\b|\bhemat\b", text, re.IGNORECASE)


def test_template_v1_does_not_print_the_new_labels() -> None:
    text = _text(render_pre_review_pdf(_sample_snapshot()))
    assert "not reviewed by a practitioner" not in text


def test_each_point_of_the_notice_is_on_its_own_line_of_the_template() -> None:
    from traceq.reports import pre_review

    source = pre_review._TEMPLATE_PATHS[TEMPLATE_VERSION].read_text(encoding="utf-8")
    points = [ln for ln in source.splitlines() if re.match(r"\s+\d\. \*", ln)]
    assert [ln.split(".")[0].strip() for ln in points] == ["1", "2", "3", "4"]
    assert all(len(re.findall(r"\s\d\. \*", ln)) == 1 for ln in points)
    assert "outdated_reference yang membawa label" in source


def test_the_notice_does_not_claim_a_label_on_every_finding_of_the_three_types() -> None:
    from traceq.reports import pre_review

    source = pre_review._TEMPLATE_PATHS[TEMPLATE_VERSION].read_text(encoding="utf-8")
    assert "Tiga jenis temuan draf terbaru" not in source
