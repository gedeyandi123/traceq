"""The URS completeness check (spec #105, K5): what of a URS did not become a requirement.

No LLM. It runs on the pages of the URS the run read, after the citation check:

- **Printed numbers missed.** The shape of a requirement number is learned from the ids the
  model returned as printed (``Requirement.printed``), each digit run generalised, so
  ``URS-AB12-001`` gives ``URS-AB<digits>-<digits>``. Ids the system made up for unnumbered
  requirements never teach it. Every token of that shape on the pages that is not the id of
  a kept requirement is missed, so a number whose requirement the citation check dropped is
  missed too. A URS whose requirements carry no printed number gets ``not_applicable``, not
  "0 missed".
- **Unquoted text.** Each line of a page that no kept requirement's quote (its segmentation
  quote or its value quote) touches, adjacent such lines merged into one entry. A kept
  requirement's value quotes count as quoted text: a line only its value quote touches is
  not listed.

Limit: the shape separates only numbers that look unlike other text. A URS numbered ``1``,
``2`` or ``4.1`` makes every such number on its pages a candidate, so the list over-reports.
That shows more and hides nothing.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal

from traceq.documents import normalise
from traceq.traceability.citations import Citation

_DIGITS = re.compile(r"\d+")
_BEFORE = r"(?<![0-9A-Za-z])(?<![0-9A-Za-z][.\-])"
_AFTER = r"(?![0-9A-Za-z]|[.\-][0-9A-Za-z])"


@dataclass(frozen=True)
class Missed:
    number: str
    page: int
    """The first page it is printed on."""


@dataclass(frozen=True)
class Unquoted:
    page: int
    text: str
    """Adjacent unquoted lines, joined by newlines."""


@dataclass(frozen=True)
class UrsCompleteness:
    doc: str
    rev: int
    numbers: Literal["checked", "not_applicable"]
    found: int
    """Distinct printed numbers of the learned shape on the pages."""
    missed: tuple[Missed, ...]
    unquoted: tuple[Unquoted, ...]


def _shape(printed: Sequence[str]) -> re.Pattern[str] | None:
    shapes = sorted(
        {
            r"\d+".join(re.escape(part) for part in _DIGITS.split(p))
            for p in (normalise(x) for x in printed)
            if p
        },
        key=lambda s: (-len(s), s),
    )
    if not shapes:
        return None
    return re.compile(f"{_BEFORE}(?:{'|'.join(shapes)}){_AFTER}")


def _missed(
    pages: Sequence[str], printed: Sequence[str], kept: Collection[str]
) -> tuple[int, tuple[Missed, ...]]:
    shape = _shape(printed)
    if shape is None:
        return 0, ()
    first: dict[str, int] = {}
    for n, text in enumerate(pages, 1):
        for m in shape.finditer(normalise(text)):
            first.setdefault(m[0], n)
    ids = {normalise(k) for k in kept}
    return len(first), tuple(Missed(x, n) for x, n in first.items() if x not in ids)


def _unquoted(page: int, text: str, quotes: Sequence[str]) -> list[Unquoted]:
    lines = [normalise(x) for x in text.splitlines()]
    spans: list[tuple[int, int]] = []
    at = 0
    for line in lines:
        spans.append((at, at + len(line)))
        at += len(line) + 1
    joined = " ".join(lines)
    covered: list[tuple[int, int]] = []
    for q in quotes:
        start = joined.find(q)
        while q and start >= 0:
            covered.append((start, start + len(q)))
            start = joined.find(q, start + 1)
    out: list[Unquoted] = []
    run: list[str] = []
    for line, (lo, hi) in zip(lines, spans, strict=True):
        if line and not any(s < hi and lo < e for s, e in covered):
            run.append(line)
            continue
        if run:
            out.append(Unquoted(page, "\n".join(run)))
            run = []
    if run:
        out.append(Unquoted(page, "\n".join(run)))
    return out


def check(
    doc: str,
    rev: int,
    pages: Sequence[str],
    *,
    printed: Sequence[str],
    kept: Collection[str],
    quotes: Sequence[Citation],
) -> UrsCompleteness:
    """``pages``: the URS as the run read it. ``printed``: every id the model returned as
    printed on it, kept or dropped. ``kept``: the ids of the requirements the run kept.
    ``quotes``: the citations of the kept requirements and their values."""
    found, missed = _missed(pages, printed, kept)
    unquoted = [
        u
        for n, text in enumerate(pages, 1)
        for u in _unquoted(
            n,
            text,
            [normalise(c.quote) for c in quotes if (c.doc, c.rev, c.page) == (doc, rev, n)],
        )
    ]
    return UrsCompleteness(
        doc=doc,
        rev=rev,
        numbers="checked" if any(normalise(p) for p in printed) else "not_applicable",
        found=found,
        missed=missed,
        unquoted=tuple(unquoted),
    )
