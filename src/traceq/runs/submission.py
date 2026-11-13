"""The system's own output model: ``submission.json``, submission schema version 1.

The system owns it rather than importing the scorer's (spec #29, "Isolation"); a test checks
that what it writes validates against the scorer's schema. Requirements carry their value,
Coverage class, the vendor steps offered as Evidence and the citations of the URS sentence,
the Evidence and the design facts compared with the URS. A value that reads two ways is an
``ambiguous_value`` finding: ask for confirmation. Other findings, missing documents, drafted
Test Steps and OCR come with later tickets. The Coverage reason is in ``matrix.json``: the
submission schema has no field for it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from traceq.traceability import Ambiguous, Citation, Linked, Traceability, Value
from traceq.traceability.coverage import CoverageClass

SUBMISSION_VERSION = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CitationOut(_Model):
    doc: str
    rev: int
    page: int
    quote: str
    value: Value | None = None


class EvidenceRef(_Model):
    doc: str
    rev: int
    step: str


class RequirementAnswer(_Model):
    id: str
    value: Value | None = None
    coverage: CoverageClass | None = None
    citations: tuple[CitationOut, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class Finding(_Model):
    type: Literal["ambiguous_value"]
    detail: str
    citations: tuple[CitationOut, ...]


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
    findings: tuple[Finding, ...] = ()


def _cite(c: Citation, value: Value | None = None) -> CitationOut:
    return CitationOut(doc=c.doc, rev=c.rev, page=c.page, quote=c.quote, value=value)


def _evidence_citations(linked: Linked | None) -> list[CitationOut]:
    """Evidence and design quotes, without a value: a value read from a vendor record is not
    the requirement's value, and an ambiguous one must not be claimed."""
    if linked is None:
        return []
    return [_cite(s.citation) for s in linked.steps] + [_cite(r.citation) for r in linked.rows]


def _ambiguous(t: Traceability) -> list[Finding]:
    findings: dict[str, Finding] = {}
    for linked in t.linked.values():
        for s, verdict in zip(linked.steps, linked.coverage.verdicts, strict=True):
            observed = verdict.step.observed
            if s.id in findings or not isinstance(observed, Ambiguous):
                continue
            readings = " or ".join(f"{x:g}" for x in observed.readings)
            findings[s.id] = Finding(
                type="ambiguous_value",
                detail=f"{s.step}: '{s.observed}' reads as {readings}; ask for confirmation",
                citations=(_cite(s.citation),),
            )
    return list(findings.values())


def build(equipment: str, system: SystemInfo, t: Traceability) -> Submission:
    """Only verified claims reach the submission: a requirement without a verified value
    keeps its URS citation and an empty value, for a human to fill."""
    answers: list[RequirementAnswer] = []
    for r in t.requirements:
        claim = t.values.get(r.id)
        linked = t.linked.get(r.id)
        urs = _cite(r.citation) if claim is None else _cite(claim.citation, claim.value)
        answers.append(
            RequirementAnswer(
                id=r.id,
                value=None if claim is None else claim.value,
                coverage=None if linked is None else linked.coverage.coverage,
                citations=(urs, *_evidence_citations(linked)),
                evidence=tuple(
                    EvidenceRef(doc=s.protocol.doc, rev=s.protocol.rev, step=s.step)
                    for s in (linked.steps if linked else ())
                ),
            )
        )
    return Submission(
        equipment=equipment,
        system=system,
        requirements=tuple(answers),
        findings=tuple(_ambiguous(t)),
    )
