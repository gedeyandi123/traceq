"""Qualification Report snapshot schema and deterministic Typst PDF renderer (Step 7, #326)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import typst
from pydantic import BaseModel, ConfigDict

QUALIFICATION_TEMPLATE_VERSION = "1.0.0"
QUALIFICATION_APPROVAL_NOTE = "a recorded status, not an Electronic Signature (ADR 0007 phase 2)"
_TEMPLATE_PATH = Path(__file__).parent / "qualification_report.typ"

type TechnicalConclusion = Literal["qualified", "qualified_with_deviations", "not_qualified"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QualificationCounts(_Frozen):
    iq_total: int
    iq_passed: int
    iq_failed: int
    oq_total: int
    oq_passed: int
    oq_failed: int
    unsplit_total: int
    unsplit_passed: int
    unsplit_failed: int
    vendor_reference_count: int
    total_rows: int
    total_deviations: int


class QualificationReportRow(_Frozen):
    requirement: str
    text: str
    kind: Literal["vendor_reference", "test_step"]
    stage_label: str
    witness_required: bool = False
    latest_verdict: str | None = None
    attempt_count: int = 0
    witness_names: tuple[str, ...] = ()


class QualificationReportDeviation(_Frozen):
    deviation_number: int
    requirement: str | None = None
    cause: str
    deviation_class: str | None = None
    status: str
    description: str


class QualificationReportSnapshot(_Frozen):
    generated_at: datetime
    equipment: str
    run_id: str
    protocol_id: int
    execution_id: int
    revision_number: int
    protocol_submission_hash: str
    execution_copy_hash: str
    completed_at: datetime
    completer_name: str
    approver_name: str
    approver_subject: str
    approver_issuer: str
    approval_note: str
    technical_conclusion: TechnicalConclusion
    conclusion_note: str | None = None
    next_requalification_date: date | None = None
    counts: QualificationCounts
    rows: tuple[QualificationReportRow, ...] = ()
    deviations: tuple[QualificationReportDeviation, ...] = ()


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def qualification_snapshot_hash(snapshot: QualificationReportSnapshot) -> str:
    """Returns the SHA-256 hex digest of the canonical JSON of ``snapshot``."""
    raw = _canonical_json(snapshot.model_dump(mode="json")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def render_qualification_pdf(snapshot: QualificationReportSnapshot) -> bytes:
    """Compiles the Indonesian Qualification Report PDF deterministically from ``snapshot``.

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
        raise RuntimeError(
            f"Typst emitted warnings during qualification report compilation: {messages}"
        )
    return pdf_bytes
