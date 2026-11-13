"""The site's Vendor Assessment, read from the corpus with citations: Coverage condition 1
(design section 6; CPOB Ch. 12).

One call per current Vendor Assessment reads every area it rates, the rating as printed,
whether the rating lets the site rely on the vendor's results, and the assessment date. An
area is kept only when its quote is on the cited page and holds both the area name and the
rating; the date only when its quote is on the page and holds it. Nothing about the areas is
typed into code: the decision table matches the area the link step names for a requirement
against the areas kept here. No assessment in the corpus means condition 1 fails.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, ValidationError

from traceq.ai import LLM, Request
from traceq.documents import Corpus, CorpusDocument, normalise
from traceq.traceability.ambiguity import parse_date
from traceq.traceability.citations import Citation, verified
from traceq.traceability.coverage import Date, VendorAssessment
from traceq.traceability.evidence import Dropped
from traceq.traceability.prompts import ASSESSMENT


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Date(_Answer):
    date: str
    page: int
    quote: str


class _Area(_Answer):
    area: str
    mark: str
    relied: bool
    page: int
    quote: str


class _Assessment(_Answer):
    assessed_on: _Date | None
    areas: list[_Area]


@dataclass(frozen=True)
class Area:
    name: str
    """As printed."""
    relied: bool
    citation: Citation
    """Verified: holds the area name and its rating."""


@dataclass(frozen=True)
class Assessment:
    doc: str
    rev: int
    sha256: str
    areas: tuple[Area, ...]
    assessed_on: Date = None
    date_citation: Citation | None = None

    @property
    def decision(self) -> VendorAssessment:
        """What the decision table matches: the areas the site may rely on."""
        return VendorAssessment(scope=frozenset(a.name for a in self.areas if a.relied))

    def area(self, name: str) -> Area | None:
        return next((a for a in self.areas if normalise(a.name) == normalise(name)), None)


def _holds(quote: str, *printed: str) -> bool:
    q = normalise(quote)
    return all(normalise(p) and normalise(p) in q for p in printed)


def _document_prompt(doc: CorpusDocument, pages: Sequence[str]) -> str:
    body = "\n\n".join(f'<page n="{n}">\n{text}\n</page>' for n, text in enumerate(pages, 1))
    return f"Document {doc.doc_id}, revision {doc.rev}, {len(pages)} pages.\n\n{body}"


def _read(doc: CorpusDocument, pages: list[str], text: str, dropped: list[Dropped]) -> Assessment:
    try:
        a = _Assessment.model_validate_json(text)
    except ValidationError:
        dropped.append(Dropped("assessment", doc.doc_id, "bad answer"))
        return Assessment(doc.doc_id, doc.rev, doc.sha256, ())
    areas: list[Area] = []
    for x in a.areas:
        c = Citation(doc.doc_id, doc.rev, x.page, x.quote)
        if not (verified(c, pages) and _holds(x.quote, x.area, x.mark)):
            dropped.append(Dropped("assessment", f"{doc.doc_id} {x.area}", "quote check"))
        elif all(normalise(y.name) != normalise(x.area) for y in areas):
            areas.append(Area(x.area, x.relied, c))
    assessed_on: Date = None
    date_citation: Citation | None = None
    if a.assessed_on is not None:
        d = a.assessed_on
        c = Citation(doc.doc_id, doc.rev, d.page, d.quote)
        if verified(c, pages) and _holds(d.quote, d.date):
            assessed_on, date_citation = parse_date(d.date), c
        else:
            dropped.append(Dropped("date", f"{doc.doc_id} assessed_on", "quote check"))
    return Assessment(doc.doc_id, doc.rev, doc.sha256, tuple(areas), assessed_on, date_citation)


def read_vendor_assessment(corpus: Corpus, llm: LLM, dropped: list[Dropped]) -> Assessment | None:
    """The current Vendor Assessment of the corpus, or ``None`` when it holds none the slice
    can read. With more than one, the last by document id is used."""
    docs = [d for d in corpus.current("vendor_assessment") if corpus.readable(d)]
    if not docs:
        return None
    doc = docs[-1]
    pages = corpus.pages(doc)
    (answer,) = llm.complete([Request(ASSESSMENT, _document_prompt(doc, pages), doc.sha256)])
    return _read(doc, pages, answer.text, dropped)
