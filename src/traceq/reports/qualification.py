"""Qualification Report snapshot schema and deterministic Typst PDF renderer (Step 7, #326)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import typst
from pydantic import BaseModel, ConfigDict

QUALIFICATION_TEMPLATE_VERSION_V1 = "1.0.0"
QUALIFICATION_TEMPLATE_VERSION = "2.0.0"
QUALIFICATION_APPROVAL_NOTE = "a recorded status, not an Electronic Signature"
_TEMPLATE_V1_PATH = Path(__file__).parent / "qualification_report_v1.typ"
_TEMPLATE_V2_PATH = Path(__file__).parent / "qualification_report_v2.typ"
_TEMPLATE_PATHS = {
    QUALIFICATION_TEMPLATE_VERSION_V1: _TEMPLATE_V1_PATH,
    QUALIFICATION_TEMPLATE_VERSION: _TEMPLATE_V2_PATH,
}
QUALIFICATION_TEMPLATE_VERSIONS: tuple[str, ...] = tuple(_TEMPLATE_PATHS)

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


class SignatureSnapshotClaim(_Frozen):
    """Electronic Signature claims embedded in a v2 Qualification Report snapshot (no jti)."""

    record_type: Literal["qualification_report"]
    signature_meaning: Literal["approved"]
    content_hash: str
    hash_scheme_version: int
    signer_subject: str
    signer_issuer: str
    signer_name: str
    auth_time: datetime
    signed_at: datetime
    is_demo: bool
    label: str


class QualificationReportSnapshotV1(_Frozen):
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
    electronic_signature: SignatureSnapshotClaim | None = None


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def qualification_snapshot_hash(
    snapshot: QualificationReportSnapshot | QualificationReportSnapshotV1,
) -> str:
    """Returns the SHA-256 hex digest of the canonical JSON of ``snapshot``."""
    raw = _canonical_json(snapshot.model_dump(mode="json")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_qualification_snapshot(
    data: Any, template_version: str = QUALIFICATION_TEMPLATE_VERSION
) -> QualificationReportSnapshot | QualificationReportSnapshotV1:
    """Deserialize a stored Qualification Report snapshot according to ``template_version``."""
    if template_version == QUALIFICATION_TEMPLATE_VERSION_V1:
        return QualificationReportSnapshotV1.model_validate(data)
    return QualificationReportSnapshot.model_validate(data)


def render_qualification_pdf(
    snapshot: QualificationReportSnapshot | QualificationReportSnapshotV1,
    *,
    template_version: str | None = None,
) -> bytes:
    """Compiles the Indonesian Qualification Report PDF deterministically from ``snapshot``.

    Dispatches to v1 or v2 template according to ``template_version`` (defaults to v1 for
    ``QualificationReportSnapshotV1``, otherwise ``QUALIFICATION_TEMPLATE_VERSION``).
    Uses Typst built-in fonts only (``ignore_system_fonts=True``) and pins ``timestamp`` to
    ``snapshot.generated_at`` so re-rendering the same snapshot yields byte-identical PDFs.
    Raises ``RuntimeError`` if Typst emits any compiler warning.
    """
    version = template_version or (
        QUALIFICATION_TEMPLATE_VERSION_V1
        if isinstance(snapshot, QualificationReportSnapshotV1)
        else QUALIFICATION_TEMPLATE_VERSION
    )
    template_path = _TEMPLATE_PATHS.get(version)
    if template_path is None:
        raise ValueError(f"unsupported qualification report template_version: {version!r}")
    payload = _canonical_json(snapshot.model_dump(mode="json"))
    ts = snapshot.generated_at
    ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    pdf_bytes, warnings = typst.compile_with_warnings(
        template_path,
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
