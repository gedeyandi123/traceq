"""Acceptance Criterion shapes Execution judges exactly: an exclusive bound and a tolerance
(spec #375, ticket S4a3). Neither is ever coerced to an inclusive range; a stored ``range``
keeps its meaning."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from traceq.assembly.rows import exact_acceptance, shaped
from traceq.assembly.written import Acceptance, WrittenContent
from traceq.execution.results import (
    NumberResultValue,
    RecordAttemptRequest,
    _format_acceptance,  # pyright: ignore[reportPrivateUsage]
    judge,
)
from traceq.review.printed import Limit, read_printed
from traceq.review.printed import Tolerance as Printed
from traceq.traceability.ambiguity import Ambiguous
from traceq.traceability.values import ExclusiveRange, Range, Text, ToleranceBand


def _verdict(acceptance: Acceptance, x: float) -> str:
    req = RecordAttemptRequest(outcome_kind="value", value=NumberResultValue(value=x))
    return judge(acceptance, req)


def _exact(printed: str, language: str = "id") -> Acceptance | None:
    read = read_printed(printed, language)
    return exact_acceptance(None if isinstance(read, Ambiguous) else read)


def test_less_than_0_8_um_fails_at_0_8_and_passes_below() -> None:
    ac = _exact("Ra < 0,8 µm")
    assert ac == ExclusiveRange(max=0.8, max_exclusive=True, unit="µm")
    assert _verdict(ac, 0.8) == "fail"  # type: ignore[arg-type]
    assert _verdict(ac, 0.79) == "pass"  # type: ignore[arg-type]
    assert _verdict(ac, 0.81) == "fail"  # type: ignore[arg-type]


def test_a_strict_lower_bound_and_a_mixed_range() -> None:
    above = ExclusiveRange(min=5, min_exclusive=True, unit="kN")
    assert (_verdict(above, 5), _verdict(above, 5.1), _verdict(above, 4.9)) == (
        "fail",
        "pass",
        "fail",
    )
    mixed = ExclusiveRange(min=20, max=70, max_exclusive=True, unit="rpm")
    assert (_verdict(mixed, 20), _verdict(mixed, 70), _verdict(mixed, 69.9)) == (
        "pass",
        "fail",
        "pass",
    )


def test_an_exclusive_bound_is_never_an_inclusive_range() -> None:
    ac = exact_acceptance(Limit(max=0.8, max_exclusive=True, unit="µm"))
    assert not isinstance(ac, Range)
    inclusive = exact_acceptance(Limit(max=0.8, unit="µm"))
    assert inclusive == Range(max=0.8, unit="µm")
    assert _verdict(inclusive, 0.8) == "pass"  # type: ignore[arg-type]


def test_a_tolerance_in_percent_includes_its_ends() -> None:
    ac = _exact("380 V ± 10 %")
    assert ac == ToleranceBand(nominal=380, tolerance=10, tolerance_unit="%", unit="V")
    assert [_verdict(ac, x) for x in (342, 418, 341.99, 418.01, 380)] == [  # type: ignore[arg-type]
        "pass",
        "pass",
        "fail",
        "fail",
        "pass",
    ]


def test_a_tolerance_in_the_nominal_unit_is_absolute_and_exact_in_decimals() -> None:
    ac = ToleranceBand(nominal=0.3, tolerance=0.1, tolerance_unit="mm", unit="mm")
    # 0.3 - 0.1 and 0.3 + 0.1 are not exact in binary floats.
    assert (_verdict(ac, 0.2), _verdict(ac, 0.4), _verdict(ac, 0.41)) == ("pass", "pass", "fail")


def test_a_tolerance_in_another_unit_is_not_shaped() -> None:
    assert exact_acceptance(Printed(nominal=380, tolerance=2, tolerance_unit="A", unit="V")) is None
    with pytest.raises(ValidationError):
        ToleranceBand(nominal=380, tolerance=2, tolerance_unit="A", unit="V")


def test_text_and_a_lone_tolerance_are_not_shaped() -> None:
    assert exact_acceptance(Text(value="sesuai")) is None
    assert exact_acceptance(None) is None
    assert not shaped(Text(value="sesuai"))
    assert shaped(ExclusiveRange(max=1, max_exclusive=True, unit="mm"))


def test_exclusive_range_is_its_own_shape() -> None:
    with pytest.raises(ValidationError):
        ExclusiveRange(min=1, max=2, unit="mm")  # no strict bound: that is a range
    with pytest.raises(ValidationError):
        ExclusiveRange(max_exclusive=True, min=1, unit="mm")  # strict bound without a value


def test_a_written_step_may_carry_the_new_shapes_and_checks_their_unit() -> None:
    base = {"description": "d", "method": "m"}
    ok = WrittenContent.model_validate(
        {
            **base,
            "acceptance": {
                "type": "exclusive_range",
                "max": 1,
                "max_exclusive": True,
                "unit": "mm",
            },
        }
    )
    assert isinstance(ok.acceptance, ExclusiveRange)
    with pytest.raises(ValidationError):
        WrittenContent.model_validate(
            {
                **base,
                "acceptance": {
                    "type": "exclusive_range",
                    "max": 1,
                    "max_exclusive": True,
                    "unit": " ",
                },
            }
        )
    with pytest.raises(ValidationError):
        WrittenContent.model_validate(
            {
                **base,
                "acceptance": {
                    "type": "tolerance",
                    "nominal": 1,
                    "tolerance": 1,
                    "tolerance_unit": "%",
                    "unit": " ",
                },
            }
        )


def test_stored_copies_and_results_are_unaffected() -> None:
    """A stored ``range`` still loads as a range with the same meaning, and dumps unchanged."""
    adapter: TypeAdapter[Acceptance] = TypeAdapter(Acceptance)
    stored = {"type": "range", "min": None, "max": 0.8, "unit": "µm"}
    loaded = adapter.validate_python(stored)
    assert isinstance(loaded, Range)
    assert json.dumps(loaded.model_dump(mode="json"), sort_keys=True) == json.dumps(
        stored, sort_keys=True
    )
    assert _verdict(loaded, 0.8) == "pass"
    # The new shapes do not accept a range's old fields under the old tag.
    with pytest.raises(ValidationError):
        adapter.validate_python({**stored, "max_exclusive": True})


def test_deviation_text_states_the_new_shapes() -> None:
    assert _format_acceptance(ExclusiveRange(max=0.8, max_exclusive=True, unit="µm")) == "< 0.8 µm"
    assert (
        _format_acceptance(ToleranceBand(nominal=380, tolerance=10, tolerance_unit="%", unit="V"))
        == "380.0 V ± 10.0 %"
    )
