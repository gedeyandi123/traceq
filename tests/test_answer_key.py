"""Answer key: derived from world data and the corpus, committed, and checked in CI."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import (
    FILES,
    TAXONOMY,
    AnswerKeyError,
    derive,
    dump,
    load_key,
    readings,
    scenarios_without_answer,
)
from traceq_dataset.corpus import Corpus, build_corpus, manifest
from traceq_dataset.schema import DefectType, Equipment
from traceq_dataset.validate import answer_key_problems
from traceq_dataset.world import load

ROOT = Path(__file__).parents[1]
TP201 = ROOT / "world" / "tp201.yaml"
KEY = ROOT / "answer_key" / "TP-201"


@pytest.fixture(scope="module")
def eq() -> Equipment:
    return load(TP201)


@pytest.fixture(scope="module")
def corpus(eq: Equipment) -> Corpus:
    return build_corpus(eq)


@pytest.fixture(scope="module")
def key() -> dict:
    return load_key(KEY)


def test_committed_key_is_current(corpus: Corpus) -> None:
    """Regenerate with: uv run python -m traceq_dataset.answer_key world/tp201.yaml"""
    for name, data in derive(corpus).items():
        assert (KEY / name).read_text(encoding="utf-8") == dump(name, data, corpus), name


def test_committed_key_matches_the_documents(key: dict, corpus: Corpus) -> None:
    assert answer_key_problems(key, corpus) == []


def test_every_taxonomy_type_has_a_layer() -> None:
    assert set(TAXONOMY) == set(DefectType)


def test_every_scenario_is_answered(eq: Equipment, key: dict) -> None:
    assert scenarios_without_answer(eq, key) == []
    assert [d["scenario"] for d in key["defects.yaml"]] == [f"S{i}" for i in range(1, 8)]


def test_coverage_matches_intent(eq: Equipment, key: dict) -> None:
    intended = {r.id: str(r.intended_coverage) for r in eq.requirements}
    assert {r["id"]: r["expected_coverage"] for r in key["requirements.yaml"]} == intended


def test_s8_superseded_value(key: dict) -> None:
    changed = [r for r in key["requirements.yaml"] if "superseded" in r]
    assert [r["id"] for r in changed] == ["URS-TP201-003"]
    assert changed[0]["superseded"][0]["value"]["min"] == 100000
    assert changed[0]["value"]["min"] == 120000


def test_s7_ambiguous_readings(key: dict) -> None:
    [a] = key["ambiguous.yaml"]
    assert a["location"]["text"] == "1.500 rpm"
    assert [r["value"] for r in a["readings"]] == [1500, 1.5]
    assert a["true_value"]["value"] == 1500
    assert a["expected_answer"] == "ask_confirmation"


def test_readings() -> None:
    assert readings("1,500 kg") == [
        {"value": 1500, "separator": "thousands", "convention": "en", "unit": "kg"},
        {"value": 1.5, "separator": "decimal", "convention": "id", "unit": "kg"},
    ]
    with pytest.raises(AnswerKeyError):
        readings("1500 rpm")


def test_scan_locations_carry_quads(key: dict, corpus: Corpus) -> None:
    sat = corpus.scanned[("SAT-TP201", 0)]
    handwritten = {k for k, p in sat.placed.items() if p.quad}
    ocr = next(s for s in key["ocr.yaml"] if s["doc"] == "SAT-TP201")
    assert {e["field"] for e in ocr["entries"]} == handwritten
    for d in key["defects.yaml"]:
        for loc in d["locations"]:
            on_scan = loc["doc"] == "SAT-TP201" and loc.get("field") in handwritten
            assert ("quad" in loc) == on_scan


def test_documents_that_should_exist(key: dict) -> None:
    status = {d["id"]: d["status"] for d in key["documents.yaml"]}
    assert status["SAT-TP201"] == "in_corpus"
    assert {i for i, s in status.items() if s != "in_corpus"} == {"IQ-TP201", "OQ-TP201"}
    assert {i for i, s in status.items() if s == "expected_gap"} == {"IQ-TP201", "OQ-TP201"}
    ra = next(d for d in key["documents.yaml"] if d["id"] == "RA-TP201")
    assert ra["files"] == [{"rev": 0, "file": "RA-TP201_rev0.xlsx"}]
    urs = next(d for d in key["documents.yaml"] if d["id"] == "URS-TP201")
    assert [f["rev"] for f in urs["files"]] == [0, 1]


# --- The validator catches a wrong key ------------------------------------------------


def _broken(key: dict, edit) -> dict:
    out = copy.deepcopy(key)
    edit(out)
    return out


def _defect(key: dict, scenario: str) -> dict:
    return next(d for d in key["defects.yaml"] if d["scenario"] == scenario)


def test_catches_a_wrong_page(key: dict, corpus: Corpus) -> None:
    def edit(k: dict) -> None:
        _defect(k, "S5")["locations"][0]["page"] = 2

    assert answer_key_problems(_broken(key, edit), corpus) == [
        "D-TP201-005: '96 kN' not on FAT-TP201-M rev 0 page 2"
    ]


def test_catches_a_value_not_in_the_document(key: dict, corpus: Corpus) -> None:
    def edit(k: dict) -> None:
        k["requirements.yaml"][1]["value"]["max"] = 75

    assert answer_key_problems(_broken(key, edit), corpus) == [
        "URS-TP201-002: value '75' not in 'Kecepatan turret dapat diatur pada rentang 20–70 rpm.'"
    ]


def test_catches_a_wrong_risk_score(key: dict, corpus: Corpus) -> None:
    def edit(k: dict) -> None:
        k["requirements.yaml"][1]["risk"]["severity"] = 3

    problems = answer_key_problems(_broken(key, edit), corpus)
    assert problems == ["URS-TP201-002 risk: severity is not 3 in F11"]


def test_catches_a_risk_on_the_wrong_row(key: dict, corpus: Corpus) -> None:
    def edit(k: dict) -> None:
        k["requirements.yaml"][1]["risk"]["row"] = 12

    problems = answer_key_problems(_broken(key, edit), corpus)
    assert "URS-TP201-002 risk: critical is not on row 12" in problems


def test_catches_a_moved_quad(key: dict, corpus: Corpus) -> None:
    def edit(k: dict) -> None:
        _defect(k, "S7")["locations"][0]["quad"][0][1] += 5

    assert answer_key_problems(_broken(key, edit), corpus) == [
        "D-TP201-007: SAT-03.observed quad does not match the scan"
    ]


def test_catches_a_planned_document_that_is_rendered(key: dict, corpus: Corpus) -> None:
    def edit(k: dict) -> None:
        _defect(k, "S4")["locations"] = [{"doc": "FAT-TP201-C", "rev": 0, "status": "planned"}]

    assert answer_key_problems(_broken(key, edit), corpus) == [
        "D-TP201-004: FAT-TP201-C is rendered now; re-derive the answer key"
    ]


# --- World data -----------------------------------------------------------------------


def _with(eq: Equipment, edit) -> Equipment:
    data = eq.model_dump(mode="json")
    edit(data)
    return Equipment.model_validate(data)


def test_anchor_needs_a_locator_in_a_rendered_document(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["scenarios"][3]["finding"]["at"] = [{"doc": "FAT-TP201-C"}]

    with pytest.raises(ValidationError, match="S4: anchor FAT-TP201-C rev 0 needs a field or text"):
        _with(eq, edit)


def test_anchor_document_must_be_known(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["scenarios"][5]["finding"]["at"][1]["doc"] = "MTC-NOPE"

    with pytest.raises(ValidationError, match="neither rendered nor a missing required"):
        _with(eq, edit)


def test_required_document_status_matches_rendering(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        sat = next(r for r in d["required_documents"] if r["id"] == "SAT-TP201")
        sat["missing"] = "withheld"

    with pytest.raises(ValidationError, match="SAT-TP201: marked withheld but rendered"):
        _with(eq, edit)


def test_unknown_placed_key(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        d["scenarios"][0]["finding"]["at"][0]["field"] = "SAT-99.observed"

    with pytest.raises(AnswerKeyError, match=r"no placed string 'SAT-99.observed'"):
        derive(build_corpus(_with(eq, edit)))


# --- Corpus manifest ------------------------------------------------------------------


def test_manifest_lists_every_published_file(corpus: Corpus) -> None:
    m = manifest([corpus])
    assert (m["t0"], m["seed"]) == ("2026-06-01", 0)
    by_path = {d["path"]: d for d in m["documents"]}
    assert set(by_path) == {f"TP-201/{corpus.filename(k)}" for k in corpus.rendered}
    sat = by_path["TP-201/SAT-TP201_rev0.pdf"]
    assert (sat["format"], sat["scan_level"], sat["pages"]) == ("scan", "medium", 2)
    published = corpus.published(("SAT-TP201", 0))
    assert sat["sha256"] == hashlib.sha256(published).hexdigest()
    ra = by_path["TP-201/RA-TP201_rev0.xlsx"]
    assert (ra["format"], ra["sheets"], ra["scan_level"]) == ("xlsx", 1, None)
    assert "pages" not in ra


def test_files_are_the_documented_set() -> None:
    assert sorted(p.name for p in KEY.iterdir()) == sorted(FILES)
