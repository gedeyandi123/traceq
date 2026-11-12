"""Decision table for ``covered_by_vendor`` (design section 6).

Fixture values here are test inputs only, not world data.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from traceq_dataset.coverage import IncomparableError, classify, meets
from traceq_dataset.schema import (
    CoverageClass,
    DesignEvidence,
    NumberObs,
    OneOfSpec,
    RangeSpec,
    Requirement,
    TestEvidence,
    Vendor,
    VendorProtocol,
)

C = CoverageClass

VENDORS = {
    "v-full": Vendor.model_validate(
        {
            "id": "v-full",
            "name": "Vendor A",
            "assessment": {"assessed_on": "T0-200d", "scope": ["mechanical", "control"]},
        }
    ),
    "v-mech": Vendor.model_validate(
        {
            "id": "v-mech",
            "name": "Vendor B",
            "assessment": {"assessed_on": "T0-200d", "scope": ["mechanical"]},
        }
    ),
    "v-none": Vendor(id="v-none", name="Vendor C"),
}


def _protocol(doc_id: str, stage: str, vendor: str, approved: str | None, executed: str):
    return VendorProtocol.model_validate(
        {
            "doc_id": doc_id,
            "stage": stage,
            "vendor": vendor,
            "site_approved_on": approved,
            "executed_on": executed,
        }
    )


PROTOCOLS = {
    p.doc_id: p
    for p in [
        _protocol("FAT-OK", "FAT", "v-full", "T0-100d", "T0-90d"),
        _protocol("FAT-UNAPPROVED", "FAT", "v-full", None, "T0-90d"),
        _protocol("FAT-LATE", "FAT", "v-full", "T0-80d", "T0-90d"),
        _protocol("FAT-MECH", "FAT", "v-mech", "T0-100d", "T0-90d"),
        _protocol("FAT-NONE", "FAT", "v-none", "T0-100d", "T0-90d"),
        _protocol("SAT-OK", "SAT", "v-full", "T0-20d", "T0-10d"),
    ]
}


def _req(**overrides: Any) -> Requirement:
    data: dict[str, Any] = {
        "id": "URS-TEST-001",
        "text": "speed adjustable",
        "param": "speed",
        "spec": {"type": "range", "min": 10, "max": 80, "unit": "rpm"},
        "source": {
            "kind": "site_decision",
            "ref": "test fixture",
            "rationale": "fixture",
            "drafted_by": "human",
        },
        "scope": "control",
        "transport_sensitive": False,
        "intended_coverage": "gap",
    }
    data.update(overrides)
    return Requirement.model_validate(data)


def _step(protocol: str, observed: dict[str, Any], result: str = "pass", step: str = "S1"):
    return TestEvidence.model_validate(
        {
            "step": step,
            "protocol": protocol,
            "requirement": "URS-TEST-001",
            "observed": observed,
            "recorded_result": result,
        }
    )


FULL = {"type": "range", "min": 10, "max": 80, "unit": "rpm"}
SHORT = {"type": "range", "min": 10, "max": 60, "unit": "rpm"}


def _classify(req: Requirement, tests=(), designs=()) -> CoverageClass:
    return classify(req, tests, designs, PROTOCOLS, VENDORS).coverage


def test_covered_when_all_four_conditions_hold() -> None:
    assert _classify(_req(), [_step("FAT-OK", FULL)]) is C.COVERED_BY_VENDOR


def test_gap_without_any_step() -> None:
    assert _classify(_req()) is C.GAP


def test_steps_for_other_requirements_are_ignored() -> None:
    other = _step("FAT-OK", FULL).model_copy(update={"requirement": "URS-TEST-999"})
    assert _classify(_req(), [other]) is C.GAP


def test_site_only_wins_over_vendor_steps() -> None:
    assert _classify(_req(site_only=True), [_step("FAT-OK", FULL)]) is C.SITE_ONLY


def test_conflict_wins_over_everything() -> None:
    req = _req(spec={"type": "one_of", "allowed": ["SS 316L"]}, site_only=True)
    cert = DesignEvidence.model_validate(
        {
            "doc_id": "MC-1",
            "requirement": req.id,
            "observed": {"type": "text", "value": "SS 304"},
        }
    )
    assert _classify(req, designs=[cert]) is C.CONFLICT


def test_matching_design_fact_is_not_conflict() -> None:
    req = _req(spec={"type": "one_of", "allowed": ["SS 316L"]}, site_only=True)
    cert = DesignEvidence.model_validate(
        {
            "doc_id": "MC-1",
            "requirement": req.id,
            "observed": {"type": "text", "value": "SS 316L"},
        }
    )
    assert _classify(req, designs=[cert]) is C.SITE_ONLY


@pytest.mark.parametrize(
    ("protocol", "reason"),
    [
        ("FAT-NONE", "condition 1"),  # vendor never assessed
        ("FAT-MECH", "condition 1"),  # 'control' outside assessed scope
        ("FAT-UNAPPROVED", "condition 2"),
        ("FAT-LATE", "condition 2"),  # approved after execution
    ],
)
def test_vendor_and_approval_failures_are_partial(protocol: str, reason: str) -> None:
    result = classify(_req(), [_step(protocol, FULL)], [], PROTOCOLS, VENDORS)
    assert result.coverage is C.PARTIAL
    assert reason in result.reason


def test_condition_order_reports_first_failure() -> None:
    # Unassessed vendor and short range: condition 1 is reported, not condition 3.
    result = classify(_req(), [_step("FAT-NONE", SHORT)], [], PROTOCOLS, VENDORS)
    assert "condition 1" in result.reason
    assert "condition 3" not in result.reason


def test_short_range_is_partial() -> None:
    result = classify(_req(), [_step("FAT-OK", SHORT)], [], PROTOCOLS, VENDORS)
    assert result.coverage is C.PARTIAL
    assert "condition 3" in result.reason


def test_transport_sensitive_needs_sat() -> None:
    req = _req(transport_sensitive=True)
    fat_only = classify(req, [_step("FAT-OK", FULL)], [], PROTOCOLS, VENDORS)
    assert fat_only.coverage is C.PARTIAL
    assert "condition 4" in fat_only.reason
    assert _classify(req, [_step("FAT-OK", FULL), _step("SAT-OK", FULL)]) is C.COVERED_BY_VENDOR


def test_out_of_limit_value_marked_pass_does_not_prove() -> None:
    req = _req(spec={"type": "range", "max": 80, "unit": "rpm"})
    bad = _step("FAT-OK", {"type": "number", "value": 85, "unit": "rpm"}, result="pass")
    result = classify(req, [bad], [], PROTOCOLS, VENDORS)
    assert result.coverage is C.PARTIAL
    assert "does not meet the URS" in result.reason


def test_one_good_step_is_enough() -> None:
    steps = [_step("FAT-UNAPPROVED", FULL, step="S1"), _step("FAT-OK", FULL, step="S2")]
    assert _classify(_req(), steps) is C.COVERED_BY_VENDOR


def test_single_reading_proves_one_sided_limit() -> None:
    req = _req(spec={"type": "range", "max": 80, "unit": "dB"})
    step = _step("FAT-OK", {"type": "number", "value": 75, "unit": "dB"})
    assert _classify(req, [step]) is C.COVERED_BY_VENDOR


def test_unit_mismatch_is_an_error_not_a_label() -> None:
    with pytest.raises(IncomparableError, match="unit"):
        meets(RangeSpec(min=10, max=80, unit="rpm"), NumberObs(value=50, unit="Hz"))


def test_kind_mismatch_is_an_error() -> None:
    with pytest.raises(IncomparableError):
        meets(OneOfSpec(allowed=("SS 316L",)), NumberObs(value=316, unit="grade"))


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "range", "unit": "rpm"},
        {"type": "range", "min": 80, "max": 10, "unit": "rpm"},
        {"type": "one_of", "allowed": []},
    ],
)
def test_invalid_specs_rejected(spec: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _req(spec=spec)


def test_requirement_id_format_enforced() -> None:
    with pytest.raises(ValidationError):
        _req(id="REQ-1")


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        _req(colour="blue")
