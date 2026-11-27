"""``shaped``: an Acceptance Criterion a Test Step row may be submitted with (audit #341, M3)."""

from traceq.assembly.rows import shaped
from traceq.traceability.values import ExclusiveRange, Number, OneOf, Present, Range, Text


def test_a_range_with_its_bounds_the_right_way_round_is_shaped() -> None:
    assert shaped(Range(min=20, max=70, unit="rpm"))
    assert shaped(Range(min=20, max=20, unit="rpm"))


def test_a_range_with_one_open_bound_is_shaped() -> None:
    assert shaped(Range(min=20, unit="rpm"))
    assert shaped(Range(max=70, unit="rpm"))


def test_a_range_whose_lower_bound_is_above_its_upper_bound_is_not_shaped() -> None:
    assert not shaped(Range(min=70, max=20, unit="rpm"))


def test_the_other_shapes_are_shaped_and_free_text_or_nothing_is_not() -> None:
    assert shaped(Number(value=3, unit="mm"))
    assert shaped(OneOf(allowed=("a", "b")))
    assert shaped(Present())
    assert not shaped(Text(value="turret runs smoothly"))
    assert not shaped(None)


def test_an_exclusive_range_is_shaped_unless_its_bounds_are_inverted() -> None:
    assert shaped(ExclusiveRange(max=0.8, max_exclusive=True, unit="um"))
    assert not shaped(ExclusiveRange(min=70, max=20, min_exclusive=True, unit="rpm"))
