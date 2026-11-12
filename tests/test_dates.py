import datetime as dt

import pytest
from pydantic import BaseModel, ValidationError

from traceq_dataset.dates import Offset, RelDate


@pytest.mark.parametrize(
    ("text", "days"),
    [("T0", 0), ("T0-400d", -400), ("T0+30d", 30), (" T0+0d ", 0)],
)
def test_parse(text: str, days: int) -> None:
    assert RelDate.parse(text).days == days


@pytest.mark.parametrize("text", ["", "T1", "T0-4", "T0+-3d", "2026-03-12", "T0 - 4d"])
def test_parse_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="expected"):
        RelDate.parse(text)


def test_resolve_and_order() -> None:
    t0 = dt.date(2026, 3, 1)
    assert RelDate.parse("T0-1d").resolve(t0) == dt.date(2026, 2, 28)
    assert RelDate.parse("T0-20d") < RelDate.parse("T0") < RelDate.parse("T0+30d")


class _Doc(BaseModel):
    on: Offset


def test_pydantic_round_trip() -> None:
    doc = _Doc.model_validate({"on": "T0-400d"})
    assert doc.on == RelDate(-400)
    assert doc.model_dump() == {"on": "T0-400d"}


def test_pydantic_rejects_absolute_date() -> None:
    with pytest.raises(ValidationError):
        _Doc.model_validate({"on": dt.date(2026, 3, 1)})
