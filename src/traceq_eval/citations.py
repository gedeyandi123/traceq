"""Deterministic citation check (design section 9, "Citations"); no LLM judge.

A citation holds when its document and page exist in the corpus, its quote is found in the
page text by fuzzy match (ratio ≥ 0.9), and the value it claims appears inside the quote.

Page text is what is printed: for a scan, the born-digital render behind the pixels (a
system reads the scan by OCR, and the fuzzy match absorbs small OCR slips); for a
spreadsheet, page *n* is sheet *n* with its cell values in row order.
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

from openpyxl import load_workbook

from traceq_dataset.corpus import Corpus, DocKey
from traceq_dataset.render import fmt_number
from traceq_dataset.validate import page_texts

MIN_RATIO = 0.9
MAX_QUOTE = 200

_SPACE = re.compile(r"\s+")


def norm(text: str) -> str:
    """NFKC and collapsed whitespace; case and punctuation stay (the quote is verbatim)."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def partial_ratio(needle: str, haystack: str) -> float:
    """Best ``SequenceMatcher`` ratio of ``needle`` against any window of ``haystack`` of
    the same length, with windows aligned on matching blocks (as fuzzywuzzy does)."""
    a, b = norm(needle), norm(haystack)
    if not a or not b:
        return 0.0
    if a in b:
        return 1.0
    if len(a) >= len(b):
        return SequenceMatcher(None, a, b, autojunk=False).ratio()
    best = 0.0
    for i, j, _ in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        start = max(0, min(j - i, len(b) - len(a)))
        window = b[start : start + len(a)]
        best = max(best, SequenceMatcher(None, a, window, autojunk=False).ratio())
    return best


# --- Values inside a quote ------------------------------------------------------------


def _number_forms(x: float) -> set[str]:
    """How a number may be printed: grouped or not, ``.`` or ``,`` as decimal point."""
    plain = f"{x:.10g}"
    return {fmt_number(x, "id"), fmt_number(x, "en"), plain, plain.replace(".", ",")}


def _contains_number(text: str, x: float) -> bool:
    return any(
        re.search(rf"(?<![\d.,]){re.escape(form)}(?![\d]|[.,]\d)", text)
        for form in _number_forms(x)
    )


def value_tokens(value: Mapping[str, Any]) -> list[str | float]:
    """What must be in the quote: each number of a range or measurement, each allowed text.
    A ``present`` value has nothing to find."""
    match value["type"]:
        case "range":
            return [value[b] for b in ("min", "max") if value.get(b) is not None]
        case "number":
            return [value["value"]]
        case "one_of":
            return list(value["allowed"])
        case "text":
            return [value["value"]]
    return []


def value_in_quote(value: Mapping[str, Any], quote: str) -> bool:
    text = norm(quote)
    return all(
        _contains_number(text, t) if isinstance(t, int | float) else norm(t) in text
        for t in value_tokens(value)
    )


# --- Verdicts -------------------------------------------------------------------------


class Status(StrEnum):
    VERIFIED = "verified"
    """Quote found on the page and, if the citation claims a value, the value is in it."""
    VALUE_NOT_IN_QUOTE = "value_not_in_quote"
    """Quote found, but it does not state the claimed value: unsupported, not fabricated."""
    TOO_LONG = "too_long"
    """Quote longer than 200 characters: invalid, not fabricated."""
    UNKNOWN_DOCUMENT = "unknown_document"
    UNKNOWN_PAGE = "unknown_page"
    QUOTE_NOT_FOUND = "quote_not_found"


FABRICATED = frozenset({Status.UNKNOWN_DOCUMENT, Status.UNKNOWN_PAGE, Status.QUOTE_NOT_FOUND})
"""Statuses that count against the gate "fabricated citation" (floor 0)."""


@dataclass(frozen=True)
class Verdict:
    status: Status
    ratio: float

    @property
    def found(self) -> bool:
        """The quote is on the cited page (whatever it says about the value)."""
        return self.status in {Status.VERIFIED, Status.VALUE_NOT_IN_QUOTE}

    @property
    def fabricated(self) -> bool:
        return self.status in FABRICATED


class PageTexts:
    """Printed text per page of every document of a corpus, read lazily."""

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus
        self._cache: dict[DocKey, list[str]] = {}

    def __contains__(self, doc: DocKey) -> bool:
        return doc in self.corpus.rendered

    def pages(self, doc: DocKey) -> list[str]:
        if doc not in self._cache:
            rendered = self.corpus.rendered[doc]
            if rendered.format == "xlsx":
                wb = load_workbook(io.BytesIO(rendered.data), read_only=True)
                self._cache[doc] = [
                    norm(
                        " ".join(
                            str(c)
                            for row in ws.iter_rows(values_only=True)
                            for c in row
                            if c is not None
                        )
                    )
                    for ws in wb.worksheets
                ]
            else:
                self._cache[doc] = page_texts(rendered.pdf)
        return self._cache[doc]

    def check(self, doc: str, rev: int, page: int, quote: str, value: Mapping | None) -> Verdict:
        key = (doc, rev)
        if key not in self:
            return Verdict(Status.UNKNOWN_DOCUMENT, 0.0)
        pages = self.pages(key)
        if not 1 <= page <= len(pages):
            return Verdict(Status.UNKNOWN_PAGE, 0.0)
        ratio = partial_ratio(quote, pages[page - 1])
        if ratio < MIN_RATIO:
            return Verdict(Status.QUOTE_NOT_FOUND, ratio)
        if len(quote) > MAX_QUOTE:
            return Verdict(Status.TOO_LONG, ratio)
        if value is not None and not value_in_quote(value, quote):
            return Verdict(Status.VALUE_NOT_IN_QUOTE, ratio)
        return Verdict(Status.VERIFIED, ratio)
