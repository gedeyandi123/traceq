"""Review Package TP-201-OQ-draft 0.2.0, S1a to S1c: the defect types
``ac_outside_documented_capability`` (spec #375, ticket #379), ``unit_error`` (ticket #380) and
``outdated_reference`` (ticket #381):
fixed and seeded placements, the render, the derived key and its Clean Traps, and the
Datasheet-to-requirement link every planted defect relies on.

0.1.0 (``test_review_package.py``) keeps its world data, its key and its release manifest byte
for byte; the 0.2.0 files live beside them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from traceq.runs.run import run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus
from traceq_dataset.review_package import (
    NOT_REVIEWED_FIELD,
    DraftRender,
    Package,
    RenderError,
    derive_key,
    draw,
    dump_key,
    key_problems,
    load_package,
    load_package_key,
    outside_body,
    package_key_dir,
    release_manifest_text,
    render_draft,
)
from traceq_dataset.validate import missing_text, normalise, page_texts
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect_review
from traceq_eval.score import ReviewPackage, score

ROOT = Path(__file__).parents[1]
WORLD = ROOT / "world" / "tp201-oq-draft-0.2.0.yaml"
WORLD_0_1_0 = ROOT / "world" / "tp201-oq-draft.yaml"
TP201 = ROOT / "world" / "tp201.yaml"
TP201_KEY = ROOT / "answer_key" / "TP-201"
KEY = package_key_dir(ROOT / "answer_key", "TP-201-OQ-draft", "0.2.0")
CORPUS_MANIFEST = ROOT / "recordings" / "corpus-0.1.1" / "manifest.json"
RELEASE_MANIFEST = ROOT / "recordings" / "TP-201-OQ-draft-0.2.0" / "manifest.json"
MANIFEST = ROOT / "recordings" / "corpus-0.1.1"
R10 = ROOT / "recordings" / "haiku-r10"
MODEL = "claude-haiku-5-5"
CAPABILITY = "ac_outside_documented_capability"
PLANTED = {"OQ-04": "URS-TP201-004", "OQ-11": "URS-TP201-016"}
NEAR_CAPABILITY = {"OQ-05": "URS-TP201-005", "OQ-06": "URS-TP201-006"}
UNIT = "unit_error"
UNIT_PLANTED = {"OQ-07": "URS-TP201-007", "OQ-23": "URS-TP201-028"}
EQUIVALENT_UNIT = {"OQ-25": "URS-TP201-030", "OQ-27": "URS-TP201-032"}
OUTDATED = "outdated_reference"
OUTDATED_PLANTED = {"OQ-02": "URS-TP201-002", "OQ-26": "URS-TP201-031"}
REFERENCE_TRAPS = {"OQ-14": "URS-TP201-019", "OQ-19": "URS-TP201-024"}


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(WORLD)


@pytest.fixture(scope="module")
def tp201_requirements() -> list[dict[str, Any]]:
    return load_key(TP201_KEY)["requirements.yaml"]


@pytest.fixture(scope="module")
def draft(package: Package, tp201_corpus: Corpus) -> DraftRender:
    return render_draft(package, tp201_corpus.eq)


@pytest.fixture(scope="module")
def key() -> dict[str, list[dict[str, Any]]]:
    return load_package_key(KEY)


# --- Placements ---------------------------------------------------------------------


def test_the_version_and_the_key_folder_are_0_2_0s_own(package: Package) -> None:
    assert (package.id, package.version) == ("TP-201-OQ-draft", "0.2.0")
    assert KEY == ROOT / "answer_key" / "TP-201-OQ-draft-0.2.0"
    assert load_package(WORLD_0_1_0).version == "0.1.0"


def test_placements_are_the_seeded_draw_over_what_the_world_data_fixes(
    package: Package, tp201_requirements: list[dict[str, Any]]
) -> None:
    drawn = draw(package, tp201_requirements)
    assert drawn == package.draw.placements
    assert set(drawn.ac_outside_documented_capability) == set(PLANTED.values())
    assert set(NEAR_CAPABILITY.values()) <= set(drawn.clean_traps)
    assert set(drawn.unit_error) == set(UNIT_PLANTED.values())
    assert set(EQUIVALENT_UNIT.values()) <= set(drawn.clean_traps)
    fixed = {
        *drawn.ac_outside_documented_capability,
        *drawn.unit_error,
        *NEAR_CAPABILITY.values(),
        *EQUIVALENT_UNIT.values(),
        *OUTDATED_PLANTED.values(),
        *REFERENCE_TRAPS.values(),
    }
    # The draw never takes a fixed requirement for another placement.
    assert not fixed & set(drawn.ac_deviates_from_urs)
    assert not fixed & set(drawn.requirement_not_tested)
    assert not set(drawn.unit_error) & set(drawn.clean_traps)
    assert set(drawn.outdated_reference) == set(OUTDATED_PLANTED.values())
    assert set(drawn.reference_traps) == set(REFERENCE_TRAPS.values())
    assert not set(drawn.reference_traps) & set(drawn.clean_traps)
    # No old-type defect is cut: 0.1.0's five deviations and two missing tests stay.
    assert len(drawn.ac_deviates_from_urs) == package.draw.ac_deviates_from_urs == 5
    assert len(drawn.requirement_not_tested) == package.draw.requirement_not_tested == 2
    assert len(drawn.clean_traps) == package.draw.clean_traps == 4


def test_the_draw_is_reproducible_from_the_recorded_seed(
    package: Package, tp201_requirements: list[dict[str, Any]]
) -> None:
    assert draw(package, tp201_requirements) == draw(package, tp201_requirements)
    other = package.model_copy(update={"draw": package.draw.model_copy(update={"seed": 204})})
    assert draw(other, tp201_requirements) != package.draw.placements


def test_a_fixed_placement_needs_its_printed_variant(
    package: Package, tp201_requirements: list[dict[str, Any]]
) -> None:
    steps = tuple(
        s.model_copy(update={"outside": None}) if s.id == "OQ-04" else s for s in package.steps
    )
    with pytest.raises(RenderError, match="URS-TP201-004: fixed as outside the capability"):
        draw(package.model_copy(update={"steps": steps}), tp201_requirements)
    steps = tuple(
        s.model_copy(update={"trap": None}) if s.id == "OQ-05" else s for s in package.steps
    )
    with pytest.raises(RenderError, match="URS-TP201-005: fixed as a Clean Trap"):
        draw(package.model_copy(update={"steps": steps}), tp201_requirements)


def test_a_fixed_unit_error_needs_its_printed_variant(
    package: Package, tp201_requirements: list[dict[str, Any]]
) -> None:
    steps = tuple(
        s.model_copy(update={"unit_slip": None}) if s.id == "OQ-07" else s for s in package.steps
    )
    with pytest.raises(RenderError, match="URS-TP201-007: fixed as a unit error"):
        draw(package.model_copy(update={"steps": steps}), tp201_requirements)


def test_a_fixed_outdated_reference_or_reference_trap_needs_its_printed_variant(
    package: Package, tp201_requirements: list[dict[str, Any]]
) -> None:
    steps = tuple(
        s.model_copy(update={"stale_reference": None}) if s.id == "OQ-26" else s
        for s in package.steps
    )
    with pytest.raises(RenderError, match="URS-TP201-031: fixed as an outdated reference"):
        draw(package.model_copy(update={"steps": steps}), tp201_requirements)
    steps = tuple(
        s.model_copy(update={"reference_trap": None}) if s.id == "OQ-19" else s
        for s in package.steps
    )
    with pytest.raises(RenderError, match="URS-TP201-024: fixed as a reference trap"):
        draw(package.model_copy(update={"steps": steps}), tp201_requirements)


# --- Render -------------------------------------------------------------------------


def test_render_is_byte_identical(
    package: Package, draft: DraftRender, tp201_corpus: Corpus
) -> None:
    assert render_draft(package, tp201_corpus.eq).data == draft.data


def test_every_placed_string_is_on_its_page_in_the_body(draft: DraftRender) -> None:
    assert missing_text(draft) == []
    assert outside_body(draft) == []


def test_the_planted_steps_print_their_outside_variant(draft: DraftRender) -> None:
    assert draft.placed["OQ-04.acceptance"].text == "minimal 105 kN"
    assert draft.placed["OQ-11.acceptance"].text == "maks. ± 0,5 % FS"
    assert draft.placed["OQ-05.acceptance"].text == "≥ 20 kN"
    assert draft.placed["OQ-06.acceptance"].text == "≤ 25 mm"
    assert draft.placed["OQ-07.acceptance"].text == "maks. 18 cm"
    assert draft.placed["OQ-23.acceptance"].text == "minimal 300 m²/jam"
    assert draft.placed["OQ-25.acceptance"].text == "tinggi maks. 3 m"
    assert draft.placed["OQ-27.acceptance"].text == "maks. 2 jam"
    assert len([k for k in draft.placed if k.endswith(".acceptance")]) == 26


def test_the_reference_steps_print_their_method_variant(draft: DraftRender) -> None:
    assert draft.placed["OQ-02.method"].text.endswith("sesuai VMP-001 Rev. 2.")
    assert draft.placed["OQ-26.method"].text.endswith("sesuai SOP-VAL-002 Rev. 1.")
    assert draft.placed["OQ-19.method"].text.endswith("Rev. 2; Rev. 1 sudah digantikan.")
    assert "IEC 60204-1" in draft.placed["OQ-14.method"].text
    assert sorted(k for k in draft.placed if k.endswith(".method")) == [
        "OQ-02.method",
        "OQ-14.method",
        "OQ-19.method",
        "OQ-26.method",
    ]


# --- Answer key ---------------------------------------------------------------------


def test_committed_key_is_current(
    package: Package, draft: DraftRender, tp201_requirements: list[dict[str, Any]]
) -> None:
    """Regenerate with: uv run python -m traceq_dataset.review_package
    world/tp201-oq-draft-0.2.0.yaml"""
    for name, data in derive_key(package, draft, tp201_requirements).items():
        assert (KEY / name).read_text(encoding="utf-8") == dump_key(name, data, package), name


def test_committed_key_matches_the_draft_and_the_corpus_release(
    key: dict[str, Any], package: Package, draft: DraftRender
) -> None:
    assert key_problems(key, package, draft, CORPUS_MANIFEST.read_bytes()) == []


def test_committed_release_manifest_is_current(package: Package, draft: DraftRender) -> None:
    assert RELEASE_MANIFEST.read_text(encoding="utf-8") == release_manifest_text(package, draft)
    assert json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))["version"] == "0.2.0"


def test_two_defects_of_the_new_type_each_flagged_not_reviewed(key: dict[str, Any]) -> None:
    """The flag is a field of the key, not prose; n = 2 is a dev-only smoke count."""
    planted = [d for d in key["defects.yaml"] if d["type"] == CAPABILITY]
    assert [(d["test_step"], d["requirement"]) for d in planted] == list(PLANTED.items())
    assert all(d[NOT_REVIEWED_FIELD] is True and d["layer"] == "rule" for d in planted)
    others = [d for d in key["defects.yaml"] if d["type"] not in (CAPABILITY, UNIT, OUTDATED)]
    assert {d["type"] for d in others} == {"ac_deviates_from_urs", "requirement_not_tested"}
    assert not any(NOT_REVIEWED_FIELD in d for d in others)
    assert len(others) == 7


def test_two_unit_errors_each_flagged_not_reviewed(key: dict[str, Any]) -> None:
    """One SI prefix factor and one dimension slip; n = 2 is a dev-only smoke count. The number
    printed is the URS number and only the unit differs."""
    planted = [d for d in key["defects.yaml"] if d["type"] == UNIT]
    assert [(d["test_step"], d["requirement"]) for d in planted] == list(UNIT_PLANTED.items())
    assert all(d[NOT_REVIEWED_FIELD] is True and d["layer"] == "rule" for d in planted)
    assert [d["unit"] for d in planted] == [
        {"kind": "prefix", "urs": "mm", "printed": "cm"},
        {"kind": "dimension", "urs": "m³/jam", "printed": "m²/jam"},
    ]
    steps = {s["id"]: s["acceptance"] for s in key["test_steps.yaml"]}
    assert steps["OQ-07"] == {"type": "range", "max": 18, "unit": "cm"}  # URS: at most 18 mm
    assert steps["OQ-23"] == {"type": "range", "min": 300, "unit": "m²/jam"}  # URS: 300 m³/jam
    assert [d["locations"][0]["text"] for d in planted] == ["maks. 18 cm", "minimal 300 m²/jam"]
    # No `ac_deviates_from_urs` is expected on a unit error: the type takes the Test Step.
    assert not {d["test_step"] for d in planted} & {
        d["test_step"] for d in key["defects.yaml"] if d["type"] == "ac_deviates_from_urs"
    }


def test_two_outdated_references_each_flagged_not_reviewed(
    key: dict[str, Any], package: Package
) -> None:
    """Both sit in normative method text, cite a register document below its current revision,
    and carry the register anchor and the flag as fields of the key; n = 2 is a smoke count."""
    planted = [d for d in key["defects.yaml"] if d["type"] == OUTDATED]
    assert [(d["test_step"], d["requirement"]) for d in planted] == list(OUTDATED_PLANTED.items())
    assert all(d[NOT_REVIEWED_FIELD] is True and d["layer"] == "rule" for d in planted)
    assert [d["reference"] for d in planted] == [
        {"doc": "VMP-001", "printed_rev": 2, "current_rev": 3, "context": "normative"},
        {"doc": "SOP-VAL-002", "printed_rev": 1, "current_rev": 2, "context": "normative"},
    ]
    recorded = {(d.doc, d.rev) for d in package.corpus.documents}
    for d in planted:
        assert d["reference"]["printed_rev"] < d["reference"]["current_rev"]
        assert d["register"] == {"doc": d["reference"]["doc"], "rev": d["reference"]["current_rev"]}
        assert (d["register"]["doc"], d["register"]["rev"]) in recorded
        assert d["locations"][0]["field"] == f"{d['test_step']}.method"
        assert d["reference"]["doc"] in d["locations"][0]["text"]
    # No other placement on these steps: the rule must not meet a second finding there.
    assert not {d["test_step"] for d in planted} & {
        d["test_step"] for d in key["defects.yaml"] if d["type"] != OUTDATED and "test_step" in d
    }


def test_reference_clean_traps_cover_the_four_safe_contexts_and_raise_nothing(
    key: dict[str, Any],
) -> None:
    traps = {t["test_step"]: t for t in key["clean_traps.yaml"] if "reference" in t}
    assert {s: r["requirement"] for s, r in traps.items()} == REFERENCE_TRAPS
    contexts = {c for t in traps.values() for c in t["reference"]["contexts"]}
    assert contexts == {"current_revision", "revision_history", "unversioned", "external_standard"}
    text = {k: t["location"]["text"] for k, t in traps.items()}
    assert "SOP-VAL-002 Rev. 2; Rev. 1 sudah digantikan" in text["OQ-19"]
    assert "VMP-001." in text["OQ-14"] and "Rev." not in text["OQ-14"]
    assert traps["OQ-19"]["register"] == {"doc": "SOP-VAL-002", "rev": 2}
    assert not set(traps) & {d.get("test_step") for d in key["defects.yaml"]}


def test_a_register_anchor_off_the_recorded_corpus_is_a_problem(
    key: dict[str, Any], package: Package, draft: DraftRender
) -> None:
    broken = json.loads(json.dumps(key))
    next(d for d in broken["defects.yaml"] if d["type"] == OUTDATED)["register"]["rev"] = 9
    problems = key_problems(broken, package, draft, CORPUS_MANIFEST.read_bytes())
    assert len(problems) == 1 and "rev 9 is not a recorded corpus document" in problems[0]


def test_the_register_documents_are_the_releases_current_revisions(package: Package) -> None:
    manifest = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    current: dict[str, int] = {}
    for d in manifest["documents"]:
        current[d["doc_id"]] = max(current.get(d["doc_id"], -1), d["rev"])
    for ref in ("VMP-001", "SOP-VAL-002"):
        (rev,) = [d.rev for d in package.corpus.documents if d.doc == ref]
        assert rev == current[ref]


def test_equivalent_units_are_clean_traps_and_not_defects(key: dict[str, Any]) -> None:
    """2 jam = 120 menit stays a Clean Trap (OQ-27); 3 m = 3,000 mm joins it (OQ-25)."""
    traps = {t["test_step"]: t for t in key["clean_traps.yaml"]}
    for step, requirement in EQUIVALENT_UNIT.items():
        assert traps[step]["requirement"] == requirement
        assert "another unit" in traps[step]["why"]
    steps = {s["id"]: s["acceptance"] for s in key["test_steps.yaml"]}
    assert steps["OQ-25"] == {"type": "range", "max": 3, "unit": "m"}  # URS: at most 3,000 mm
    assert steps["OQ-27"] == {"type": "range", "max": 2, "unit": "jam"}  # URS: at most 120 min
    assert not set(EQUIVALENT_UNIT) & {d.get("test_step") for d in key["defects.yaml"]}


def test_oq_04_is_the_planted_defect_and_no_longer_a_clean_trap(key: dict[str, Any]) -> None:
    """In 0.1.0 "minimal 105 kN" is a Clean Trap; here it is the planted defect, and the
    step holds one placement only."""
    assert "OQ-04" not in [t["test_step"] for t in key["clean_traps.yaml"]]
    (defect,) = [d for d in key["defects.yaml"] if d.get("test_step") == "OQ-04"]
    assert defect["type"] == CAPABILITY
    assert defect["locations"][0]["text"] == "minimal 105 kN"
    old = load_package_key(ROOT / "answer_key" / "TP-201-OQ-draft")
    assert "OQ-04" in [t["test_step"] for t in old["clean_traps.yaml"]]


def test_the_planted_limits_sit_inside_the_urs_limit_so_no_deviation_is_expected(
    key: dict[str, Any],
) -> None:
    steps = {s["id"]: s["acceptance"] for s in key["test_steps.yaml"]}
    assert steps["OQ-04"] == {"type": "range", "min": 105, "unit": "kN"}  # URS: at least 100 kN
    assert steps["OQ-11"] == {"type": "range", "max": 0.5, "unit": "% FS"}  # URS: at most 1 %


def test_clean_traps_of_the_type_sit_at_the_capability_without_passing_it(
    key: dict[str, Any],
) -> None:
    traps = {t["test_step"]: t for t in key["clean_traps.yaml"]}
    assert len(traps) == 6
    for step, requirement in NEAR_CAPABILITY.items():
        trap = traps[step]
        assert trap["requirement"] == requirement
        assert trap["capability"]["kind"] == "maximum"
        assert "not above it" in trap["why"]
    steps = {s["id"]: s["acceptance"] for s in key["test_steps.yaml"]}
    assert steps["OQ-05"] == {"type": "range", "min": 20, "unit": "kN"}  # Datasheet maximum 20 kN
    assert steps["OQ-06"] == {"type": "range", "max": 25, "unit": "mm"}  # Datasheet maximum 25 mm


def test_key_counts_are_in_the_design_range(key: dict[str, Any]) -> None:
    # The design range is 6 to 14 defects (owner, 26 Nov 2026); 13 here: 5 deviations, 2 missing
    # tests, 2 outside the capability, 2 unit errors, 2 outdated references. No old-type defect
    # was cut. Clean Traps: 4 of an Acceptance Criterion and 2 of a reference, never below 4.
    assert len(key["defects.yaml"]) == 13
    assert len(key["clean_traps.yaml"]) == 6
    assert len(key["injection_probes.yaml"]) == 2
    assert len(key["test_steps.yaml"]) == 26


def test_the_type_without_its_flag_is_a_key_problem(
    key: dict[str, Any], package: Package, draft: DraftRender
) -> None:
    broken = json.loads(json.dumps(key))
    planted = next(d for d in broken["defects.yaml"] if d["type"] == CAPABILITY)
    del planted[NOT_REVIEWED_FIELD]
    problems = key_problems(broken, package, draft, CORPUS_MANIFEST.read_bytes())
    assert problems == [f"{planted['id']}: {NOT_REVIEWED_FIELD} must be true for type {CAPABILITY}"]


def test_a_capability_anchor_off_the_recorded_corpus_is_a_problem(
    key: dict[str, Any], package: Package, draft: DraftRender
) -> None:
    broken = json.loads(json.dumps(key))
    next(d for d in broken["defects.yaml"] if d["type"] == CAPABILITY)["capability"]["doc"] = "XX"
    problems = key_problems(broken, package, draft, CORPUS_MANIFEST.read_bytes())
    assert len(problems) == 1 and "XX rev 0 is not a recorded corpus document" in problems[0]


def test_the_capability_anchors_are_on_the_datasheet_page(
    key: dict[str, Any], tp201_corpus: Corpus
) -> None:
    """Every anchor's row name and printed value are on the page the key cites."""
    sheet = tp201_corpus.rendered[("DS-TP201", 0)]
    pages = page_texts(sheet.pdf)
    anchors = [d["capability"] for d in key["defects.yaml"] if "capability" in d]
    anchors += [t["capability"] for t in key["clean_traps.yaml"] if "capability" in t]
    assert len(anchors) == 4
    for a in anchors:
        text = pages[a["page"] - 1]
        assert (a["doc"], a["rev"]) == ("DS-TP201", 0)
        assert normalise(a["name"]) in text and normalise(a["printed"]) in text, a


