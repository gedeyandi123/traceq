"""Dates stored as day offsets from T0.

World data never holds absolute dates. ``"T0"``, ``"T0-400d"`` and ``"T0+30d"`` are
resolved against a T0 chosen at render time: fixed for the eval corpus, the reset day
for the demo corpus (design section 4, "Dates").
"""

from __future__ import annotations

import datetime as dt
import re
from functools import total_ordering
from typing import Annotated, Any

from pydantic import PlainSerializer, PlainValidator

_PATTERN = re.compile(r"^T0(?:([+-])(\d+)d)?$")


@total_ordering
class RelDate:
    """A date expressed as a whole number of days relative to T0."""

    __slots__ = ("days",)

    def __init__(self, days: int) -> None:
        self.days = days

    @classmethod
    def parse(cls, text: str) -> RelDate:
        match = _PATTERN.fullmatch(text.strip())
        if not match:
            raise ValueError(f"expected 'T0', 'T0+Nd' or 'T0-Nd', got {text!r}")
        sign, num = match.groups()
        days = 0 if num is None else int(num)
        return cls(-days if sign == "-" else days)

    def resolve(self, t0: dt.date) -> dt.date:
        return t0 + dt.timedelta(days=self.days)

    def __str__(self) -> str:
        if self.days == 0:
            return "T0"
        return f"T0{'+' if self.days > 0 else '-'}{abs(self.days)}d"

    def __repr__(self) -> str:
        return f"RelDate({self})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RelDate) and self.days == other.days

    def __lt__(self, other: RelDate) -> bool:
        return self.days < other.days

    def __hash__(self) -> int:
        return hash(self.days)


def _coerce(value: Any) -> RelDate:
    if isinstance(value, RelDate):
        return value
    if isinstance(value, str):
        return RelDate.parse(value)
    raise ValueError(f"expected a T0 offset string, got {type(value).__name__}")


Offset = Annotated[RelDate, PlainValidator(_coerce), PlainSerializer(str, return_type=str)]
"""Pydantic field type for a T0 offset; serialises back to ``"T0-400d"`` form."""
