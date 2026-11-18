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
- Units compare by the system's own unit rule, as in Coverage (``coverage.comparable``): no
  conversion, so ``2 jam`` and ``120 menit`` are not compared.
"""

from __future__ import annotations

from dataclasses import dataclass

from traceq.review.printed import Limit, PrintedValue, Tolerance
from traceq.traceability.coverage import comparable
from traceq.traceability.values import Number, Text


@dataclass(frozen=True)
class Outcome:
    deviates: bool = False
    not_compared: str | None = None
    """Why the AC was not compared with the URS limit; ``None`` when it was."""


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


def _units(ac: Number | Limit, urs: Number | Limit) -> str | None:
    if comparable(urs, ac):
        return None
    return f"units do not compare ({ac.unit or 'none'} and {urs.unit or 'none'})"


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
        if (units := _units(value, nominal)) is not None:
            return Outcome(not_compared=units)
        return Outcome(deviates=value.value != nominal.value)
    assert isinstance(urs, Limit)
    if urs.min is not None and urs.max is not None:
        return Outcome(not_compared="the URS states a two-sided range")
    if isinstance(ac, Tolerance):
        return Outcome(
            not_compared="the acceptance criterion is a tolerance around a nominal value"
        )
    accepted = Limit(min=ac.value, max=ac.value, unit=ac.unit) if isinstance(ac, Number) else ac
    if (units := _units(accepted, urs)) is not None:
        return Outcome(not_compared=units)
    if urs.min is not None:
        return Outcome(deviates=_below(accepted, urs))
    return Outcome(deviates=_above(accepted, urs))
