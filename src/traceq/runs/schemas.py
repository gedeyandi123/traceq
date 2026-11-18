"""The shape of ``matrix.json``, ``findings.json``, ``protocol_draft.json`` and of the read-only
API over run folders.

The pipeline writes both files from these models and the API serves them, so the OpenAPI
schema, and the TypeScript client generated from it (ADR 0003), describe exactly what a
run folder holds.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from traceq.review.ai_findings import AiType
from traceq.review.draft_rules import DraftType
from traceq.review.facts import SiteRule
from traceq.review.printed import Limit, Tolerance
from traceq.review.rules import CheckType
from traceq.traceability.coverage import CoverageClass, Result, Stage
from traceq.traceability.values import Number, Text, Value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Cite(_Model):
    """Where a claim comes from: document, revision, page and the verbatim quote."""

    doc: str
    rev: int
    page: int
    quote: str


class AmbiguousValue(_Model):
    """An observation that reads two ways: ask for confirmation, never guess."""

    type: Literal["ambiguous"] = "ambiguous"
    readings: tuple[float, ...]


ObservedValue = Annotated[Value | AmbiguousValue, Field(discriminator="type")]


class EvidenceStep(_Model):
    """A vendor FAT/SAT step linked to a requirement, with its verdict."""

    doc: str
    rev: int
    stage: Stage
    step: str
    test: str
    acceptance: str
    observed: str
    observed_value: ObservedValue | None
    result: Result | None
    failure: str | None
    """The first failing condition, or ``None`` when the step meets conditions 1-3."""
    citation: Cite


class DesignRow(_Model):
    """A datasheet or certificate value compared with the URS value."""

    doc: str
    rev: int
    name: str
    printed: str
    value: Value | None
    citation: Cite


class MatrixRow(_Model):
    """One requirement: its text and value, Coverage class and reason, and Evidence."""

    id: str
    text: str
    source: Cite
    value: Value | None
    value_citation: Cite | None
    coverage: CoverageClass | None
    reason: str | None
    site_only: bool | None
    transport_sensitive: bool | None
    evidence: tuple[EvidenceStep, ...] = ()
    design: tuple[DesignRow, ...] = ()


class NotRead(_Model):
    """A vendor document the run could not read."""

    doc_id: str
    rev: int
    format: str


class Matrix(_Model):
    """The traceability matrix of a run."""

    requirements: tuple[MatrixRow, ...]
    not_read: tuple[NotRead, ...] = ()


class RunPackage(_Model):
    """The Review Package a run reviews and the Protocol Draft it read."""

    package: str
    version: str
    doc_id: str
    rev: int


class RunSummary(_Model):
    """What identifies a run: its id, Equipment, model and mode."""

    run_id: str
    created: str
    equipment: str
    model: str
    mode: Literal["replay", "live"]
    pipeline_version: str
    review_package: RunPackage | None = None
    """For a Review Package run: the package and its Protocol Draft; ``null`` otherwise."""


class Source(_Model):
    """A document and revision an AI Finding cites."""

    doc: str
    rev: int


class CheckFinding(_Model):
    """A Pre-review finding of a deterministic rule: no model involved."""

    layer: Literal["check"]
    type: CheckType
    doc: str
    detail: str
    citations: tuple[Cite, ...]
    rule: Cite | None
    """The SOP sentence that sets the rule, for a site rule."""


class AiFinding(_Model):
    """A Pre-review finding of the LLM, every citation verified; advisory (ADR 0002)."""

    layer: Literal["ai"]
    type: AiType
    detail: str
    citations: tuple[Cite, ...]
    sources: tuple[Source, ...]
    model: str
    prompt: str
    """Hash of the prompt that produced it."""
    created: str
    reviewer_action: Literal["pending"]
    """``pending`` until a write feature lets a human accept, edit or reject it."""


DocStage = Literal["design", "FAT", "SAT", "IQ", "OQ"]


class RequiredDocument(_Model):
    """A document the VMP requires for the Equipment, with the annex row cited."""

    doc_id: str
    type: str
    stage: DocStage
    in_corpus: bool
    citation: Cite


class MissingDocument(_Model):
    """A document the VMP requires that the corpus lacks."""

    doc_id: str
    type: str
    stage: DocStage
    citation: Cite


class SiteRuleCite(_Model):
    """A site rule read from the SOP, with the sentence that sets it."""

    rule: SiteRule
    citation: Cite


class GoverningDocument(_Model):
    """A VMP or SOP the run read its required documents and site rules from."""

    doc_id: str
    rev: int


class Findings(_Model):
    """The Pre-review of a run: Check Findings and AI Findings kept apart, and the
    documents the VMP requires that the corpus lacks."""

    check_findings: tuple[CheckFinding, ...]
    ai_findings: tuple[AiFinding, ...]
    required_documents: tuple[RequiredDocument, ...]
    missing_documents: tuple[MissingDocument, ...]
    site_rules: tuple[SiteRuleCite, ...]
    governing_documents: tuple[GoverningDocument, ...]


class DroppedClaim(_Model):
    """A claim the citation check dropped, with its reason in plain text."""

    claim: str
    """What kind of claim: a requirement, a value, a test step, a finding."""
    id: str
    """What it was about: a requirement id, a step, a document and page."""
    reason: str


class MissedNumber(_Model):
    """A printed requirement number that did not become a kept requirement."""

    number: str
    page: int
    """The first page it is printed on."""


class UnquotedText(_Model):
    """URS text that no kept requirement quotes: adjacent lines merged."""

    page: int
    text: str


class UrsCompleteness(_Model):
    """The completeness check of one URS the run read, built without an LLM."""

    doc: str
    rev: int
    numbers: Literal["checked", "not_applicable"]
    """``not_applicable`` when the model returned no printed requirement number for it."""
    found: int
    """Distinct printed numbers of the learned shape on its pages."""
    missed: tuple[MissedNumber, ...]
    unquoted: tuple[UnquotedText, ...]


class Completeness(_Model):
    """The URS completeness check of a run: printed numbers that did not become a
    requirement, and URS text no kept requirement quotes."""

    urs: tuple[UrsCompleteness, ...]


# --- protocol_draft.json (spec #196, "Outputs") ---------------------------------------

PrintedRead = Annotated[
    Limit | Number | Tolerance | Text | AmbiguousValue, Field(discriminator="type")
]
"""A limit as code read it from the print: a one- or two-sided limit (``range``, either bound
may be strict), a single number, a nominal value with a tolerance, text, or a number that
reads two ways (``ambiguous``)."""


class DraftDocument(_Model):
    """The Protocol Draft under review: document, revision and the SHA-256 of its bytes."""

    doc_id: str
    rev: int
    sha256: str


class DraftAcceptance(_Model):
    """A Test Step's Acceptance Criterion as printed, the value code read from it (none: a
    form the parser does not know) and the verified citation it was read from."""

    printed: str
    value: PrintedRead | None
    citation: Cite


class VendorFactCite(_Model):
    """A vendor step's observation or a design value, as printed, with its citation."""

    name: str
    printed: str
    citation: Cite


