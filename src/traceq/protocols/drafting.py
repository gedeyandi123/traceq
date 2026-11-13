"""Drafted IQ/OQ Test Steps: one LLM call per requirement that needs one, then the AC
validator.

A requirement needs a draft when the vendor did not prove it (``partial``, ``site_only``,
``gap``, ``conflict``, or no Coverage at all). The ``vendor_reuse`` run setting (default
true) decides whether a ``covered_by_vendor`` requirement also gets one: with false every
requirement does, and its draft is marked as one reuse could save. Coverage is the same
either way.

The model sees the requirement, its verified value and Coverage, the Evidence linked to it,
and the pages those cite. It drafts the description, method and instrument, and proposes an
AC with the place it copied it from; ``validate_acceptance`` keeps the AC only when that
citation is verified, else empties and flags it. Every draft is an AI Finding: a proposal a
human accepts, edits or rejects (ADR 0002).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from traceq.ai import LLM, Request
from traceq.ai.port import sha256
from traceq.documents import Corpus
from traceq.protocols.acceptance import Acceptance, Sources, validate_acceptance
from traceq.protocols.prompts import DRAFT
from traceq.traceability import Citation, Dropped, Linked, Requirement, Traceability, Value
from traceq.traceability.coverage import CoverageClass
from traceq.traceability.values import Number, OneOf, Present, Range, Text


def needs_draft(coverage: CoverageClass | None, *, vendor_reuse: bool) -> bool:
    return coverage != "covered_by_vendor" or not vendor_reuse


@dataclass(frozen=True)
class Draft:
    id: str
    requirement: Requirement
    coverage: CoverageClass | None
    description: str
    method: str
    instrument: str | None
    acceptance: Acceptance

    @property
    def saved_by_reuse(self) -> bool:
        """Drafted only because ``vendor_reuse`` is false: reuse of the vendor's Evidence
        could save it."""
        return self.coverage == "covered_by_vendor"


@dataclass
class Drafts:
    vendor_reuse: bool = True
    drafts: list[Draft] = field(default_factory=list[Draft])
    dropped: list[Dropped] = field(default_factory=list[Dropped])


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Acceptance(_Answer):
    kind: Literal["range", "number", "one_of", "text", "present", "none"]
    min: float | None
    max: float | None
    number: float | None
    unit: str | None
    allowed: list[str]
    text: str | None


class _Source(_Answer):
    doc: str
    rev: int
    page: int
    quote: str


class _Draft(_Answer):
    description: str
    method: str
    instrument: str | None
    acceptance: _Acceptance
    acceptance_source: _Source | None


def _value(a: _Acceptance) -> Value | None:
    """The proposed AC, or ``None`` when the answer proposes none or an incomplete one."""
    match a.kind:
        case "range" if a.min is not None or a.max is not None:
            return Range(min=a.min, max=a.max, unit=a.unit or "")
        case "number" if a.number is not None:
            return Number(value=a.number, unit=a.unit or "")
        case "one_of" if a.allowed:
            return OneOf(allowed=tuple(a.allowed))
        case "text" if a.text:
            return Text(value=a.text)
        case "present":
            return Present()
        case _:
            return None


def _cited(t: Traceability, r: Requirement, linked: Linked | None) -> list[Citation]:
    """The URS sentence and value, then the Evidence and design facts."""
    claim = t.values.get(r.id)
    found = [r.citation] if claim is None else [r.citation, claim.citation]
    if linked is not None:
        found += [s.citation for s in linked.steps] + [d.citation for d in linked.rows]
    return found


def _prompt(t: Traceability, r: Requirement, linked: Linked | None, sources: Sources) -> str:
    claim = t.values.get(r.id)
    pages = dict.fromkeys((c.doc, c.rev, c.page) for c in _cited(t, r, linked))
    return json.dumps(
        {
            "requirement": {
                "id": r.id,
                "text": r.text,
                "value": None if claim is None else claim.value.model_dump(mode="json"),
                "value_citation": None
                if claim is None
                else {
                    "doc": claim.citation.doc,
                    "rev": claim.citation.rev,
                    "page": claim.citation.page,
                    "quote": claim.citation.quote,
                },
                "coverage": None if linked is None else linked.coverage.coverage,
                "reason": None if linked is None else linked.coverage.reason,
            },
            "evidence": [
                {
                    "doc": s.protocol.doc,
                    "step": s.step,
                    "test": s.test,
                    "acceptance": s.acceptance,
                    "observed": s.observed,
                    "failure": v.failure,
                }
                for s, v in zip(
                    linked.steps if linked else (),
                    linked.coverage.verdicts if linked else (),
                    strict=True,
                )
            ],
            "sources": [
                {"doc": doc, "rev": rev, "page": page, "text": sources[(doc, rev)][page - 1]}
                for doc, rev, page in pages
            ],
        },
        ensure_ascii=False,
        indent=1,
    )


def draft(corpus: Corpus, llm: LLM, t: Traceability, *, vendor_reuse: bool = True) -> Drafts:
    out = Drafts(vendor_reuse)
    todo = [
        (r, linked)
        for r in t.requirements
        if needs_draft(
            None if (linked := t.linked.get(r.id)) is None else linked.coverage.coverage,
            vendor_reuse=vendor_reuse,
        )
    ]
    docs = {
        (c.doc, c.rev): d
        for r, linked in todo
        for c in _cited(t, r, linked)
        if (d := corpus.find(c.doc, c.rev)) is not None
    }
    sources: Sources = {k: corpus.pages(d) for k, d in docs.items()}
    requests = [
        Request(
            DRAFT,
            _prompt(t, r, linked, sources),
            sha256(",".join(sorted({docs[c.doc, c.rev].sha256 for c in _cited(t, r, linked)}))),
        )
        for r, linked in todo
    ]
    answers = llm.complete(requests)
    for (r, linked), answer in zip(todo, answers, strict=True):
        try:
            a = _Draft.model_validate_json(answer.text)
        except ValidationError:
            out.dropped.append(Dropped("test_step", r.id, "bad answer"))
            continue
        s = a.acceptance_source
        citation = None if s is None else Citation(s.doc, s.rev, s.page, s.quote)
        proposed = _value(a.acceptance)
        given = {(c.doc, c.rev) for c in _cited(t, r, linked)}
        acceptance = validate_acceptance(proposed, citation, {k: sources[k] for k in given})
        if proposed is not None and acceptance.flag is not None:
            out.dropped.append(Dropped("acceptance", r.id, acceptance.flag))
        out.drafts.append(
            Draft(
                id=f"TS-{r.id}",
                requirement=r,
                coverage=None if linked is None else linked.coverage.coverage,
                description=a.description,
                method=a.method,
                instrument=a.instrument,
                acceptance=acceptance,
            )
        )
    return out
