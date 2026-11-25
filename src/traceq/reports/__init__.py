"""Typst PDF report rendering for TraceQ (Step 6, #319).

Isolated from ``traceq_dataset``, ``traceq_eval``, and database modules (ADR 0008).
"""

from traceq.reports.pre_review import (
    TEMPLATE_VERSION,
    TYPST_VERSION,
    PreReviewReportSnapshot,
    ReportDocument,
    ReportDroppedClaim,
    ReportFinding,
    ReportKindSummary,
    ReportMissingDocument,
    ReportRoundDiff,
    ReportUrsCompleteness,
    render_pre_review_pdf,
    snapshot_hash,
)
from traceq.reports.qualification import (
    QUALIFICATION_APPROVAL_NOTE,
    QUALIFICATION_TEMPLATE_VERSION,
    QUALIFICATION_TEMPLATE_VERSION_V1,
    QualificationCounts,
    QualificationReportDeviation,
    QualificationReportRow,
    QualificationReportSnapshot,
    QualificationReportSnapshotV1,
    SignatureSnapshotClaim,
    TechnicalConclusion,
    parse_qualification_snapshot,
    qualification_snapshot_hash,
    render_qualification_pdf,
)

__all__ = [
    "QUALIFICATION_APPROVAL_NOTE",
    "QUALIFICATION_TEMPLATE_VERSION",
    "QUALIFICATION_TEMPLATE_VERSION_V1",
    "TEMPLATE_VERSION",
    "TYPST_VERSION",
    "PreReviewReportSnapshot",
    "QualificationCounts",
    "QualificationReportDeviation",
    "QualificationReportRow",
    "QualificationReportSnapshot",
    "QualificationReportSnapshotV1",
    "ReportDocument",
    "ReportDroppedClaim",
    "ReportFinding",
    "ReportKindSummary",
    "ReportMissingDocument",
    "ReportRoundDiff",
    "ReportUrsCompleteness",
    "SignatureSnapshotClaim",
    "TechnicalConclusion",
    "parse_qualification_snapshot",
    "qualification_snapshot_hash",
    "render_pre_review_pdf",
    "render_qualification_pdf",
    "snapshot_hash",
]
