"""Tolerant span matching of requirement segmentation (design section 9, "Segmentation").

A URS that prints its requirement numbers (TP-201) is scored by id, as before. A URS that
does not (TP-202, prose and unnumbered tables) leaves the system to cut the text into
requirements and name them itself, so each answer is paired with an answer-key requirement
by the URS text the answer quotes:

- An answer's **span** is the characters its found citations quote on a URS page that holds
  a key requirement (quotes over 200 characters are invalid citations and do not count).
  A key requirement's span is its sentence on its source page.
- **Cover**: the share of the key requirement's characters the answer quotes.
- **Purity**: the share of the key-requirement text inside the answer's span that belongs to
  this requirement. Text that is no requirement (headings, table labels, intro sentences)
  counts for nothing, so quoting a row label with its cell, or running into an intro, costs
  nothing; quoting two requirements as one halves the purity.
- An answer is a candidate for a key requirement when cover ≥ ``COVER_MIN`` and purity >
  ``PURITY_OVER``. Purities add up to at most 1, so an answer is a candidate for one
  requirement at most; when several answers are candidates for one requirement, the best
  cover wins, then the best purity, then the earlier answer.

A **split** requirement therefore matches its larger part (if it quotes at least half) and
leaves the rest as an extra segment; a **merged** one matches the requirement that holds
more than half of its requirement text and leaves the other one missing, and an even merge
matches neither. An unmatched answer that quotes a URS
requirement page is an extra segment, a segmentation error rather than a made-up
requirement; one that does not is an unknown requirement, as with a wrong id.

Matched answers and the Test Steps tracing to them take the key's id, so every section
scores them as if the system had named them so. The thresholds are the owner's (ticket #44).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from traceq_eval.citations import MAX_QUOTE, MIN_RATIO, PageTexts, locate, norm
from traceq_eval.submission import RequirementAnswer, Submission

COVER_MIN = 0.5
"""An answer must quote at least this share of the key requirement's characters."""
PURITY_OVER = 0.5
"""More than this share of the requirement text an answer quotes must be this requirement's,
so an evenly merged pair matches neither requirement."""

UNMATCHED = "unmatched:"
"""Prefix for an unmatched answer whose own name is a key id, so it is not scored by id."""

Page = tuple[str, int, int]
Chars = dict[Page, set[int]]


@dataclass(frozen=True)
class Match:
    answer: str
    requirement: str
    cover: float
    purity: float


@dataclass(frozen=True)
class Alignment:
    """How the answers of a submission pair with span-matched key requirements."""

    requirements: int
    """Key requirements matched by span (their id is not printed on their source page)."""
    answers: int
    """Answers paired by span: every answer not named after an id-matched requirement."""
    matches: list[Match] = field(default_factory=list[Match])
    extra: list[str] = field(default_factory=list[str])
    """Unmatched answers that quote a URS requirement page, by their name after alignment."""


def align(
    sub: Submission, key: Mapping[str, list[dict[str, Any]]], pages: PageTexts
) -> tuple[Submission, Alignment | None]:
    """The submission with span-matched answers renamed to the key's ids, and the alignment.
    ``None`` when every key requirement prints its id: the submission is scored by id."""
    reqs = key["requirements.yaml"]
    by_span = [r for r in reqs if not _printed(r, pages)]
    if not by_span:
        return sub, None
    by_id = {r["id"] for r in reqs} - {r["id"] for r in by_span}
    span_ids = {r["id"] for r in by_span}
    answers = [a for a in sub.requirements if a.id not in by_id]

    key_chars = _key_chars(by_span, pages)
    urs_pages = {p for p, _ in key_chars.values()}
    answer_chars = {a.id: _answer_chars(a, urs_pages, pages) for a in answers}

    candidates: list[tuple[float, float, int, int, Match]] = []
    for ki, r in enumerate(by_span):
        page, k = key_chars[r["id"]]
        for ai, a in enumerate(answers):
            chars = answer_chars[a.id]
            overlap = len(chars.get(page, set()) & k)
            if not overlap:
                continue
            on_keys = sum(len(chars.get(p, set()) & c) for p, c in key_chars.values())
            cover, purity = overlap / len(k), overlap / on_keys
            if cover >= COVER_MIN and purity > PURITY_OVER:
                m = Match(a.id, r["id"], round(cover, 4), round(purity, 4))
                candidates.append((-cover, -purity, ki, ai, m))
    matches: list[Match] = []
    for *_, m in sorted(candidates, key=lambda c: c[:4]):
        if all(m.answer != x.answer and m.requirement != x.requirement for x in matches):
            matches.append(m)

    names = {m.answer: m.requirement for m in matches}

    def rename(rid: str) -> str:
        return names.get(rid, f"{UNMATCHED}{rid}" if rid in span_ids else rid)

    extra = sorted(rename(a.id) for a in answers if a.id not in names and answer_chars[a.id])

    renamed = sub.model_copy(
        update={
            "requirements": tuple(
                a.model_copy(update={"id": rename(a.id)}) for a in sub.requirements
            ),
            "test_steps": tuple(
                s.model_copy(update={"requirement": rename(s.requirement)}) for s in sub.test_steps
            ),
        }
    )
    return renamed, Alignment(len(by_span), len(answers), matches, extra)


def _printed(r: Mapping[str, Any], pages: PageTexts) -> bool:
    """The requirement's id is printed on its source page, so a system can name it."""
    src = r["source"]
    doc = (src["doc"], src["rev"])
    if doc not in pages:
        return False
    texts = pages.pages(doc)
    return 1 <= src["page"] <= len(texts) and r["id"] in norm(texts[src["page"] - 1])


def _key_chars(reqs: list[dict[str, Any]], pages: PageTexts) -> dict[str, tuple[Page, set[int]]]:
    """Each requirement's sentence on its source page; a sentence printed twice on a page
    takes the first occurrence no earlier requirement has taken."""
    out: dict[str, tuple[Page, set[int]]] = {}
    taken: dict[Page, set[int]] = {}
    for r in reqs:
        src = r["source"]
        page: Page = (src["doc"], src["rev"], src["page"])
        text, sentence = norm(pages.pages(page[:2])[page[2] - 1]), norm(r["text"])
        start = text.find(sentence)
        while start >= 0 and start in taken.get(page, set()):
            start = text.find(sentence, start + 1)
        if start < 0:
            raise ValueError(f"{r['id']}: requirement text not on its source page")
        chars = set(range(start, start + len(sentence)))
        taken.setdefault(page, set()).update(chars)
        out[r["id"]] = (page, chars)
    return out


def _answer_chars(a: RequirementAnswer, urs_pages: set[Page], pages: PageTexts) -> Chars:
    out: Chars = {}
    for c in a.citations:
        page: Page = (c.doc, c.rev, c.page)
        if page not in urs_pages or len(c.quote) > MAX_QUOTE:
            continue
        ratio, start, end = locate(c.quote, pages.pages(page[:2])[page[2] - 1])
        if ratio >= MIN_RATIO:
            out.setdefault(page, set()).update(range(start, end))
    return out
