"""Comparing an Acceptance Criterion with its URS limit, both as read by code from the print
(spec #196, "Rules", ``ac_deviates_from_urs``). No model decides here.

- A one-sided URS limit (``minimal``, ``maks.``, ``>``, ``<``): the AC deviates when it
  accepts a value the URS rejects, strict and non-strict bounds respected. An equal or
  stricter AC does not deviate (a stricter AC is not a defect in 0.1.0).
- A URS single number (or a range with min = max, as the scorer's Rule B normalises it):
  only an AC that is a single number compares; a different value deviates. An AC range or
  tolerance around a nominal value is not compared: tolerance around a nominal waits for the
  practitioner session.
- A two-sided URS range is not compared: it may be a tolerance or a span the Equipment must
  be adjustable over, and telling them apart waits for the session. Nor is a tolerance, or
  text.
- Units compare through the system's one unit table (``traceq.traceability.units``): the AC
  is converted into the URS unit, so ``2 jam`` and ``120 menit`` compare, as do ``3 m`` and
  ``3.000 mm`` and ``dB(A)`` and ``dBA``. A unit the table cannot relate to the URS unit is not
  compared. A value without a unit compares as Coverage does (``coverage.comparable``).
- ``unit_error`` (spec #375): the printed number equals the URS number and the unit is off by an
  SI prefix factor (a power of ten: ``18 cm`` for ``18 mm``) or has other dimensions
  (``300 m²/jam`` for ``300 m³/jam``). It is reported beside the comparison, which still
  converts where it can: a caller that raises ``unit_error`` does not raise
  ``ac_deviates_from_urs`` for the same Test Step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from traceq.review.printed import Limit, PrintedValue, Tolerance
from traceq.traceability.coverage import comparable
from traceq.traceability.units import Relation, convert, relate
from traceq.traceability.values import Number, Text


@dataclass(frozen=True)
class UnitError:
    """The AC prints the URS number in a wrong unit."""

    kind: Literal["prefix", "dimension"]
    ac_unit: str
    urs_unit: str
    factor: str | None = None
    """For ``prefix``: what a value in the AC unit is multiplied by to be in the URS unit."""


@dataclass(frozen=True)
class Outcome:
    deviates: bool = False
    not_compared: str | None = None
    """Why the AC was not compared with the URS limit; ``None`` when it was."""
    unit_error: UnitError | None = None


def _single(v: PrintedValue) -> Number | None:
    match v:
        case Number():
            return v
        case Limit(min=lo, max=hi) if (
            lo is not None and lo == hi and not (v.min_exclusive or v.max_exclusive)
        ):
            return Number(value=lo, unit=v.unit)
        case _:
            return None


def _figures(v: Number | Limit) -> tuple[float, ...]:
    """The numbers a value prints: one for a number or a one-sided limit, two for a range."""
    if isinstance(v, Number):
        return (v.value,)
    return tuple(x for x in (v.min, v.max) if x is not None)


def _scaled(v: Number | Limit, rel: Relation, unit: str) -> Number | Limit:
    """``v`` as a value in ``unit``."""
    if rel.factor == 1:
        return v.model_copy(update={"unit": unit})
    if isinstance(v, Number):
        return Number(value=convert(v.value, rel.factor), unit=unit)
    return v.model_copy(
        update={
            "unit": unit,
            "min": None if v.min is None else convert(v.min, rel.factor),
            "max": None if v.max is None else convert(v.max, rel.factor),
        }
    )


def _align(
    ac: Number | Limit, urs: Number | Limit
) -> tuple[Number | Limit | None, UnitError | None, str | None]:
    """The AC as a value in the URS unit, the unit error if the AC prints the URS number in a
    wrong unit, and why the AC cannot be put in the URS unit (``None`` when it can)."""
    if not ac.unit.strip() or not urs.unit.strip():  # a count without a unit (#175)
        if comparable(urs, ac):
            return ac, None, None
        return None, None, f"units do not compare ({ac.unit or 'none'} and {urs.unit or 'none'})"
    rel = relate(ac.unit, urs.unit)
    same_number = _figures(ac) == _figures(urs)
    match rel.kind:
        case "same" | "scaled":
            slip = (
                UnitError("prefix", ac.unit, urs.unit, str(rel.factor))
                if same_number and rel.power_of_ten
                else None
            )
            return _scaled(ac, rel, urs.unit), slip, None
        case "dimension":
            slip = UnitError("dimension", ac.unit, urs.unit) if same_number else None
        case "unknown":
            slip = None
    return None, slip, f"units do not compare ({ac.unit} and {urs.unit})"


def _below(ac: Limit, urs: Limit) -> bool:
    """The AC accepts a value under the URS lower bound."""
    assert urs.min is not None
    if ac.min is None or ac.min < urs.min:
        return True
    return ac.min == urs.min and urs.min_exclusive and not ac.min_exclusive


def _above(ac: Limit, urs: Limit) -> bool:
    """The AC accepts a value over the URS upper bound."""
    assert urs.max is not None
    if ac.max is None or ac.max > urs.max:
        return True
    return ac.max == urs.max and urs.max_exclusive and not ac.max_exclusive


def compare(ac: PrintedValue, urs: PrintedValue) -> Outcome:
    if isinstance(urs, Text) or isinstance(ac, Text):
        return Outcome(not_compared="no number")
    if isinstance(urs, Tolerance):
        return Outcome(not_compared="the URS states a tolerance around a nominal value")
    if (nominal := _single(urs)) is not None:
        value = _single(ac)
        if value is None:
            return Outcome(
                not_compared="the URS states a single number; the acceptance criterion does not"
            )
        aligned, slip, why = _align(value, nominal)
        if aligned is None:
            return Outcome(not_compared=why, unit_error=slip)
        assert isinstance(aligned, Number)
        return Outcome(deviates=aligned.value != nominal.value, unit_error=slip)
    assert isinstance(urs, Limit)
    if urs.min is not None and urs.max is not None:
        return Outcome(not_compared="the URS states a two-sided range")
    if isinstance(ac, Tolerance):
        return Outcome(
            not_compared="the acceptance criterion is a tolerance around a nominal value"
        )
    aligned, slip, why = _align(ac, urs)
    if aligned is None:
        return Outcome(not_compared=why, unit_error=slip)
    if isinstance(aligned, Number):
        aligned = Limit(min=aligned.value, max=aligned.value, unit=aligned.unit)
    if urs.min is not None:
        return Outcome(deviates=_below(aligned, urs), unit_error=slip)
    return Outcome(deviates=_above(aligned, urs), unit_error=slip)
