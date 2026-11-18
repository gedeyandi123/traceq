"""The system's own output model: ``submission.json``, submission schema version 1.

The system owns it rather than importing the scorer's (spec #29, "Isolation"); a test checks
that what it writes validates against the scorer's schema. Requirements carry their value,
Coverage class, the vendor steps offered as Evidence and the citations of the URS sentence,
the Evidence and the design facts compared with the URS. A value that reads two ways is an
``ambiguous_value`` finding: ask for confirmation. Pre-review adds its Check Findings and the
documents the VMP requires that the corpus lacks, then its AI Findings: the schema has no
layer field, so the layer follows from the finding type, as the scorer reports it (the
layer, model and prompt of each finding are in ``findings.json``). ``ocr`` holds every
entry the OCR model read on a scan, with its quad. ``test_steps`` are the drafted IQ/OQ
Test Steps: an AC only when copied from a verified citation, otherwise none, "to be set by
a human" (the flag and the AI Finding fields are in ``drafts.json``). The Coverage reason
is in ``matrix.json``: the submission schema has no field for it. A Review Package run
names its package (``review_package``) and adds the Protocol Draft's Test Step rows
(``draft_steps``): the AC as read with its citation, and whether it was compared.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traceq.documents import CorpusDocument, Page
from traceq.documents.pages import Quad
from traceq.protocols import Drafts
from traceq.review import AiType, Review
from traceq.review.printed import Limit, Tolerance
from traceq.review.rules import CheckType
from traceq.traceability import Ambiguous, Citation, Linked, Traceability, Value
from traceq.traceability.coverage import CoverageClass
from traceq.traceability.values import Number, Text

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
    type: Literal["ambiguous_value"] | CheckType | AiType
    detail: str
    citations: tuple[CitationOut, ...]


class MissingDocument(_Model):
    type: str
    stage: Literal["design", "FAT", "SAT", "IQ", "OQ"]
    id: str | None = None


class SystemInfo(_Model):
    name: str
    model: str | None = None
    prompt: str | None = None
    run_id: str | None = None


class OcrEntry(_Model):
    doc: str
    rev: int
    page: int
    text: str
    quad: Quad


class TestStep(_Model):
    __test__ = False  # not a pytest class

    id: str
    requirement: str
    description: str = ""
    method: str | None = None
    instrument: str | None = None
    acceptance: Value | None = None
    acceptance_citation: CitationOut | None = None


DraftValue = Annotated[Limit | Number | Tolerance | Text, Field(discriminator="type")]


class DraftStep(_Model):
    """A Test Step of the Protocol Draft under review, as read: the AC value code read from
    the print, the citation it was read from, and whether it was compared (why not)."""

    id: str
    acceptance: DraftValue | None = None
    acceptance_citation: CitationOut | None = None
    compared: bool
    not_compared: str | None = None

    @model_validator(mode="after")
    def _reason(self) -> DraftStep:
        if self.compared == (self.not_compared is not None):
            raise ValueError(f"{self.id}: a reason exactly when the step was not compared")
        return self


class Submission(_Model):
    version: Literal[1] = SUBMISSION_VERSION
    equipment: str
    system: SystemInfo
    requirements: tuple[RequirementAnswer, ...] = ()
    findings: tuple[Finding, ...] = ()
    missing_documents: tuple[MissingDocument, ...] = ()
    test_steps: tuple[TestStep, ...] = ()
    ocr: tuple[OcrEntry, ...] = ()
    review_package: str | None = None
    """The Review Package this run answers; ``None``: an Equipment run."""
    draft_steps: tuple[DraftStep, ...] = ()


def cite(c: Citation, value: Value | None = None) -> CitationOut:
    return CitationOut(doc=c.doc, rev=c.rev, page=c.page, quote=c.quote, value=value)


def _evidence_citations(linked: Linked | None) -> list[CitationOut]:
    """Evidence and design quotes, without a value: a value read from a vendor record is not
    the requirement's value, and an ambiguous one must not be claimed."""
    if linked is None:
        return []
    return [cite(s.citation) for s in linked.steps] + [cite(r.citation) for r in linked.rows]


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
                citations=(cite(s.citation),),
            )
    return list(findings.values())


def ocr_entries(scans: Sequence[tuple[CorpusDocument, Sequence[Page]]]) -> list[OcrEntry]:
    """Every entry read on the scans, page by page. Printed text the model read is handed in
    too: the scorer pairs the handwritten entries it expects and leaves the rest unscored."""
    return [
        OcrEntry(doc=doc.doc_id, rev=doc.rev, page=p.number, text=o.text, quad=o.quad)
        for doc, pages in scans
        for p in pages
        for o in p.ocr
    ]


def build(
    equipment: str,
    system: SystemInfo,
    t: Traceability,
    review: Review,
    drafts: Drafts | None = None,
    scans: Sequence[tuple[CorpusDocument, Sequence[Page]]] = (),
) -> Submission:
    """Only verified claims reach the submission: a requirement without a verified value
    keeps its URS citation and an empty value, for a human to fill."""
    answers: list[RequirementAnswer] = []
    for r in t.requirements:
        claim = t.values.get(r.id)
        linked = t.linked.get(r.id)
        urs = cite(r.citation) if claim is None else cite(claim.citation, claim.value)
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
        findings=(
            *(
                Finding(type=f.type, detail=f.detail, citations=tuple(map(cite, f.citations)))
                for f in (*review.findings, *review.ai_findings)
            ),
            *_ambiguous(t),
        ),
        missing_documents=tuple(
            MissingDocument(type=d.type, stage=d.stage, id=d.doc_id) for d in review.missing
        ),
        test_steps=tuple(
            TestStep(
                id=d.id,
                requirement=d.requirement.id,
                description=d.description,
                method=d.method,
                instrument=d.instrument,
                acceptance=d.acceptance.value,
                acceptance_citation=None
                if d.acceptance.citation is None
                else cite(d.acceptance.citation),
            )
            for d in (drafts.drafts if drafts else ())
        ),
        ocr=tuple(ocr_entries(scans)),
    )
