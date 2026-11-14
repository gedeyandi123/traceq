"""Reading qualification records for Pre-review: one call per page of each current vendor
protocol and calibration certificate the slice can read.

The model lists signature rows, calibration validities, instruments per step, deviations
and calculations, each with a quote. A fact is kept only when its quote is on the page and
holds what it claims (the name, the date, the instrument id, the numbers as printed), and
does not rest on an uncertain OCR reading (#78); otherwise it is dropped and listed for the
run metadata. Dates and numbers are read from the print by code (the ambiguity rule), not
from the model's reading.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, ValidationError

from traceq.ai import LLM, Request
from traceq.documents import Corpus, CorpusDocument, Page, normalise
from traceq.review.facts import (
    Calculation,
    Calibration,
    Deviation,
    InstrumentUse,
    Operation,
    Record,
    Role,
    Signature,
)
from traceq.review.prompts import RECORD
from traceq.traceability import Citation, Dropped
from traceq.traceability.ambiguity import parse_date, read_number
from traceq.traceability.citations import UNCERTAIN, uncertain, verified
from traceq.traceability.evidence import Claim

RECORD_TYPES = ("fat", "sat", "calibration_certificate")


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Signature(_Answer):
    role_printed: str
    role: Role
    site: bool
    name: str
    signed: bool
    date: str
    quote: str


class _Instrument(_Answer):
    id: str
    valid_until: str
    quote: str


class _StepInstruments(_Answer):
    step: str
    instruments: list[str]
    quote: str


class _Deviation(_Answer):
    id: str
    steps: list[str]
    quote: str


class _Calculation(_Answer):
    step: str
    operation: Operation
    inputs: list[str]
    result: str
    quote: str


class _Record(_Answer):
    signatures: list[_Signature]
    instruments: list[_Instrument]
    step_instruments: list[_StepInstruments]
    deviations: list[_Deviation]
    calculations: list[_Calculation]


def _holds(quote: str, *printed: str) -> bool:
    q = normalise(quote)
    return all(normalise(p) in q for p in printed if p.strip())


def _span(quote: str, *printed: str) -> str:
    """The normalised quote from the first printed field to the end of the last one, so
    text OCR joined onto the line (a stamp beside a signature) is not cited (#76)."""
    q = normalise(quote)
    found = [(q.find(f), len(f)) for f in map(normalise, printed) if f]
    return q[min(i for i, _ in found) : max(i + n for i, n in found)] if found else q


def _page_prompt(doc: CorpusDocument, page: int, text: str) -> str:
    return f"Document {doc.doc_id}, revision {doc.rev}, page {page}.\n\n<page>\n{text}\n</page>"


def _decimals(printed: str) -> int:
    m = re.search(r"[.,](\d+)\D*$", printed.strip())
    return 0 if m is None else len(m[1])


class _Reader:
    def __init__(self, doc: CorpusDocument, pages: Sequence[Page], dropped: list[Dropped]) -> None:
        self.doc, self.pages, self.dropped = doc, pages, dropped
        self.texts = [p.text for p in pages]
        self.record = Record(doc.doc_id, doc.rev, doc.type)

    def cite(
        self, page: int, quote: str, claim: Claim, what: str, *printed: str
    ) -> Citation | None:
        c = Citation(self.doc.doc_id, self.doc.rev, page, quote)
        if not (verified(c, self.texts) and _holds(quote, *printed)):
            reason = "quote check"
        elif uncertain(c, self.pages):
            reason = UNCERTAIN
        else:
            return c
        self.dropped.append(Dropped(claim, f"{self.doc.doc_id} p{page} {what}", reason))
        return None

    def page(self, n: int, a: _Record) -> None:
        r = self.record
        for s in a.signatures:
            c = self.cite(n, s.quote, "signature", s.role_printed, s.role_printed, s.name, s.date)
            if c is not None:
                c = self.cite(
                    n,
                    _span(s.quote, s.role_printed, s.name, s.date),
                    "signature",
                    s.role_printed,
                    s.role_printed,
                    s.name,
                    s.date,
                )
            if c is not None:
                date = parse_date(s.date) if s.date.strip() else None
                r.signatures.append(
                    Signature(s.role_printed, s.role, s.site, s.name, s.signed, date, c)
                )
        for i in a.instruments:
            c = self.cite(n, i.quote, "calibration", i.id, i.id, i.valid_until)
            if c is not None and i.valid_until.strip():
                r.calibrations.append(Calibration(i.id, parse_date(i.valid_until), c))
        for u in a.step_instruments:
            c = self.cite(n, u.quote, "instrument", u.step, u.step, *u.instruments)
            if c is not None:
                r.uses += [InstrumentUse(u.step, x, c) for x in u.instruments]
        for d in a.deviations:
            c = self.cite(n, d.quote, "deviation", d.id, d.id)
            if c is not None:
                r.deviations.append(Deviation(d.id, tuple(d.steps), c))
        for k in a.calculations:
            self.calculation(n, k)

    def calculation(self, n: int, k: _Calculation) -> None:
        c = self.cite(n, k.quote, "calculation", k.step, k.step, *k.inputs, k.result)
        if c is None:
            return
        numbers = [read_number(x, self.doc.language) for x in (*k.inputs, k.result)]
        values = [x for x in numbers if isinstance(x, float)]
        if len(values) != len(numbers) or not k.inputs:
            self.dropped.append(
                Dropped("calculation", f"{self.doc.doc_id} {k.step}", "number not read")
            )
            return
        self.record.calculations.append(
            Calculation(k.step, k.operation, tuple(values[:-1]), values[-1], _decimals(k.result), c)
        )


def read_records(
    corpus: Corpus, llm: LLM, dropped: list[Dropped]
) -> tuple[list[Record], list[CorpusDocument]]:
    """The records read, and the documents of these types the slice cannot read yet."""
    records: list[Record] = []
    not_read: list[CorpusDocument] = []
    for doc_type in RECORD_TYPES:
        for doc in corpus.current(doc_type):
            if not corpus.readable(doc):
                not_read.append(doc)
                continue
            records.append(_read(doc, corpus.read(doc), llm, dropped))
    return records, not_read


def _read(doc: CorpusDocument, pages: Sequence[Page], llm: LLM, dropped: list[Dropped]) -> Record:
    answers = llm.complete(
        [Request(RECORD, _page_prompt(doc, n, p.text), doc.sha256) for n, p in enumerate(pages, 1)]
    )
    reader = _Reader(doc, pages, dropped)
    for n, answer in enumerate(answers, 1):
        try:
            reader.page(n, _Record.model_validate_json(answer.text))
        except ValidationError:
            dropped.append(Dropped("signature", f"{doc.doc_id} p{n}", "bad answer"))
    return reader.record
