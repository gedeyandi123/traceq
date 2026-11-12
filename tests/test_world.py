"""Sources, Equipment cross-references, pending values, and the TP-201 world file."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from traceq_dataset.coverage import PendingError, classify
from traceq_dataset.schema import (
    Equipment,
    Requirement,
    Source,
    number_forms,
)
from traceq_dataset.world import TARGET_SHARE, load

TP201 = Path(__file__).parents[1] / "world" / "tp201.yaml"

QUOTED = {
    "kind": "regulation",
    "ref": "Permenaker 5/2018, Lampiran II",
    "url": "https://example.org/permenaker-5-2018.pdf",
    "quote": "NAB kebisingan 85 dBA untuk 8 jam per hari",
    "accessed": "2026-11-12",
}


# --- Source ---------------------------------------------------------------------------


def test_quoted_source_complete() -> None:
    assert Source.model_validate(QUOTED).quote


@pytest.mark.parametrize("missing", ["url", "quote", "accessed"])
def test_quoted_source_needs_url_quote_accessed(missing: str) -> None:
    data = {k: v for k, v in QUOTED.items() if k != missing}
    with pytest.raises(ValidationError):
        Source.model_validate(data)


def test_quote_length_capped() -> None:
    with pytest.raises(ValidationError):
        Source.model_validate({**QUOTED, "quote": "x" * 201})


SITE = {
    "kind": "site_decision",
    "ref": "VMP §5",
    "rationale": "room height 3 m",
    "drafted_by": "llm",
}


def test_site_decision_needs_rationale() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        Source.model_validate({k: v for k, v in SITE.items() if k != "rationale"})
    assert Source.model_validate(SITE).rationale


def test_site_decision_needs_drafted_by() -> None:
    with pytest.raises(ValidationError, match="drafted_by"):
        Source.model_validate({k: v for k, v in SITE.items() if k != "drafted_by"})


@pytest.mark.parametrize("field", ["drafted_by", "reviewed_by"])
def test_quoted_source_is_not_drafted_or_reviewed(field: str) -> None:
    value = "llm" if field == "drafted_by" else "owner"
    with pytest.raises(ValidationError, match="copied"):
        Source.model_validate({**QUOTED, field: value})


def test_site_decision_may_add_supporting_quote() -> None:
    data = {**QUOTED, **SITE, "rationale": "below the legal limit"}
    assert Source.model_validate(data).judged


def test_url_and_quote_go_together() -> None:
    with pytest.raises(ValidationError, match="together"):
        Source.model_validate({**SITE, "url": QUOTED["url"]})


def test_pending_source_needs_nothing() -> None:
    assert Source.model_validate({"kind": "pending"}).kind == "pending"


# --- Value in quote -------------------------------------------------------------------


def _req(spec: dict[str, Any], source: dict[str, Any]) -> Requirement:
    return Requirement.model_validate(
        {
            "id": "URS-TP201-029",
            "text": "Kebisingan maksimal {max} dBA.",
            "param": "noise_level",
            "spec": spec,
            "source": source,
            "scope": "mechanical",
            "intended_coverage": "site_only",
        }
    )


def test_quoted_value_must_appear_in_quote() -> None:
    assert _req({"type": "range", "max": 85, "unit": "dBA"}, QUOTED)
    with pytest.raises(ValidationError, match="not found in source quote"):
        _req({"type": "range", "max": 80, "unit": "dBA"}, QUOTED)


def test_site_decision_value_need_not_appear_in_quote() -> None:
    source = {**QUOTED, **SITE, "rationale": "stricter than the legal limit"}
    assert _req({"type": "range", "max": 80, "unit": "dBA"}, source)


@pytest.mark.parametrize(
    ("value", "form"), [(0.5, "0,5"), (0.5, "0.5"), (1000, "1.000"), (1000, "1,000"), (85, "85")]
)
def test_number_forms(value: float, form: str) -> None:
    assert form in number_forms(value)


# --- Equipment ------------------------------------------------------------------------


def _raw() -> dict[str, Any]:
    import yaml

    return yaml.safe_load(TP201.read_text(encoding="utf-8"))


def test_unknown_requirement_in_test_step_rejected() -> None:
    raw = _raw()
    raw["tests"][0]["requirement"] = "URS-TP201-999"
    with pytest.raises(ValidationError, match="unknown requirement"):
        Equipment.model_validate(raw)


def test_duplicate_requirement_rejected() -> None:
    raw = _raw()
    raw["requirements"].append(raw["requirements"][0])
    with pytest.raises(ValidationError, match="duplicate requirement"):
        Equipment.model_validate(raw)


def test_scenario_target_must_exist() -> None:
    raw = _raw()
    raw["scenarios"][0]["targets"] = ["NOPE"]
    with pytest.raises(ValidationError, match="unknown target"):
        Equipment.model_validate(raw)


def test_classify_refuses_pending_values() -> None:
    raw = _raw()
    raw["tests"][1]["observed"] = {"type": "pending", "expected": "range", "unit": "rpm"}
    eq = Equipment.model_validate(raw)
    req = next(r for r in eq.requirements if r.id == "URS-TP201-002")
    with pytest.raises(PendingError):
        classify(req, eq.tests, eq.designs, {p.doc_id: p for p in eq.protocols}, {})


# --- TP-201 world file (design sections 5-7) ------------------------------------------


@pytest.fixture(scope="module")
def tp201() -> Equipment:
    return load(TP201)


def test_tp201_requirement_count(tp201: Equipment) -> None:
    assert 35 <= len(tp201.requirements) <= 40


def test_tp201_data_integrity_requirements(tp201: Equipment) -> None:
    assert 4 <= sum(r.scope == "data_integrity" for r in tp201.requirements) <= 6


def test_tp201_coverage_distribution_near_target(tp201: Equipment) -> None:
    n = len(tp201.requirements)
    counts = Counter(r.intended_coverage for r in tp201.requirements)
    for cls, share in TARGET_SHARE.items():
        assert abs(counts[cls] - share * n) <= 1.5, cls


def test_tp201_has_the_eight_v0_scenarios(tp201: Equipment) -> None:
    assert [s.id for s in tp201.scenarios] == [f"S{i}" for i in range(1, 9)]


def test_unreviewed_lists_judged_values_until_signed_off() -> None:
    raw = _raw()
    first = next(r for r in raw["requirements"] if r["source"]["kind"] == "site_decision")
    before = {r.id for r in Equipment.model_validate(raw).unreviewed()}
    assert first["id"] in before
    first["source"]["reviewed_by"] = "practitioner"
    after = {r.id for r in Equipment.model_validate(raw).unreviewed()}
    assert after == before - {first["id"]}


def test_tp201_filled_requirements_agree_with_intent(tp201: Equipment) -> None:
    """Every requirement whose values are filled must classify as intended."""
    protocols = {p.doc_id: p for p in tp201.protocols}
    vendors = {tp201.vendor.id: tp201.vendor}
    checked = 0
    for r in tp201.requirements:
        try:
            got = classify(r, tp201.tests, tp201.designs, protocols, vendors)
        except PendingError:
            continue
        checked += 1
        assert got.coverage is r.intended_coverage, f"{r.id}: {got.reason}"
    assert checked > 0
