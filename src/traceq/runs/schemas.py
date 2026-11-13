"""The shape of ``matrix.json``, ``findings.json`` and of the read-only API over run folders.

The pipeline writes both files from these models and the API serves them, so the OpenAPI
schema, and the TypeScript client generated from it (ADR 0003), describe exactly what a
run folder holds.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from traceq.review.ai_findings import AiType
from traceq.review.facts import SiteRule
from traceq.review.rules import CheckType
from traceq.traceability.coverage import CoverageClass, Result, Stage
from traceq.traceability.values import Value


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


class RunSummary(_Model):
    """What identifies a run: its id, Equipment, model and mode."""

    run_id: str
    created: str
    equipment: str
    model: str
    mode: Literal["replay", "live"]
    pipeline_version: str


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
