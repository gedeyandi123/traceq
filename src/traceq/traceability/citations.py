"""The citation check: a claim is used only when its quote is printed on the cited page.

Deterministic and stricter than a fuzzy match: after whitespace and Unicode normalisation
the quote must appear verbatim in the page text, be at most ``MAX_QUOTE`` characters, and
state the value it is meant to support. A claim that fails is dropped before use, so the
fabrication floor is enforced by code, not by the prompt (spec #29).

On a scanned page the page text is what the OCR model read, so a quote can be on it and still
not be printed: a misread handwritten id is quoted verbatim. A quote that rests on an entry
the model scored below ``UNCERTAIN_OCR`` is uncertain, and a claim that needs it is dropped
like one whose quote is not on the page (#78).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from traceq.documents import Page, normalise
from traceq.traceability.values import Number, OneOf, Present, Range, Text, Value

MAX_QUOTE = 200
UNCERTAIN_OCR = 0.9
"""An OCR entry scored below this is an uncertain reading. On the dev corpus scans the only
entry below it is a misread handwritten id (0.817); the next lowest is 0.918 (#78)."""
UNCERTAIN = "uncertain OCR reading"
"""The reason a claim resting on one is dropped."""


@dataclass(frozen=True)
class Citation:
    doc: str
    rev: int
    page: int
    """1-based."""
    quote: str


def quote_on_page(quote: str, page_text: str) -> bool:
    q = normalise(quote)
    return bool(q) and len(q) <= MAX_QUOTE and q in normalise(page_text)


def _grouped(digits: str, sep: str) -> str:
    head = len(digits) % 3 or 3
    return sep.join([digits[:head], *(digits[i : i + 3] for i in range(head, len(digits), 3))])


def number_forms(x: float) -> set[str]:
    """How a number may be printed: grouped or not, ``.`` or ``,`` as decimal point."""
    plain = f"{x:.10g}"
    sign = "-" if plain.startswith("-") else ""
    whole, _, frac = plain.lstrip("-").partition(".")
    forms = {plain, plain.replace(".", ",")}
    for thousands, decimal in ((".", ","), (",", ".")):
        forms.add(sign + _grouped(whole, thousands) + (decimal + frac if frac else ""))
    return forms


def _contains_number(text: str, x: float) -> bool:
    return any(
        re.search(rf"(?<![\d.,]){re.escape(form)}(?![\d]|[.,]\d)", text) for form in number_forms(x)
    )


def value_in_quote(value: Value, quote: str) -> bool:
    """Every number of the value, or every allowed text, appears in the quote."""
    text = normalise(quote)
    match value:
        case Range(min=lo, max=hi):
            return all(_contains_number(text, b) for b in (lo, hi) if b is not None)
        case Number(value=x):
            return _contains_number(text, x)
        case OneOf(allowed=allowed):
            return all(normalise(a) in text for a in allowed)
        case Text(value=t):
            return normalise(t) in text
        case Present():
            return True


def verified(c: Citation, pages: list[str], value: Value | None = None) -> bool:
    if not 1 <= c.page <= len(pages) or not quote_on_page(c.quote, pages[c.page - 1]):
        return False
    return value is None or value_in_quote(value, c.quote)


def _spans(pattern: str, text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


def uncertain(c: Citation, pages: Sequence[Page]) -> bool:
    """Whether the quote rests on an uncertain OCR reading: every place it occurs on the
    cited page overlaps an entry scored below ``UNCERTAIN_OCR``. A page without OCR entries
    (born-digital, a spreadsheet) is never uncertain."""
    if not 1 <= c.page <= len(pages):
        return False
    page = pages[c.page - 1]
    low = {normalise(o.text) for o in page.ocr if o.score < UNCERTAIN_OCR} - {""}
    q = normalise(c.quote)
    if not low or not q:
        return False
    text = normalise(page.text)
    # Entries are joined by whitespace in the page text, so each one stands between spaces.
    # The page keeps no offsets per entry: every place a low entry's text stands is taken as
    # uncertain, which can only drop more, never keep a misreading.
    misread = [s for e in low for s in _spans(rf"(?<!\S){re.escape(e)}(?!\S)", text)]
    quoted = _spans(rf"(?={re.escape(q)})", text)
    return bool(quoted) and all(
        any(i < end and start < i + len(q) for start, end in misread) for i, _ in quoted
    )
