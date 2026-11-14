"""Vendor Evidence: facts read from FAT/SAT protocols, datasheets and certificates, the links
the LLM proposes from each requirement to them, and the Coverage the decision table decides.

1. Facts: one call per page of each current vendor document reads its test steps (AC,
   observed result, pass/fail), its site approval and execution dates, and its design rows.
   A fact whose quote is not on the page, does not hold the printed value, or rests on an
   uncertain OCR reading (#78) is dropped.
   Numbers and dates are read from the printed text by code (the ambiguity rule), not from
   the model's reading.
2. Links: one call per requirement proposes which steps and design rows concern it,
   judges whether only the site can test it and whether transport can affect it, and names
   the area of the Vendor Assessment (``traceability.assessment``) it belongs to. An id or
   an area the model invents is dropped. The ``transport_sensitive`` bit is noisy: when it
   alone lets FAT steps cover a requirement, the ``transport`` prompt, which defines the
   bit by category, is asked ``TRANSPORT_VOTES`` times with the same user text, and any
   ``true`` (or unparsable) answer makes the requirement transport-sensitive (#88, #90).
3. Coverage: ``traceability.coverage.classify``. Condition 1 holds only when the named area
   is one the verified assessment lets the site rely on; with no assessment in the corpus it
   fails for every step.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from traceq.ai import LLM, Request
from traceq.ai.port import sha256
from traceq.documents import Corpus, CorpusDocument, Page, normalise
from traceq.traceability.ambiguity import Ambiguous, parse_date, read_number
from traceq.traceability.citations import (
    UNCERTAIN,
    Citation,
    quote_on_page,
    uncertain,
    value_in_quote,
    verified,
)
from traceq.traceability.coverage import (
    Coverage,
    Date,
    DesignFact,
    Observed,
    Protocol,
    RequirementFacts,
    Result,
    Stage,
    Step,
    classify,
)
from traceq.traceability.prompts import FACTS, LINK, TRANSPORT
from traceq.traceability.values import Number, Present, Range, Text, Value

if TYPE_CHECKING:
    from traceq.traceability.assessment import Area, Assessment

PROTOCOL_TYPES: dict[str, Stage] = {"fat": "FAT", "sat": "SAT"}
DESIGN_TYPES = ("datasheet", "material_certificate")
TRANSPORT_VOTES = 3
"""Answers to the ``transport`` request before FAT steps alone may cover a requirement
(#88, #90)."""


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Value(_Answer):
    kind: Literal["range", "number", "text", "present", "none"]
    min: float | None
    max: float | None
    number: float | None
    unit: str | None
    text: str | None
    present: bool | None


class _Date(_Answer):
    date: str
    quote: str


class _Step(_Answer):
    step: str
    test: str
    acceptance: str
    observed: str
    result: Literal["pass", "fail", "none"]
    value: _Value
    quote: str


class _Row(_Answer):
    name: str
    printed: str
    value: _Value
    quote: str


class _Facts(_Answer):
    site_approved_on: _Date | None
    executed_on: _Date | None
    steps: list[_Step]
    rows: list[_Row]


class _Link(_Answer):
    steps: list[str]
    rows: list[str]
    site_only: bool
    transport_sensitive: bool
    area: str | None


Claim = Literal[
    "requirement",
    "value",
    "step",
    "row",
    "date",
    "link",
    "signature",
    "calibration",
    "instrument",
    "deviation",
    "calculation",
    "required_document",
    "site_rule",
    "assessment",
    "test_step",
    "acceptance",
    "ai_finding",
]


@dataclass(frozen=True)
class Dropped:
    claim: Claim
    id: str
    reason: str


def _contains(printed: str, quote: str) -> bool:
    p = normalise(printed)
    return bool(p) and p in normalise(quote)


def _observation(v: _Value, printed: str, language: str) -> Observed | None:
    """The value as printed. A number is read from the print by the ambiguity rule."""
    match v.kind:
        case "number":
            x = read_number(printed, language)
            if isinstance(x, Ambiguous):
                return x
            return None if x is None else Number(value=x, unit=v.unit or "")
        case "range":
            if v.min is None and v.max is None:
                return None
            r = Range(min=v.min, max=v.max, unit=v.unit or "")
            return r if value_in_quote(r, printed) else None
        case "text":
            return Text(value=v.text) if v.text and _contains(v.text, printed) else None
        case "present":
            return None if v.present is None else Present(value=v.present)
        case "none":
            return None


@dataclass(frozen=True)
class StepFact:
    protocol: Protocol
    step: str
    test: str
    acceptance: str
    observed: str
    """As printed."""
    result: Result | None
    citation: Citation
    language: str
    value: _Value

    @property
    def id(self) -> str:
        return f"{self.protocol.doc}/{self.step}"

    def as_step(self) -> Step:
        observed = _observation(self.value, self.observed, self.language)
        return Step(self.protocol, self.step, observed, self.result)


@dataclass(frozen=True)
class RowFact:
    id: str
    name: str
    printed: str
    fact: DesignFact
    citation: Citation


@dataclass(frozen=True)
class Linked:
    """One requirement's Evidence, design facts and Coverage."""

    facts: RequirementFacts
    coverage: Coverage
    steps: tuple[StepFact, ...]
    """The Evidence, in the order of ``coverage.verdicts``."""
    rows: tuple[RowFact, ...]
    """The design facts compared with the URS value."""
    area: Area | None = None
    """The Vendor Assessment area named for the requirement, with its verified rating."""


_LinkInputs = tuple[Request, Sequence[StepFact], Sequence[RowFact]]
"""A requirement's first ``link`` request and the steps and rows its answer linked."""


@dataclass
class VendorFacts:
    steps: list[StepFact] = field(default_factory=list[StepFact])
    rows: list[RowFact] = field(default_factory=list[RowFact])
    read: list[CorpusDocument] = field(default_factory=list[CorpusDocument])
    not_read: list[CorpusDocument] = field(default_factory=list[CorpusDocument])


def _page_prompt(doc: CorpusDocument, page: int, text: str) -> str:
    return f"Document {doc.doc_id}, revision {doc.rev}, page {page}.\n\n<page>\n{text}\n</page>"


def _date(
    d: _Date | None, doc: CorpusDocument, page: int, pages: Sequence[Page], dropped: list[Dropped]
) -> Date:
    if d is None:
        return None
    c = Citation(doc.doc_id, doc.rev, page, d.quote)
    if not (quote_on_page(d.quote, pages[page - 1].text) and _contains(d.date, d.quote)):
        dropped.append(Dropped("date", f"{doc.doc_id} p{page}", "quote not on page"))
        return None
    if uncertain(c, pages):
        dropped.append(Dropped("date", f"{doc.doc_id} p{page}", UNCERTAIN))
        return None
    return parse_date(d.date)


def read_vendor_facts(corpus: Corpus, llm: LLM, dropped: list[Dropped]) -> VendorFacts:
    out = VendorFacts()
    for doc_type in (*PROTOCOL_TYPES, *DESIGN_TYPES):
        for doc in corpus.current(doc_type):
            if not corpus.readable(doc):
                out.not_read.append(doc)
                continue
            out.read.append(doc)
            read = corpus.read(doc)
            pages = [p.text for p in read]
            answers = llm.complete(
                [
                    Request(FACTS, _page_prompt(doc, n, text), doc.sha256)
                    for n, text in enumerate(pages, 1)
                ]
            )
            approved: Date = None
            executed: Date = None
            steps: list[tuple[int, _Step]] = []
            for n, answer in enumerate(answers, 1):
                try:
                    a = _Facts.model_validate_json(answer.text)
                except ValidationError:
                    dropped.append(Dropped("step", f"{doc.doc_id} p{n}", "bad answer"))
                    continue
                approved = approved or _date(a.site_approved_on, doc, n, read, dropped)
                executed = executed or _date(a.executed_on, doc, n, read, dropped)
                steps += [(n, s) for s in a.steps]
                for i, r in enumerate(a.rows if doc.type in DESIGN_TYPES else [], 1):
                    _add_row(out, doc, n, i, r, read, dropped)
            stage = PROTOCOL_TYPES.get(doc.type)
            if stage is None:
                continue
            protocol = Protocol(doc.doc_id, doc.rev, stage, approved, executed)
            for n, s in steps:
                c = Citation(doc.doc_id, doc.rev, n, s.quote)
                if not (
                    verified(c, pages)
                    and _contains(s.step, s.quote)
                    and _contains(s.observed, s.quote)
                ):
                    dropped.append(Dropped("step", f"{doc.doc_id}/{s.step}", "quote not on page"))
                    continue
                if uncertain(c, read):
                    dropped.append(Dropped("step", f"{doc.doc_id}/{s.step}", UNCERTAIN))
                    continue
                result = None if s.result == "none" else s.result
                out.steps.append(
                    StepFact(
                        protocol,
                        s.step,
                        s.test,
                        s.acceptance,
                        s.observed,
                        result,
                        c,
                        doc.language,
                        s.value,
                    )
                )
    return out


def _add_row(
    out: VendorFacts,
    doc: CorpusDocument,
    page: int,
    i: int,
    r: _Row,
    pages: Sequence[Page],
    dropped: list[Dropped],
) -> None:
    rid = f"{doc.doc_id}#p{page}.{i}"
    c = Citation(doc.doc_id, doc.rev, page, r.quote)
    value = _observation(r.value, r.printed, doc.language)
    if not (verified(c, [p.text for p in pages]) and _contains(r.printed, r.quote)):
        dropped.append(Dropped("row", rid, "quote not on page"))
    elif uncertain(c, pages):
        dropped.append(Dropped("row", rid, UNCERTAIN))
    elif value is None or isinstance(value, Ambiguous):
        dropped.append(Dropped("row", rid, "value not read from the print"))
    else:
        out.rows.append(RowFact(rid, r.name, r.printed, DesignFact(doc.doc_id, doc.rev, value), c))


def _link_prompt(
    rid: str, text: str, value: Value | None, facts: VendorFacts, areas: Sequence[str]
) -> str:
    return json.dumps(
        {
            "requirement": {
                "id": rid,
                "text": text,
                "value": None if value is None else value.model_dump(mode="json"),
            },
            "steps": [
                {"id": s.id, "test": s.test, "acceptance": s.acceptance, "observed": s.observed}
                for s in facts.steps
            ],
            "rows": [{"id": r.id, "name": r.name, "value": r.printed} for r in facts.rows],
            "areas": list(areas),
        },
        ensure_ascii=False,
        indent=1,
    )


def link(
    requirements: Sequence[tuple[str, str, Value | None]],
    facts: VendorFacts,
    urs_sha256: str,
    llm: LLM,
    dropped: list[Dropped],
    assessment: Assessment | None = None,
) -> dict[str, Linked]:
    """``requirements``: id, text and verified value of each requirement. ``assessment``:
    the verified Vendor Assessment, ``None`` when the corpus holds none. The model is
    offered every area it prints, never the rating."""
    shas = [urs_sha256, *(d.sha256 for d in facts.read)]
    if assessment is not None:
        shas.append(assessment.sha256)
    key = sha256(",".join(sorted(shas)))
    areas = [] if assessment is None else [a.name for a in assessment.areas]
    requests = [
        Request(LINK, _link_prompt(rid, text, value, facts, areas), key)
        for rid, text, value in requirements
    ]
    answers = llm.complete(requests)
    steps = {s.id: s for s in facts.steps}
    rows = {r.id: r for r in facts.rows}
    out: dict[str, Linked] = {}
    inputs: dict[str, _LinkInputs] = {}
    for (rid, _text, value), request, answer in zip(requirements, requests, answers, strict=True):
        try:
            a = _Link.model_validate_json(answer.text)
        except ValidationError:
            dropped.append(Dropped("link", rid, "bad answer"))
            a = _Link(steps=[], rows=[], site_only=False, transport_sensitive=True, area=None)
        for unknown in [i for i in a.steps if i not in steps] + [
            i for i in a.rows if i not in rows
        ]:
            dropped.append(Dropped("link", f"{rid} {unknown}", "unknown id"))
        linked_steps = [steps[i] for i in dict.fromkeys(a.steps) if i in steps]
        linked_rows = [rows[i] for i in dict.fromkeys(a.rows) if i in rows]
        area = None if assessment is None or a.area is None else assessment.area(a.area)
        if a.area is not None and area is None:
            dropped.append(Dropped("link", f"{rid} {a.area}", "unknown area"))
        scope = None if area is None else area.name
        req = RequirementFacts(rid, value, a.site_only, a.transport_sensitive, scope)
        out[rid] = _classify(req, linked_steps, linked_rows, area, assessment)
        inputs[rid] = (request, linked_steps, linked_rows)
    _vote_on_transport(out, inputs, llm, dropped, assessment)
    return out


def _classify(
    req: RequirementFacts,
    linked_steps: Sequence[StepFact],
    linked_rows: Sequence[RowFact],
    area: Area | None,
    assessment: Assessment | None,
) -> Linked:
    pairs = [(s, s.as_step()) for s in linked_steps]
    decision = None if assessment is None else assessment.decision
    coverage = classify(req, [p[1] for p in pairs], [r.fact for r in linked_rows], decision)
    used = [next(f for f, s in pairs if s is v.step) for v in coverage.verdicts]
    compared = [r for r in linked_rows if any(r.fact is d for d in coverage.design)]
    return Linked(req, coverage, tuple(used), tuple(compared), area)


def _fat_only(linked: Linked) -> bool:
    """``covered_by_vendor`` that rests on the ``transport_sensitive`` bit alone."""
    return (
        linked.coverage.coverage == "covered_by_vendor"
        and not linked.facts.transport_sensitive
        and not any(
            v.failure is None and v.step.protocol.stage == "SAT" for v in linked.coverage.verdicts
        )
    )


def _vote_on_transport(
    out: dict[str, Linked],
    inputs: dict[str, _LinkInputs],
    llm: LLM,
    dropped: list[Dropped],
    assessment: Assessment | None,
) -> None:
    """Ask each FAT-only ``covered_by_vendor`` requirement the ``transport`` prompt
    ``TRANSPORT_VOTES`` times, in one batch, with its ``link`` request's user text. Any
    answer that says ``transport_sensitive``, or does not parse, makes the requirement
    transport-sensitive. Only the bit is taken from the votes; the ``link`` answer's own
    bit only selects the candidates."""
    voters = [rid for rid, linked in out.items() if _fat_only(linked)]
    votes = [
        (rid, n, replace(inputs[rid][0], prompt=TRANSPORT, sample=n))
        for rid in voters
        for n in range(TRANSPORT_VOTES)
    ]
    if not votes:
        return
    answers = llm.complete([r for _, _, r in votes])
    sensitive: set[str] = set()
    for (rid, n, _), answer in zip(votes, answers, strict=True):
        try:
            if _Link.model_validate_json(answer.text).transport_sensitive:
                sensitive.add(rid)
        except ValidationError:
            dropped.append(Dropped("link", f"{rid} vote {n + 1}", "bad answer"))
            sensitive.add(rid)
    for rid in voters:
        if rid in sensitive:
            _, linked_steps, linked_rows = inputs[rid]
            req = replace(out[rid].facts, transport_sensitive=True)
            out[rid] = _classify(req, linked_steps, linked_rows, out[rid].area, assessment)
