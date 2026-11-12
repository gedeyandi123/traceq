"""What a system under evaluation hands in: one JSON file per Equipment (design section 9).

A submission says, for each requirement, its value, its Coverage class and where that comes
from; it lists the defects found by Pre-review, the documents that should exist but do not,
and the drafted IQ/OQ Test Steps. Every claim about the corpus carries a citation: document,
revision, page and a verbatim quote (design section 9, "Citations"). Values use the same
normalised shapes as the answer key.

The schema is strict (unknown fields fail) so a system cannot drift from it silently. Limits
the scorer judges, such as the 200-character quote, are not schema errors: a long quote is
scored as an invalid citation, not a rejected submission.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traceq_dataset.schema import CoverageClass, DefectType

SUBMISSION_VERSION = 1


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Values (same shapes as the answer key) -------------------------------------------


class Range(Model):
    """A required or tested range; either bound may be open (``≥ 100 kN``)."""

    type: Literal["range"] = "range"
    min: float | None = None
    max: float | None = None
    unit: str

    @model_validator(mode="after")
    def _bounds(self) -> Range:
        if self.min is None and self.max is None:
            raise ValueError("range needs at least one bound")
        return self


class Number(Model):
    type: Literal["number"] = "number"
    value: float
    unit: str


class OneOf(Model):
    type: Literal["one_of"] = "one_of"
    allowed: tuple[str, ...] = Field(min_length=1)


class Text(Model):
    type: Literal["text"] = "text"
    value: str


class Present(Model):
    """A feature that must exist; ``value`` is set when an observation states it."""

    type: Literal["present"] = "present"
    value: bool | None = None


Value = Annotated[Range | Number | OneOf | Text | Present, Field(discriminator="type")]


# --- Claims ---------------------------------------------------------------------------


class Citation(Model):
    """``doc_id + revision + page + verbatim quote``; ``value`` is the value the citation is
    meant to support, which must appear inside the quote."""

    doc: str
    rev: int = Field(ge=0)
    page: int = Field(ge=1, description="1-based; for a spreadsheet, the sheet number.")
    quote: str = Field(min_length=1)
    value: Value | None = None


class EvidenceRef(Model):
    """A vendor test step offered as Evidence for a requirement."""

    doc: str
    rev: int = Field(ge=0)
    step: str


class RequirementAnswer(Model):
    id: str
    value: Value | None = None
    coverage: CoverageClass | None = None
    citations: tuple[Citation, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class Finding(Model):
    """A Pre-review finding. Its citations locate it in the corpus."""

    type: DefectType
    severity: Literal["critical", "major", "minor"] | None = None
    detail: str = ""
    citations: tuple[Citation, ...] = Field(min_length=1)


class MissingDocument(Model):
    """A document the VMP requires that is not in the corpus. ``id`` is informational: the
    system cannot know the number a document that does not exist would get."""

    type: str
    stage: Literal["design", "FAT", "SAT", "IQ", "OQ"]
    id: str | None = None


class TestStep(Model):
    """A drafted IQ/OQ Test Step. ``acceptance: null`` means "to be set by a human"; a
    non-null Acceptance Criterion must be copied from ``acceptance_citation``."""

    __test__ = False  # not a pytest class

    id: str
    requirement: str
    description: str = ""
    method: str | None = None
    instrument: str | None = None
    acceptance: Value | None = None
    acceptance_citation: Citation | None = None
    witness: bool | None = None


class System(Model):
    name: str
    model: str | None = None
    prompt: str | None = None
    run_id: str | None = None


class Submission(Model):
    version: Literal[1] = SUBMISSION_VERSION
    equipment: str
    system: System
    requirements: tuple[RequirementAnswer, ...] = ()
    findings: tuple[Finding, ...] = ()
    missing_documents: tuple[MissingDocument, ...] = ()
    test_steps: tuple[TestStep, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> Submission:
        for name, ids in (
            ("requirement", [r.id for r in self.requirements]),
            ("test step", [s.id for s in self.test_steps]),
        ):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            if dupes:
                raise ValueError(f"duplicate {name} ids: {dupes}")
        return self