class DraftComparator(_Model):
    """The vendor facts of one document a requirement's matrix row holds: shown only, never
    a finding."""

    doc: str
    rev: int
    kind: Literal["FAT", "SAT", "design"]
    facts: tuple[VendorFactCite, ...]


class DraftTraced(_Model):
    """A Test Step's AC compared with one requirement the traceability table traces it to."""

    requirement: str
    urs_limit: PrintedRead | None
    """The URS limit read from the requirement's verified URS citation."""
    citation: Cite | None
    not_parsed: str | None
    """Why no URS limit was read."""
    compared: bool
    deviates: bool
    not_compared: str | None
    """Why the AC was not compared with this requirement."""
    comparators: tuple[DraftComparator, ...]
    """Empty: none."""


class DraftTestStep(_Model):
    """A Test Step of the draft, in draft order, as read and compared."""

    id: str
    requirements: tuple[str, ...]
    """The requirement ids the step's own header prints."""
    acceptance: DraftAcceptance
    traced: tuple[DraftTraced, ...]
    compared: bool
    not_compared: str | None
    """Why the step was not compared with any requirement."""


class DraftTraceRow(_Model):
    """A row of the draft's traceability table: a requirement and its Test Step ids."""

    requirement: str
    test_steps: tuple[str, ...]
    citation: Cite


class DraftCheckFinding(_Model):
    """A Check Finding (layer Rule) on the draft, with the values it compared, as parsed. It
    is on a Test Step (``test_step``) or, for ``requirement_not_tested``, on a traceability
    row (``row``, the row's requirement id)."""

    type: DraftType
    layer: Literal["rule"]
    test_step: str | None = None
    row: str | None = None
    requirement: str
    detail: str
    ac: PrintedRead | None
    urs_limit: PrintedRead | None
    citations: tuple[Cite, ...]


class ProtocolDraft(_Model):
    """The Protocol Draft of a Review Package run: its Test Steps in draft order, its
    traceability rows and its findings."""

    package: str
    document: DraftDocument
    test_steps: tuple[DraftTestStep, ...]
    trace_rows: tuple[DraftTraceRow, ...]
    findings: tuple[DraftCheckFinding, ...]
