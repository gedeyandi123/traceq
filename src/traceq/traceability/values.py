"""Normalised values a requirement or an observation states (submission schema version 1)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Range(_Model):
    """A required or tested range; either bound may be open."""

    type: Literal["range"] = "range"
    min: float | None = None
    max: float | None = None
    unit: str

    @model_validator(mode="after")
    def _bounds(self) -> Range:
        if self.min is None and self.max is None:
            raise ValueError("range needs at least one bound")
        return self


class ExclusiveRange(_Model):
    """A required range with at least one strict bound (``< 0,8 µm``): the bound itself fails.

    A member of the Acceptance Criterion shapes of its own, not a flag on ``Range``, so that
    a stored ``range`` keeps its meaning (spec #375, S4a3)."""

    type: Literal["exclusive_range"] = "exclusive_range"
    min: float | None = None
    max: float | None = None
    min_exclusive: bool = False
    max_exclusive: bool = False
    unit: str

    @model_validator(mode="after")
    def _bounds(self) -> ExclusiveRange:
        if self.min is None and self.max is None:
            raise ValueError("an exclusive range needs at least one bound")
        if (self.min_exclusive and self.min is None) or (self.max_exclusive and self.max is None):
            raise ValueError("a strict bound needs its value")
        if not (self.min_exclusive or self.max_exclusive):
            raise ValueError("an exclusive range has a strict bound; otherwise use a range")
        return self


class ToleranceBand(_Model):
    """A nominal value with a symmetric tolerance (``380 V ± 10 %``), the ends included.

    ``tolerance_unit`` is ``%`` (of the nominal value) or the nominal's own unit."""

    type: Literal["tolerance"] = "tolerance"
    nominal: float
    tolerance: float
    tolerance_unit: str
    unit: str

    @model_validator(mode="after")
    def _judgeable(self) -> ToleranceBand:
        if self.tolerance < 0:
            raise ValueError("a tolerance is not negative")
        if not tolerance_judgeable(self.tolerance_unit, self.unit):
            raise ValueError("a tolerance is in percent or in the unit of the nominal value")
        return self

    def limits(self) -> tuple[Decimal, Decimal]:
        """The lowest and highest value that meets it, exactly (decimal, not binary, floats)."""
        nominal, t = Decimal(repr(self.nominal)), Decimal(repr(self.tolerance))
        delta = abs(nominal) * t / 100 if self.tolerance_unit.strip() == "%" else t
        return nominal - delta, nominal + delta


def tolerance_judgeable(tolerance_unit: str, unit: str) -> bool:
    return tolerance_unit.strip() == "%" or (
        bool(unit.strip()) and tolerance_unit.strip() == unit.strip()
    )


class Number(_Model):
    type: Literal["number"] = "number"
    value: float
    unit: str


class OneOf(_Model):
    type: Literal["one_of"] = "one_of"
    allowed: tuple[str, ...] = Field(min_length=1)


class Text(_Model):
    type: Literal["text"] = "text"
    value: str


class Present(_Model):
    """A feature that must exist; ``value`` is set when an observation states it."""

    type: Literal["present"] = "present"
    value: bool | None = None


Value = Annotated[Range | Number | OneOf | Text | Present, Field(discriminator="type")]
