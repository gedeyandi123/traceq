"""Pre-Review Report snapshot schema and deterministic Typst PDF renderer."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import typst
from pydantic import BaseModel, ConfigDict

TEMPLATE_VERSION = "1.0.0"
TYPST_VERSION: str = version("typst")
_TEMPLATE_PATHS = {TEMPLATE_VERSION: Path(__file__).parent / "pre_review_report_v1.typ"}
# A released template is frozen: stored exports re-render from it by their ``template_version``.
# A changed layout is a new ``pre_review_report_vN.typ`` and a new entry here, never an edit.
PRE_REVIEW_TEMPLATE_VERSIONS: tuple[str, ...] = tuple(_TEMPLATE_PATHS)


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


# What the bundled fonts (Libertinus Serif, DejaVu Sans Mono) draw: Latin, Greek and Cyrillic
# letters with their marks, general punctuation, sub- and superscripts, currency, letterlike
# symbols, number forms, arrows, mathematical operators and the Latin ligatures. Any other
# script (CJK, Arabic, emoji) has no glyph in them and would print as an empty box.
_TYPESET_RANGES = (
    (0x20, 0x24F),
    (0x250, 0x2FF),
    (0x300, 0x36F),
    (0x370, 0x52F),
    (0x1E00, 0x1EFF),
    (0x2010, 0x2027),
    (0x2030, 0x205E),
    (0x2070, 0x209F),
    (0x20A0, 0x20CF),
    (0x2100, 0x218F),
    (0x2190, 0x21FF),
    (0x2200, 0x22FF),
    (0xFB00, 0xFB06),
)
REPLACEMENT = "\N{REPLACEMENT CHARACTER}"


def typesettable(text: str) -> str:
    """``text`` as the report can print it: a character the bundled fonts have no glyph for
    becomes U+FFFD, a control or format character (also a lone surrogate) is dropped, a line
    break stays. The text a person typed or a model read is never trusted to be typesettable."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch in "\n\t":
            out.append(ch)
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"):
            continue
        elif any(lo <= code <= hi for lo, hi in _TYPESET_RANGES):
            out.append(ch)
        else:
            out.append(REPLACEMENT)
    return "".join(out)


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return typesettable(value)
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in cast(dict[str, Any], value).items()}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in cast(list[Any], value)]
    return value


def typesettable_snapshot(snapshot: PreReviewReportSnapshot) -> PreReviewReportSnapshot:
    """The snapshot with every text typesettable. Built before it is hashed and stored, so the
    hash covers the text the report prints; a snapshot stored before this holds its text as it
    was and is scrubbed only when rendered."""
    return PreReviewReportSnapshot.model_validate(_scrub(snapshot.model_dump(mode="python")))


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def snapshot_hash(snapshot: PreReviewReportSnapshot) -> str:
    """Returns the SHA-256 hex digest of the canonical JSON of ``snapshot``."""
    raw = _canonical_json(snapshot.model_dump(mode="json")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def render_pre_review_pdf(
    snapshot: PreReviewReportSnapshot, *, template_version: str = TEMPLATE_VERSION
) -> bytes:
    """Compiles the Indonesian Pre-Review Report PDF deterministically from ``snapshot``.

    Dispatches to the template of ``template_version`` (the current one by default).

    Uses Typst built-in fonts only (``ignore_system_fonts=True``) and pins ``timestamp`` to
    ``snapshot.generated_at`` so re-rendering the same snapshot yields byte-identical PDFs.
    Raises ``RuntimeError`` if Typst emits any compiler warning.
    """
    template_path = _TEMPLATE_PATHS.get(template_version)
    if template_path is None:
        raise ValueError(f"unsupported pre-review report template_version: {template_version!r}")
    payload = _canonical_json(_scrub(snapshot.model_dump(mode="json")))
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
        raise RuntimeError(f"Typst emitted warnings during report compilation: {messages}")
    return pdf_bytes
