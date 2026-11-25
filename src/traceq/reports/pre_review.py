"""Pre-Review Report snapshot schema and deterministic Typst PDF renderer."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import typst
from pydantic import BaseModel, ConfigDict

TEMPLATE_VERSION = "1.0.0"
TYPST_VERSION: str = version("typst")
_TEMPLATE_PATH = Path(__file__).parent / "pre_review_report.typ"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportDocument(_Frozen):
    doc_id: str
    rev: int
    doc_type: str | None = None
    source: str
    sha256: str


class ReportKindSummary(_Frozen):
    total: int
    decided: int
    accepted: int
    edited: int
    rejected: int
    undecided: int
    changed: int


class ReportFinding(_Frozen):
    position: int
    finding_type: str
    doc: str | None = None
    detail: str
    citations: tuple[str, ...] = ()
    state: str
    decision: str | None = None
    reason: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


class ReportMissingDocument(_Frozen):
    doc_id: str
    doc_type: str
    stage: str
    citation: str


class ReportDroppedClaim(_Frozen):
    claim: str
    id: str
    reason: str


class ReportUrsCompleteness(_Frozen):
    doc: str
    rev: int
    numbers: str
    found: int
    missed_count: int
    unquoted_count: int


class ReportRoundDiff(_Frozen):
    previous_round_number: int
    previous_run_id: str
    documents_added: tuple[str, ...] = ()
    documents_revised: tuple[str, ...] = ()
    documents_unchanged: tuple[str, ...] = ()
    documents_removed: tuple[str, ...] = ()
    findings_resolved: int
    findings_persisted: int
    findings_new: int
    decisions_carried_forward: int
    decisions_changed: int
    decisions_undecided: int


class PreReviewReportSnapshot(_Frozen):
    generated_at: datetime
    equipment: str
    run_id: str
    round_number: int
    round_status: str
    documents: tuple[ReportDocument, ...] = ()
    coverage: ReportKindSummary
    findings_summary: ReportKindSummary
    check_findings: tuple[ReportFinding, ...] = ()
    ai_findings: tuple[ReportFinding, ...] = ()
    draft_findings: tuple[ReportFinding, ...] = ()
    missing_documents: tuple[ReportMissingDocument, ...] = ()
    dropped_claims: tuple[ReportDroppedClaim, ...] = ()
    completeness: tuple[ReportUrsCompleteness, ...] = ()
    round_diff: ReportRoundDiff | None = None


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def snapshot_hash(snapshot: PreReviewReportSnapshot) -> str:
    """Returns the SHA-256 hex digest of the canonical JSON of ``snapshot``."""
    raw = _canonical_json(snapshot.model_dump(mode="json")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def render_pre_review_pdf(snapshot: PreReviewReportSnapshot) -> bytes:
    """Compiles the Indonesian Pre-Review Report PDF deterministically from ``snapshot``.

    Uses Typst built-in fonts only (``ignore_system_fonts=True``) and pins ``timestamp`` to
    ``snapshot.generated_at`` so re-rendering the same snapshot yields byte-identical PDFs.
    Raises ``RuntimeError`` if Typst emits any compiler warning.
    """
    payload = _canonical_json(snapshot.model_dump(mode="json"))
    ts = snapshot.generated_at
    ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    pdf_bytes, warnings = typst.compile_with_warnings(
        _TEMPLATE_PATH,
        ignore_system_fonts=True,
        sys_inputs={"snapshot": payload},
        timestamp=ts,
    )
    if warnings:
        messages = "; ".join(str(w) for w in warnings)
        raise RuntimeError(f"Typst emitted warnings during report compilation: {messages}")
    return pdf_bytes
