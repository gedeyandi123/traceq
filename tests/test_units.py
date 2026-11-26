"""The one unit table (spec #375, S2b): units that are one unit written two ways, units that
differ by a power of ten, units of other dimensions, and units the table cannot judge."""

from __future__ import annotations

from fractions import Fraction

import pytest

from traceq.traceability.units import convert, parse_unit, relate


@pytest.mark.parametrize(
    ("a", "b", "factor"),
    [
        ("jam", "menit", 60),
        ("jam", "h", 1),
        ("menit", "min", 1),
        ("hari", "jam", 24),
        ("detik", "s", 1),
        ("cm", "mm", 10),
        ("m", "mm", 1000),
        ("µm", "mm", Fraction(1, 1000)),  # U+00B5
        ("μm", "mm", Fraction(1, 1000)),  # U+03BC
        ("kN", "N", 1000),
        ("kPa", "bar", Fraction(1, 100)),
        ("mbar", "Pa", 100),
        ("L", "m³", Fraction(1, 1000)),
        ("mL", "L", Fraction(1, 1000)),
        ("kg", "g", 1000),
        ("µg", "mg", Fraction(1, 1000)),
        ("m³/jam", "m³/h", 1),
        ("m3/h", "m³/jam", 1),
        ("m³/jam", "L/menit", Fraction(1000, 60)),
        ("mm/s", "m/s", Fraction(1, 1000)),
        ("dB(A)", "dBA", 1),
        ("tablet/jam", "tablets/h", 1),
        ("rpm", "rpm", 1),
        ("°C", "°C", 1),
        ("cm²", "mm²", 100),
        ("kV", "V", 1000),
    ],
)
def test_one_dimension_is_related_by_its_factor(a: str, b: str, factor: int | Fraction) -> None:
    rel = relate(a, b)
    assert rel.kind == ("same" if factor == 1 else "scaled")
    assert rel.factor == Fraction(factor)


@pytest.mark.parametrize(
    ("a", "b", "power"),
    [
        ("cm", "mm", True),
        ("N", "kN", True),
        ("µm", "mm", True),
        ("L", "m³", True),
        ("jam", "menit", False),  # 60
        ("hari", "jam", False),  # 24
        ("kPa", "bar", True),
        ("m³/jam", "L/menit", False),
    ],
)
def test_a_factor_that_is_a_power_of_ten_is_flagged_as_such(a: str, b: str, power: bool) -> None:
    assert relate(a, b).power_of_ten is power


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("m²/jam", "m³/jam"),
        ("rpm", "Hz"),
        ("mm", "bar"),
        ("kN", "kg"),
        ("°C", "mm"),
        ("mm/s", "mm"),
        ("V", "A"),
    ],
)
def test_units_of_the_table_with_other_dimensions_differ_in_dimension(a: str, b: str) -> None:
    assert relate(a, b).kind == "dimension"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("stasiun", "buah"),  # two units the table does not know
        ("stasiun", "mm"),  # one of them known
        ("% FS", "%"),
        ("dB", "dBA"),  # a weighting is not a conversion
        ("°C", "°F"),
        ("kali", "menit"),
    ],
)
def test_a_unit_the_table_does_not_know_is_never_judged_to_be_of_another_dimension(
    a: str, b: str
) -> None:
    assert relate(a, b).kind == "unknown"


def test_case_matters_for_si_atoms() -> None:
    assert relate("mm", "Mm").factor == Fraction(1, 10**9)
    assert relate("MN", "mN").factor == Fraction(10**9)


def test_a_unit_that_is_none_is_none() -> None:
    assert parse_unit("") is None and parse_unit("  ") is None


def test_conversion_is_rounded_once_not_per_step() -> None:
    assert convert(1.5, relate("cm", "mm").factor) == 15.0
    assert convert(0.1, relate("cm", "mm").factor) == 1.0
    assert convert(2, relate("jam", "menit").factor) == 120.0
    assert convert(7, relate("kN", "N").factor) == 7000.0
