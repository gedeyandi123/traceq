"""The site's governing documents, read from the corpus with citations (spec #29): the
required-document list from the VMP annex and the rules the qualification SOP states.

Nothing here is typed into code or config: a required document or a site rule exists for
the system only when the VMP or SOP prints it and the quote passes the citation check. The
model maps the printed (possibly Indonesian) document type to its type code; code checks
that the quote holds the document number, the printed type and the printed stage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from traceq.ai import LLM, Request
from traceq.documents import Corpus, CorpusDocument, normalise
from traceq.review.facts import RequiredDocument, SiteRule
from traceq.review.prompts import REQUIRED, RULES
from traceq.traceability import Citation, Dropped
from traceq.traceability.citations import verified

DocType = Literal[
    "urs",
    "risk_assessment",
    "datasheet",
    "functional_spec",
    "dq_report",
    "material_certificate",
    "calibration_certificate",
    "fat",
    "sat",
    "iq_protocol",
    "oq_protocol",
    "other",
]


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Row(_Answer):
    doc_id: str
    type_printed: str
    type: DocType
    stage_printed: str
    stage: Literal["design", "FAT", "SAT", "IQ", "OQ"]
    page: int
    quote: str


class _Annex(_Answer):
    equipment: str
    page: int
    quote: str
    rows: list[_Row]


class _Annexes(_Answer):
    annexes: list[_Annex]


class _Rule(_Answer):
    rule: SiteRule
    page: int
    quote: str


class _Rules(_Answer):
    rules: list[_Rule]


@dataclass
class Governing:
    required: list[RequiredDocument] = field(default_factory=list[RequiredDocument])
    rules: dict[SiteRule, Citation] = field(default_factory=dict[SiteRule, Citation])
    read: list[CorpusDocument] = field(default_factory=list[CorpusDocument])


def _holds(quote: str, *printed: str) -> bool:
    q = normalise(quote)
    return all(normalise(p) in q for p in printed)


def _document_prompt(doc: CorpusDocument, pages: Sequence[str]) -> str:
    body = "\n\n".join(f'<page n="{n}">\n{text}\n</page>' for n, text in enumerate(pages, 1))
    return f"Document {doc.doc_id}, revision {doc.rev}, {len(pages)} pages.\n\n{body}"


def _required(
    doc: CorpusDocument, pages: list[str], text: str, equipment: str, dropped: list[Dropped]
) -> list[RequiredDocument]:
    try:
        annexes = _Annexes.model_validate_json(text).annexes
    except ValidationError:
        dropped.append(Dropped("required_document", doc.doc_id, "bad answer"))
        return []
    out: list[RequiredDocument] = []
    for annex in annexes:
        if normalise(annex.equipment) != normalise(equipment):
            continue
        head = Citation(doc.doc_id, doc.rev, annex.page, annex.quote)
        if not (verified(head, pages) and _holds(annex.quote, equipment)):
            dropped.append(Dropped("required_document", f"{doc.doc_id} annex", "quote check"))
            continue
        for r in annex.rows:
            c = Citation(doc.doc_id, doc.rev, r.page, r.quote)
            if not (verified(c, pages) and _holds(r.quote, r.doc_id, r.type_printed)):
                dropped.append(Dropped("required_document", r.doc_id, "quote check"))
            elif not _holds(r.quote, r.stage_printed):
                dropped.append(Dropped("required_document", r.doc_id, "stage not in quote"))
            elif all(d.doc_id != r.doc_id for d in out):
                out.append(RequiredDocument(r.doc_id, r.type, r.stage, c))
    return out


def _rules(
    doc: CorpusDocument, pages: list[str], text: str, dropped: list[Dropped]
) -> dict[SiteRule, Citation]:
    try:
        rules = _Rules.model_validate_json(text).rules
    except ValidationError:
        dropped.append(Dropped("site_rule", doc.doc_id, "bad answer"))
        return {}
    out: dict[SiteRule, Citation] = {}
    for r in rules:
        c = Citation(doc.doc_id, doc.rev, r.page, r.quote)
        if verified(c, pages):
            out.setdefault(r.rule, c)
        else:
            dropped.append(Dropped("site_rule", f"{doc.doc_id} {r.rule}", "quote not on page"))
    return out


def read_governing(corpus: Corpus, llm: LLM, dropped: list[Dropped]) -> Governing:
    """One call per current VMP and SOP the slice can read."""
    out = Governing()
    jobs = [(d, REQUIRED) for d in corpus.current("vmp")] + [
        (d, RULES) for d in corpus.current("sop")
    ]
    jobs = [(d, p) for d, p in jobs if corpus.readable(d)]
    pages = {d.doc_id: corpus.pages(d) for d, _ in jobs}
    answers = llm.complete(
        [Request(p, _document_prompt(d, pages[d.doc_id]), d.sha256) for d, p in jobs]
    )
    for (doc, prompt), answer in zip(jobs, answers, strict=True):
        out.read.append(doc)
        if prompt is REQUIRED:
            found = _required(doc, pages[doc.doc_id], answer.text, corpus.equipment, dropped)
            out.required += [r for r in found if all(x.doc_id != r.doc_id for x in out.required)]
        else:
            for rule, c in _rules(doc, pages[doc.doc_id], answer.text, dropped).items():
                out.rules.setdefault(rule, c)
    return out


def missing_documents(
    required: Sequence[RequiredDocument], corpus: Corpus
) -> list[RequiredDocument]:
    """Documents the VMP requires for this Equipment that the corpus does not hold, in any
    revision."""
    held = {normalise(d.doc_id) for d in corpus.documents}
    return [r for r in required if normalise(r.doc_id) not in held]
