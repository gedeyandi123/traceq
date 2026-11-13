"""The system's own output model: ``submission.json``, submission schema version 1.

The system owns it rather than importing the scorer's (spec #29, "Isolation"); a test checks
that what it writes validates against the scorer's schema. This slice fills requirements
with their values and citations; Coverage, Evidence, findings, missing documents, drafted
Test Steps and OCR come with later tickets.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from traceq.traceability import Citation, Traceability, Value

SUBMISSION_VERSION = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CitationOut(_Model):
    doc: str
    rev: int
    page: int
    quote: str
    value: Value | None = None


class RequirementAnswer(_Model):
    id: str
    value: Value | None = None
    citations: tuple[CitationOut, ...] = ()


class SystemInfo(_Model):
    name: str
    model: str | None = None
    prompt: str | None = None
    run_id: str | None = None


class Submission(_Model):
    version: Literal[1] = SUBMISSION_VERSION
    equipment: str
    system: SystemInfo
    requirements: tuple[RequirementAnswer, ...] = ()


def _cite(c: Citation, value: Value | None = None) -> CitationOut:
    return CitationOut(doc=c.doc, rev=c.rev, page=c.page, quote=c.quote, value=value)


def build(equipment: str, system: SystemInfo, t: Traceability) -> Submission:
    """Only verified claims reach the submission: a requirement without a verified value
    keeps its URS citation and an empty value, for a human to fill."""
    answers: list[RequirementAnswer] = []
    for r in t.requirements:
        claim = t.values.get(r.id)
        if claim is None:
            answers.append(RequirementAnswer(id=r.id, citations=(_cite(r.citation),)))
        else:
            answers.append(
                RequirementAnswer(
                    id=r.id, value=claim.value, citations=(_cite(claim.citation, claim.value),)
                )
            )
    return Submission(equipment=equipment, system=system, requirements=tuple(answers))
