"""One table of units, for a code that compares a value in one unit with a value in another
(spec #375, ``unit_error``). The Acceptance Criterion of a Protocol Draft is compared with its
URS limit through it (``traceq.review.compare``), and the same table says when a unit is off by
a power of ten or by its dimension (``traceq.review.draft_rules``). No model decides here.

A unit is read as a product of atoms with exponents, over a denominator: ``m³/jam``,
``mm/s``, ``tablet/jam``. Each atom of the table has a dimension and a scale to its dimension's
base (exact, as a fraction, so ``1.5 cm`` is ``15 mm`` and not ``15.000000000000002``):

- SI atoms (``m``, ``g``, ``s``, ``N``, ``Pa``, ``bar``, ``L``, ``V``, ``A``, ``W``, ``Hz``) take
  an SI prefix (``k``, ``M``, ``G``, ``m``, ``µ``, ``n``, ``c``); they are case-sensitive
  (``mm`` is a millimetre, ``Mm`` a megametre).
- Time and rotation words (``menit``, ``jam``, ``detik``, ``hari``, ``h``, ``min``, ``rpm``) take
  none.
- Any other atom (``tablet``, ``stasiun``, ``dB(A)``) is *unknown*: it equals itself (case, a
  trailing plural ``s`` and brackets ignored, so ``dB(A)`` is ``dBA`` and ``tablets`` is
  ``tablet``) and nothing else. A unit with an unknown atom is never judged to be of another
  dimension: only units made entirely of known atoms are (``m²/jam`` against ``m³/jam``).

The table has no offset units (``°C`` is a known atom with no conversion) and no
dimensionless ratio (``%`` is unknown).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

_PREFIXES: dict[str, Fraction] = {
    "G": Fraction(10**9),
    "M": Fraction(10**6),
    "k": Fraction(10**3),
    "c": Fraction(1, 10**2),
    "m": Fraction(1, 10**3),
    "µ": Fraction(1, 10**6),
    "μ": Fraction(1, 10**6),
    "u": Fraction(1, 10**6),
    "n": Fraction(1, 10**9),
}

Dims = tuple[tuple[str, int], ...]
"""A dimension: the base names with their exponents, sorted, no zero exponent."""


def _dims(**exponents: int) -> Dims:
    return tuple(sorted(exponents.items()))


_SI: dict[str, tuple[Dims, Fraction]] = {
    "m": (_dims(length=1), Fraction(1)),
    "g": (_dims(mass=1), Fraction(1)),
    "s": (_dims(time=1), Fraction(1)),
    "N": (_dims(force=1), Fraction(1)),
    "Pa": (_dims(pressure=1), Fraction(1)),
    "bar": (_dims(pressure=1), Fraction(10**5)),
    "L": (_dims(length=3), Fraction(1, 10**3)),
    "l": (_dims(length=3), Fraction(1, 10**3)),
    "V": (_dims(voltage=1), Fraction(1)),
    "A": (_dims(current=1), Fraction(1)),
    "W": (_dims(power=1), Fraction(1)),
    "Hz": (_dims(time=-1), Fraction(1)),
}
"""SI atoms: dimension and scale to the base of that dimension (``g`` is the base of mass, so
``kg`` is 1000; ``m`` the base of length, so ``L`` is 1/1000 of ``m³``)."""

_WORDS: dict[str, tuple[Dims, Fraction]] = {
    "detik": (_dims(time=1), Fraction(1)),
    "sec": (_dims(time=1), Fraction(1)),
    "menit": (_dims(time=1), Fraction(60)),
    "min": (_dims(time=1), Fraction(60)),
    "jam": (_dims(time=1), Fraction(3600)),
    "h": (_dims(time=1), Fraction(3600)),
    "hr": (_dims(time=1), Fraction(3600)),
    "hari": (_dims(time=1), Fraction(86400)),
    "d": (_dims(time=1), Fraction(86400)),
    "rpm": (_dims(rev=1, time=-1), Fraction(1, 60)),
    "°c": (_dims(temperature=1), Fraction(1)),
}
"""Words and symbols that take no prefix, matched without case."""

_ATOM = re.compile(r"^(?P<atom>.+?)(?:\^?(?P<exp>-?\d)|(?P<sup>[²³]))?$")


@dataclass(frozen=True)
class Unit:
    dims: Dims
    scale: Fraction
    """One of this unit in the base of its dimensions (for unknown atoms, 1)."""
    known: bool
    """Every atom is in the table."""


def _atom(text: str) -> tuple[Dims, Fraction, bool]:
    """One atom without exponent: ``(dimension, scale, known)``."""
    if (hit := _SI.get(text)) is not None:
        return hit[0], hit[1], True
    if (hit := _WORDS.get(text.casefold())) is not None:
        return hit[0], hit[1], True
    if len(text) > 1 and text[0] in _PREFIXES and (hit := _SI.get(text[1:])) is not None:
        return hit[0], hit[1] * _PREFIXES[text[0]], True
    name = text.casefold().replace("(", "").replace(")", "")
    if len(name) >= 4 and name.endswith("s"):
        name = name[:-1]
    return ((f"?{name}", 1),), Fraction(1), False


def _factor(text: str) -> tuple[Dims, Fraction, bool]:
    m = _ATOM.match(text)
    assert m is not None  # any non-empty text matches
    exp = 1
    if m["exp"] is not None:
        exp = int(m["exp"])
    elif m["sup"] is not None:
        exp = 2 if m["sup"] == "²" else 3
    dims, scale, known = _atom(m["atom"])
    return tuple((n, e * exp) for n, e in dims), scale**exp, known


def parse_unit(text: str) -> Unit | None:
    """The unit as a product of atoms, or ``None`` for no unit at all."""
    text = unicodedata.normalize("NFKC", text).strip()
    if not text:
        return None
    exponents: dict[str, int] = {}
    scale, known = Fraction(1), True
    for i, part in enumerate(text.split("/")):
        sign = 1 if i == 0 else -1
        for piece in re.split(r"[·*]", part):
            if not piece.strip():
                continue
            dims, s, k = _factor(piece.strip())
            for name, e in dims:
                exponents[name] = exponents.get(name, 0) + sign * e
            scale *= s**sign
            known = known and k
    dims = tuple(sorted((n, e) for n, e in exponents.items() if e != 0))
    return Unit(dims, scale, known)


@dataclass(frozen=True)
class Relation:
    """How a value in one unit stands to a value in another."""

    kind: Literal["same", "scaled", "dimension", "unknown"]
    """``same``: one unit written two ways (``jam`` and ``h``, ``dB(A)`` and ``dBA``);
    ``scaled``: the same dimension at another scale (``cm`` and ``mm``); ``dimension``: two
    units of the table with other dimensions; ``unknown``: the table cannot say."""
    factor: Fraction = Fraction(1)
    """What a value of the first unit is multiplied by to be a value of the second (``same``
    and ``scaled``)."""

    @property
    def power_of_ten(self) -> bool:
        """The factor is 10 to a power other than 0: an SI prefix factor, the number right and
        the unit off."""
        if self.kind != "scaled":
            return False
        n, d = self.factor.numerator, self.factor.denominator
        return (d == 1 and _is_power_of_ten(n)) or (n == 1 and _is_power_of_ten(d))


def _is_power_of_ten(n: int) -> bool:
    while n % 10 == 0:
        n //= 10
    return n == 1


def relate(a: str, b: str) -> Relation:
    """How a value in unit ``a`` stands to a value in unit ``b``. Neither is empty."""
    x, y = parse_unit(a), parse_unit(b)
    if x is None or y is None:
        return Relation("unknown")
    if x.dims == y.dims:
        factor = x.scale / y.scale
        return Relation("same" if factor == 1 else "scaled", factor)
    return Relation("dimension" if x.known and y.known else "unknown")


def convert(value: float, factor: Fraction) -> float:
    """``value`` times ``factor``, rounded once (so ``1.5`` times 10 is ``15.0``)."""
    return float(Fraction(value) * factor)
