"""The ambiguity rule: a value that reads two ways is flagged for confirmation, never guessed
(design section 6, "Ambiguous values"; scenario S7).

Numbers. A single ``.`` or ``,`` followed by exactly three digits reads as a thousands
separator or as a decimal point. Where it is the decimal point of the document's language
(``.`` in English, ``,`` in Indonesian), a writer of the other convention may have meant
thousands, so ``1.500 rpm`` on an English form is 1500 or 1.5. Where it is the document's
grouping separator (``120.000`` in an Indonesian URS) it reads one way. A reading is dropped
only when a reference value (the URS value) makes it implausible: off by a factor of 100 or
more while the other reading is within a factor of 10. Otherwise the value is ambiguous.

Dates. ``03/04/2026`` is 3 April or 4 March: two numeric fields that are both valid months
and differ are ambiguous. ``22-Jan-2026``, ``29/10/2025`` and ISO dates read one way.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Ambiguous[T]:
    readings: tuple[T, ...]


DECIMAL_POINT = {"en": ".", "id": ","}
_NUMBER = re.compile(r"(?<![\d.,])\d+(?:[.,]\d+)*")


def _parse(token: str, decimal: str) -> float:
    if "." in token and "," in token:
        decimal = token[max(token.rfind("."), token.rfind(","))]
    elif token.count(decimal) > 1:
        return float(token.replace(decimal, ""))
    grouping = "," if decimal == "." else "."
    return float(token.replace(grouping, "").replace(decimal, "."))


def _decades_off(x: float, reference: Sequence[float]) -> float:
    lo, hi = min(reference), max(reference)
    if x <= 0 or lo <= 0:
        return math.inf
    if x < lo:
        return math.log10(lo / x)
    if x > hi:
        return math.log10(x / hi)
    return 0.0


def read_number(
    printed: str, language: str, reference: Sequence[float]
) -> float | Ambiguous[float] | None:
    """The first number printed, read by the document's convention."""
    m = _NUMBER.search(printed)
    if m is None:
        return None
    token = m[0]
    decimal = DECIMAL_POINT.get(language, ".")
    seps = [c for c in token if c in ".,"]
    if seps != [decimal] or len(token) - token.index(decimal) - 1 != 3:
        return _parse(token, decimal)
    whole, frac = token.split(decimal)
    readings = (float(whole + frac), float(f"{whole}.{frac}"))
    if reference:
        off = [_decades_off(r, reference) for r in readings]
        for keep, drop in ((0, 1), (1, 0)):
            if off[keep] < 1 and off[drop] >= 2:
                return readings[keep]
    return Ambiguous(readings)


def parse_date(printed: str) -> dt.date | Ambiguous[dt.date] | None:
    text = printed.strip()
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return dt.datetime.strptime(text, "%d-%b-%Y").date()
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
    if m is None:
        return None
    a, b, year = int(m[1]), int(m[2]), int(m[3])
    try:
        if a <= 12 and b <= 12 and a != b:
            return Ambiguous((dt.date(year, b, a), dt.date(year, a, b)))
        if a > 12:
            return dt.date(year, b, a)
        if b > 12:
            return dt.date(year, a, b)
        return dt.date(year, b, a)
    except ValueError:
        return None
