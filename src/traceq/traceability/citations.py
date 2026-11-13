"""The citation check: a claim is used only when its quote is printed on the cited page.

Deterministic and stricter than a fuzzy match: after whitespace and Unicode normalisation
the quote must appear verbatim in the page text, be at most ``MAX_QUOTE`` characters, and
state the value it is meant to support. A claim that fails is dropped before use, so the
fabrication floor is enforced by code, not by the prompt (spec #29).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from traceq.documents import normalise
from traceq.traceability.values import Number, OneOf, Present, Range, Text, Value

MAX_QUOTE = 200


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