# --- The Datasheet-to-requirement link every planted defect relies on -----------------------


@pytest.fixture(scope="module")
def matrix(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    """The Equipment run replayed from the recordings (no live call): each requirement with the
    Datasheet rows the Coverage linked to it."""
    out = run(MANIFEST, tmp_path_factory.mktemp("runs"), R10, MODEL, equipment="TP-201")
    data = json.loads((out.folder / "matrix.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in data["requirements"]}


def test_every_planted_requirement_keeps_its_datasheet_link(
    key: dict[str, Any], matrix: dict[str, dict[str, Any]]
) -> None:
    """The plan of spec #375: plant only where the link survives today. The rows are linked
    with a verified citation, under the name and value the key anchors."""
    anchored = [*(d for d in key["defects.yaml"] if "capability" in d)]
    anchored += [t for t in key["clean_traps.yaml"] if "capability" in t]
    assert len(anchored) == 4
    for item in anchored:
        rows = [r for r in matrix[item["requirement"]]["design"] if r["doc"] == "DS-TP201"]
        cap = item["capability"]
        assert [(r["name"], r["printed"].replace("%FS", "% FS")) for r in rows] == [
            (cap["name"], cap["printed"])
        ], item["requirement"]
        assert rows[0]["citation"]["page"] == cap["page"]


def test_the_requirement_that_loses_its_link_is_not_planted(
    key: dict[str, Any], matrix: dict[str, dict[str, Any]]
) -> None:
    """URS-TP201-003 (its unit reads `tablet/h` against `tablets/h`) carries no comparable row,
    so the capability type is never planted on it."""
    assert not [r for r in matrix["URS-TP201-003"]["design"] if r["doc"] == "DS-TP201"]
    assert "URS-TP201-003" not in [
        d["requirement"] for d in key["defects.yaml"] if d["type"] == CAPABILITY
    ]


def test_no_planted_row_is_a_utilities_row(tp201_corpus: Corpus) -> None:
    """Utility supply rows are not comparators (ADR 0010, Limits)."""
    sections = {d.requirement: d.section for d in tp201_corpus.eq.designs if d.doc_id == "DS-TP201"}
    for requirement in (*PLANTED.values(), *NEAR_CAPABILITY.values()):
        assert sections[requirement] != "Utilities", requirement


# --- The scorer on the new key ------------------------------------------------------


def test_the_oracle_scores_full_marks_and_labels_the_new_type(
    key: dict[str, Any], package: Package, draft: DraftRender, tp201_corpus: Corpus
) -> None:
    review = ReviewPackage.of(package, draft, key)
    best = perfect_review(load_key(TP201_KEY), review)
    report = score(
        best, load_key(TP201_KEY), PageTexts(tp201_corpus, extra=[draft]), package=review
    )
    rp = report["review_package"]
    assert report["gates"]["passed"]
    assert (rp["id"], rp["version"]) == ("TP-201-OQ-draft", "0.2.0")
    assert rp["labels"] == [
        "dev only",
        "labels not reviewed",
        f"{CAPABILITY}: not reviewed by a practitioner",
        f"{OUTDATED}: not reviewed by a practitioner",
        f"{UNIT}: not reviewed by a practitioner",
    ]
    assert rp["not_reviewed_types"] == [CAPABILITY, OUTDATED, UNIT]
    c = rp["counts"]
    assert c["recall"] == {"k": 13, "n": 13, "rate": 1.0}
    assert c[f"recall_by_type.{CAPABILITY}"] == {"k": 2, "n": 2, "rate": 1.0}
    assert c[f"recall_by_type.{UNIT}"] == {"k": 2, "n": 2, "rate": 1.0}
    assert c[f"recall_by_type.{OUTDATED}"] == {"k": 2, "n": 2, "rate": 1.0}
    assert c["recall_by_type.ac_deviates_from_urs"] == {"k": 5, "n": 5, "rate": 1.0}
    assert c["clean_traps_without_finding"] == {"k": 6, "n": 6, "rate": 1.0}
    assert rp["metrics"]["wrong_findings"] == 0
