"""AI Findings: the layer of Pre-review that runs after the rules, on what rules cannot judge
(spec #29): inconsistent data across documents, an AC that deviates from the URS, GDP
corrections on scans, outdated references.

One call reads every current document the slice can read, with the register of every
document and revision held, so a reference to a superseded revision can be seen. Each
finding the model returns is kept only when every one of its citations names a document
given in the call and quotes its cited page (the citation check); otherwise the whole
finding is dropped and listed for the run metadata. A finding is a proposal for a human
(ADR 0002): ``findings.json`` carries its model, prompt hash, time and a ``pending``
reviewer action.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from traceq.ai import LLM, Request
from traceq.ai.port import sha256
from traceq.documents import Corpus, CorpusDocument
from traceq.review.prompts import AI_REVIEW
from traceq.traceability import Citation, Dropped
from traceq.traceability.citations import verified

AiType = Literal[
    "inconsistent_data",
    "ac_deviates_from_urs",
    "gdp_correction",
    "outdated_reference",
]


@dataclass(frozen=True)
class AiFinding:
    type: AiType
    detail: str
    citations: tuple[Citation, ...]
    """Every one verified: a finding with one unverifiable citation is dropped whole."""


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Citation(_Answer):
    doc: str
    rev: int
    page: int
    quote: str


class _Finding(_Answer):
    type: AiType
    detail: str
    citations: list[_Citation] = Field(min_length=1)


class _Findings(_Answer):
    findings: list[_Finding]


Pages = Mapping[tuple[str, int], list[str]]
"""Page text per document given to the model, keyed by ``(doc_id, rev)``."""


def verify_findings(text: str, pages: Pages, dropped: list[Dropped]) -> list[AiFinding]:
    """The model's answer, kept finding by finding when every citation passes the check."""
    try:
        answer = _Findings.model_validate_json(text).findings
    except ValidationError:
        dropped.append(Dropped("ai_finding", "ai_review", "bad answer"))
        return []
    out: list[AiFinding] = []
    for n, f in enumerate(answer, 1):
        cites = tuple(Citation(c.doc, c.rev, c.page, c.quote) for c in f.citations)
        what = f"{f.type} {n}"
        if any((c.doc, c.rev) not in pages for c in cites):
            dropped.append(Dropped("ai_finding", what, "document not given"))
        elif not all(verified(c, pages[(c.doc, c.rev)]) for c in cites):
            dropped.append(Dropped("ai_finding", what, "quote not on page"))
        elif not f.detail.strip():
            dropped.append(Dropped("ai_finding", what, "no detail"))
        else:
            finding = AiFinding(f.type, f.detail.strip(), tuple(dict.fromkeys(cites)))
            if all((x.type, x.citations) != (finding.type, finding.citations) for x in out):
                out.append(finding)
    return out


def _register(corpus: Corpus) -> str:
    lines = [f"Equipment {corpus.equipment}. Documents held (doc, revisions, type):"]
    revs: dict[str, list[int]] = {}
    types: dict[str, str] = {}
    for d in corpus.documents:
        revs.setdefault(d.doc_id, []).append(d.rev)
        types[d.doc_id] = d.type
    for doc_id in sorted(revs):
        held = ", ".join(str(r) for r in sorted(revs[doc_id]))
        lines.append(f"- {doc_id}: rev {held} (current {max(revs[doc_id])}); {types[doc_id]}")
    return "\n".join(lines)


def _document(doc: CorpusDocument, pages: Sequence[str]) -> str:
    body = "\n".join(f'<page n="{n}">\n{text}\n</page>' for n, text in enumerate(pages, 1))
    return f'<document doc="{doc.doc_id}" rev="{doc.rev}" type="{doc.type}">\n{body}\n</document>'


def ai_review(corpus: Corpus, llm: LLM, dropped: list[Dropped]) -> list[AiFinding]:
    """One call over every current, readable document of the corpus."""
    types = sorted({d.type for d in corpus.documents})
    docs = [d for t in types for d in corpus.current(t) if corpus.readable(d)]
    if not docs:
        return []
    pages: dict[tuple[str, int], list[str]] = {(d.doc_id, d.rev): corpus.pages(d) for d in docs}
    user = "\n\n".join([_register(corpus), *(_document(d, pages[(d.doc_id, d.rev)]) for d in docs)])
    key = sha256(",".join(sorted(d.sha256 for d in docs)))
    (answer,) = llm.complete([Request(AI_REVIEW, user, key)])
    return verify_findings(answer.text, pages, dropped)
