"""URS to requirements with values: the LLM reads and cites, code decides what is kept.

1. Segmentation: one call per page of the current URS revision lists its requirements.
2. Extraction: one call per requirement reads its required value with a quote.
3. Citation check: a requirement or value whose quote is not on the cited page, or does not
   state the value, is dropped and listed in ``dropped`` for the run metadata.
4. Evidence and Coverage (``traceability.evidence``): facts from the vendor documents, the
   links the LLM proposes, and the decision table.

Only the current URS revision is read, so a value a later revision superseded (S8) is never
claimed: a quote of the old value is not on the current page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from traceq.ai import LLM, Request
from traceq.ai.port import sha256
from traceq.documents import Corpus, CorpusDocument
from traceq.traceability.citations import Citation, verified
from traceq.traceability.evidence import Dropped, Linked, VendorFacts, link, read_vendor_facts
from traceq.traceability.prompts import EXTRACT, SEGMENT
from traceq.traceability.values import Number, OneOf, Present, Range, Text, Value

PIPELINE_VERSION = "0.2.0"
"""Part of every recording key: bump it when a change outside the prompts alters requests."""


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    citation: Citation
    """Verified: the requirement as printed in the URS."""


@dataclass(frozen=True)
class ValueClaim:
    value: Value
    citation: Citation
    """Verified: the quote is on the page and states the value."""


@dataclass
class Traceability:
    requirements: list[Requirement] = field(default_factory=list[Requirement])
    values: dict[str, ValueClaim] = field(default_factory=dict[str, ValueClaim])
    dropped: list[Dropped] = field(default_factory=list[Dropped])
    vendor: VendorFacts = field(default_factory=VendorFacts)
    linked: dict[str, Linked] = field(default_factory=dict[str, Linked])


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Segment(_Answer):
    id: str
    text: str
    quote: str


class _Segments(_Answer):
    requirements: list[_Segment]


class _Extracted(_Answer):
    kind: Literal["range", "number", "one_of", "text", "present", "none"]
    min: float | None
    max: float | None
    number: float | None
    unit: str | None
    allowed: list[str]
    text: str | None
    quote: str


def _page_prompt(doc: CorpusDocument, page: int, text: str) -> str:
    return f"Document {doc.doc_id}, revision {doc.rev}, page {page}.\n\n<page>\n{text}\n</page>"


def _value(a: _Extracted) -> Value | None:
    """The claimed value, or ``None`` when the answer claims none. Raises ``ValueError``
    when the answer is incomplete for its kind."""
    match a.kind:
        case "none":
            return None
        case "range":
            return Range(min=a.min, max=a.max, unit=a.unit or "")
        case "number":
            if a.number is None:
                raise ValueError("number without a value")
            return Number(value=a.number, unit=a.unit or "")
        case "one_of":
            return OneOf(allowed=tuple(a.allowed))
        case "text":
            if not a.text:
                raise ValueError("text without a value")
            return Text(value=a.text)
        case "present":
            return Present()


def trace(corpus: Corpus, llm: LLM) -> Traceability:
    out = Traceability()
    urs = corpus.current("urs")
    for doc in urs:
        pages = corpus.pages(doc)
        segment_answers = llm.complete(
            [
                Request(SEGMENT, _page_prompt(doc, n, text), doc.sha256)
                for n, text in enumerate(pages, 1)
            ]
        )
        found: list[Requirement] = []
        for n, answer in enumerate(segment_answers, 1):
            try:
                segments = _Segments.model_validate_json(answer.text).requirements
            except ValidationError:
                out.dropped.append(Dropped("requirement", f"{doc.doc_id} p{n}", "bad answer"))
                continue
            for s in segments:
                c = Citation(doc.doc_id, doc.rev, n, s.quote)
                if any(r.id == s.id for r in [*out.requirements, *found]):
                    out.dropped.append(Dropped("requirement", s.id, "duplicate id"))
                elif not verified(c, pages):
                    out.dropped.append(Dropped("requirement", s.id, "quote not on page"))
                else:
                    found.append(Requirement(s.id, s.text, c))
        out.requirements += found

        extract_answers = llm.complete(
            [
                Request(
                    EXTRACT,
                    json.dumps({"id": r.id, "requirement": r.text}, ensure_ascii=False)
                    + "\n\n"
                    + _page_prompt(doc, r.citation.page, pages[r.citation.page - 1]),
                    doc.sha256,
                )
                for r in found
            ]
        )
        for r, answer in zip(found, extract_answers, strict=True):
            try:
                a = _Extracted.model_validate_json(answer.text)
                value = _value(a)
            except (ValidationError, ValueError):
                out.dropped.append(Dropped("value", r.id, "bad answer"))
                continue
            if value is None:
                continue
            c = Citation(doc.doc_id, doc.rev, r.citation.page, a.quote)
            if verified(c, pages, value):
                out.values[r.id] = ValueClaim(value, c)
            else:
                out.dropped.append(Dropped("value", r.id, "quote not on page or value not in it"))

    out.vendor = read_vendor_facts(corpus, llm, out.dropped)
    requirements = [(r.id, r.text, _claimed(out, r.id)) for r in out.requirements]
    if requirements:
        key = sha256(",".join(sorted(d.sha256 for d in urs)))
        out.linked = link(requirements, out.vendor, key, llm, out.dropped)
    return out


def _claimed(t: Traceability, rid: str) -> Value | None:
    claim = t.values.get(rid)
    return None if claim is None else claim.value
