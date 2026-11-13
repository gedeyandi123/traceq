"""Printed limits and readings, read by code: ``≥ 100 kN``, ``20–60 rpm``, ``0.5 % FS``.

Numbers follow the document's convention through the ambiguity rule; a reading that may be
two numbers is ``None`` here (the ambiguity rule asks for confirmation instead). A text that
is not a number with a unit (``Present and functional``, ``SS 304``) is ``None`` too: no
rule judges it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from traceq.documents import normalise
from traceq.traceability.ambiguity import read_number

_NUM = r"\d+(?:[.,]\d+)*"
_LIMIT = re.compile(
    rf"^(?P<op>≥|>=|≤|<=|>|<)?\s*(?P<a>{_NUM})\s*(?:(?:–|—|-|to|s/d)\s*(?P<b>{_NUM}))?"
    r"\s*(?P<unit>.*)$"
)


@dataclass(frozen=True)
class Interval:
    lo: float | None
    hi: float | None
    unit: str
    strict_lo: bool = False
    strict_hi: bool = False

    def contains(self, x: float) -> bool:
        above = self.lo is None or (x > self.lo if self.strict_lo else x >= self.lo)
        below = self.hi is None or (x < self.hi if self.strict_hi else x <= self.hi)
        return above and below

    def bounds(self) -> tuple[float, ...]:
        return tuple(b for b in (self.lo, self.hi) if b is not None)


def _unit(text: str) -> str:
    return normalise(text).casefold()


def _number(token: str, language: str, reference: Sequence[float]) -> float | None:
    x = read_number(token, language, reference)
    return x if isinstance(x, float) else None


def parse(printed: str, language: str, reference: Sequence[float] = ()) -> Interval | None:
    """A limit (``≥ 100 kN``, ``20–60 rpm``) or a reading (``96 kN``: lo = hi)."""
    m = _LIMIT.match(normalise(printed))
    if m is None:
        return None
    a = _number(m["a"], language, reference)
    b = None if m["b"] is None else _number(m["b"], language, reference)
    if a is None or (m["b"] is not None and b is None):
        return None
    unit = _unit(m["unit"])
    match m["op"]:
        case "≥" | ">=":
            return Interval(a, None, unit)
        case ">":
            return Interval(a, None, unit, strict_lo=True)
        case "≤" | "<=":
            return Interval(None, a, unit)
        case "<":
            return Interval(None, a, unit, strict_hi=True)
        case _:
            return Interval(a, a if b is None else b, unit)


def outside(acceptance: str, observed: str, language: str) -> bool | None:
    """Whether a printed reading lies outside its printed Acceptance Criterion. ``None`` when
    either cannot be read as a number with the same unit."""
    limit = parse(acceptance, language)
    if limit is None:
        return None
    reading = parse(observed, language, limit.bounds())
    if reading is None or reading.unit != limit.unit:
        return None
    return not all(limit.contains(x) for x in reading.bounds())
