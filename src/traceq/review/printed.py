"""Limits as a site document prints them, read by code (spec #196, "Draft reading").

A Protocol Draft prints an Acceptance Criterion the way its writer would (``minimal 100 kN``,
``maks. 25 mm``, ``20 s/d 70 rpm``, ``Ra < 0,8 µm``, ``380 V ± 10 %``), and a URS states a
limit inside a sentence (``Diameter tablet maksimal 25 mm.``). Both are read here, by the same
code, from the printed text: the model only copies the text and quotes it.

This is a parse path of its own. The out-of-limit rule on vendor records keeps reading with
``traceq.review.limits``, whose formats and behaviour do not change.

- The first limit printed is the value: a further clause after it (``380 V ± 10 %, 3 fase``)
  is not part of it. Digits inside an id (``URS-XY100-004``, ``OQ-05``) are not a number.
- ``minimal``, ``min.``, ``tidak kurang dari``, ``≥`` bound from below; ``maksimal``,
  ``maks.``, ``tidak lebih dari``, ``≤`` from above; ``>``, ``<``, ``lebih dari``, ``kurang
  dari`` are strict bounds; ``minimal`` and ``maksimal`` are not.
- ``a–b``, ``a - b``, ``a s/d b``, ``a sampai b`` is a two-sided range; a lone number is a
  single number; ``n unit ± t unit`` is a nominal value with a tolerance; ``± t unit`` alone
  (or after ``maks.``) is a deviation of at most ``t``.
- A number glued to a letter (``316L``) is not a number. The unit is the first word after
  the number (``stasiun`` in ``36 stasiun punch``), with a qualifier written in capitals
  after ``%`` (``% FS``); it is kept as printed (``m³``, ``µm``).
- A number that reads two ways is ``Ambiguous`` (the ambiguity rule): never guessed. Text
  without a number is ``Text``; a number in a form not listed above is ``None``.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from traceq.traceability.ambiguity import Ambiguous, read_number
from traceq.traceability.values import Number, Range, Text


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limit(Range):
    """A limit as printed: either bound may be strict (``< 0,8 µm``)."""

    min_exclusive: bool = False
    max_exclusive: bool = False


class Tolerance(_Model):
    """A nominal value with a tolerance: ``380 V ± 10 %``."""

    type: Literal["tolerance"] = "tolerance"
    nominal: float
    tolerance: float
    tolerance_unit: str
    unit: str

    @model_validator(mode="after")
    def _positive(self) -> Tolerance:
        if self.tolerance < 0:
            raise ValueError("a tolerance is not negative")
        return self


PrintedValue = Limit | Number | Tolerance | Text
"""An Acceptance Criterion or URS limit as read: the shapes of submission ``draft_steps``."""

_GE = (
    r"tidak\s+kurang\s+dari|sekurang-kurangnya|paling\s+sedikit|minimal|minimum"
    r"|min\.|min\b|at\s+least|≥|>="
)
_LE = (
    r"tidak\s+lebih\s+dari|paling\s+banyak|maksimal|maksimum|maks\.|maks\b"
    r"|max\.|max\b|at\s+most|≤|<="
)
_GT = r"lebih\s+dari|more\s+than|>"
_LT = r"kurang\s+dari|less\s+than|<"
_NUM = r"\d+(?:[.,]\d+)*"
_EXPR = re.compile(
    rf"(?:(?P<op>{_GE}|{_LE}|{_GT}|{_LT})\s*)?"
    r"(?P<pm>±\s*)?"
    rf"(?<![\w.,/-])(?P<a>{_NUM})(?![^\W_])"
    rf"(?:\s*(?:–|—|-|s/d|sampai(?:\s+dengan)?|to)\s*(?P<b>{_NUM})(?![^\W_]))?"
    r"(?:\s*(?P<unit>(?-i:%\s*[A-Z]{1,3}\b)|[^\s\d,;:±]+))?"
    rf"(?:\s*±\s*(?P<t>{_NUM})\s*(?P<tu>%|[^\s\d,;:±]+)?)?",
    re.IGNORECASE,
)


def _op(word: str | None) -> str | None:
    if word is None:
        return None
    for name, pattern in (("ge", _GE), ("le", _LE), ("gt", _GT), ("lt", _LT)):
        if re.fullmatch(pattern, word, re.IGNORECASE):
            return name
    return None


def _spaced(text: str) -> str:
    """Collapsed whitespace only: NFKC would print ``m³`` as ``m3`` and ``µ`` as ``μ``."""
    return " ".join(text.split())


def _unit(text: str | None) -> str:
    if text is None:
        return ""
    unit = " ".join(text.split())
    return unit[:-1] if unit.endswith(".") else unit


def read_printed(
    printed: str, language: str, *, ignore: tuple[str, ...] = ()
) -> PrintedValue | Ambiguous[float] | None:
    """The first limit ``printed`` states. ``ignore``: text left out first (the requirement's
    own id in a URS quote)."""
    text = _spaced(printed)
    for s in ignore:
        text = text.replace(_spaced(s), " ")
    m = _EXPR.search(text)
    if m is None:
        return Text(value=_spaced(printed))
    tokens = [x for x in (m["a"], m["b"], m["t"]) if x is not None]
    numbers = [read_number(x, language) for x in tokens]
    if any(isinstance(x, Ambiguous) for x in numbers):
        return next(x for x in numbers if isinstance(x, Ambiguous))
    values = [x for x in numbers if isinstance(x, float)]
    if len(values) != len(tokens):
        return None
    a = values[0]
    op, unit = _op(m["op"]), _unit(m["unit"])
    if m["t"] is not None:
        if op is not None or m["pm"] is not None or m["b"] is not None:
            return None
        return Tolerance(
            nominal=a, tolerance=values[-1], tolerance_unit=_unit(m["tu"]) or unit, unit=unit
        )
    if m["b"] is not None:
        b = values[1]
        if op is not None or m["pm"] is not None or b < a:
            return None
        return Limit(min=a, max=b, unit=unit)
    if m["pm"] is not None:
        return Limit(max=a, unit=unit) if op in (None, "le") else None
    match op:
        case "ge":
            return Limit(min=a, unit=unit)
        case "gt":
            return Limit(min=a, min_exclusive=True, unit=unit)
        case "le":
            return Limit(max=a, unit=unit)
        case "lt":
            return Limit(max=a, max_exclusive=True, unit=unit)
        case _:
            return Number(value=a, unit=unit)
