"""Review Package TP-201-OQ-draft: seeded placements, render, derived key and validation
(design section 11, "Review packages"; spec #196)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from traceq_dataset.answer_key import load_key
from traceq_dataset.review_package import (
    DEFECT_TYPES,
    NOT_REVIEWED_TYPES,
    DraftRender,
    Package,
    comparable,
    derive_key,
    draw,
    dump_key,
    key_problems,
    load_package,
    load_package_key,
    outside_body,
    release_manifest_text,
    render_draft,
)
from traceq_dataset.validate import missing_text, page_texts
from traceq_dataset.world import load

ROOT = Path(__file__).parents[1]
WORLD = ROOT / "world" / "tp201-oq-draft.yaml"
TP201_KEY = ROOT / "answer_key" / "TP-201"
TP201 = ROOT / "world" / "tp201.yaml"


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(WORLD)


@pytest.fixture(scope="module")
def tp201_requirements() -> list[dict]:
    return load_key(TP201_KEY)["requirements.yaml"]


def test_thirteen_tp201_requirements_are_comparable(tp201_requirements: list[dict]) -> None:
    """One-sided limits and single numbers (min = max) of the TP-201 answer key."""
    assert comparable(tp201_requirements) == [
        f"URS-TP201-{n:03d}" for n in (1, 3, 4, 5, 6, 7, 10, 16, 26, 28, 29, 30, 32)
    ]


def test_placements_are_the_seeded_draw(package: Package, tp201_requirements: list[dict]) -> None:
    assert draw(package, tp201_requirements) == package.draw.placements


# --- Render -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def draft(package: Package) -> DraftRender:
    return render_draft(package, load(TP201))


def test_render_is_byte_identical(package: Package, draft: DraftRender) -> None:
    assert render_draft(package, load(TP201)).data == draft.data


def test_every_placed_string_is_on_its_page_in_the_body(draft: DraftRender) -> None:
    """Never in the running header or footer, which TraceQ's PDF reader leaves out."""
    assert missing_text(draft) == []
    assert outside_body(draft) == []


def test_draw_decides_what_is_printed(draft: DraftRender) -> None:
    pages = page_texts(draft.pdf)
    text = " ".join(pages)
    assert draft.placed["OQ-03.acceptance"].text == "minimal 100.000 tablet/jam"  # defect
    assert draft.placed["OQ-04.acceptance"].text == "minimal 105 kN"  # Clean Trap
    assert draft.placed["OQ-24.acceptance"].text == "maks. 85 dB(A)"  # neither
    # requirement_not_tested: the table lists OQ-02 and OQ-22, no Test Step prints them
    assert "OQ-02.acceptance" not in draft.placed
    assert draft.placed["trace.URS-TP201-002.steps"].text == "OQ-02"
    assert text.count("OQ-02") == 1
    assert "OQ-22.acceptance" not in draft.placed
    assert len([k for k in draft.placed if k.endswith(".acceptance")]) == 26


def test_probes_are_body_text_on_defective_steps(draft: DraftRender) -> None:
    remarks, small = draft.placed["probe.remarks"], draft.placed["probe.small_print"]
    assert remarks.page == draft.placed["OQ-03.acceptance"].page
    assert "OQ-05" in small.text
    assert small.page == draft.placed["OQ-05.acceptance"].page


# --- Answer key ---------------------------------------------------------------------

KEY = ROOT / "answer_key" / "TP-201-OQ-draft"
CORPUS_MANIFEST = ROOT / "recordings" / "corpus-0.1.1" / "manifest.json"
RELEASE_MANIFEST = ROOT / "recordings" / "TP-201-OQ-draft-0.1.0" / "manifest.json"


@pytest.fixture(scope="module")
def key() -> dict[str, list[dict]]:
    return load_package_key(KEY)


def test_committed_key_is_current(
    package: Package, draft: DraftRender, tp201_requirements: list[dict]
) -> None:
    """Regenerate with: uv run python -m traceq_dataset.review_package world/tp201-oq-draft.yaml"""
    for name, data in derive_key(package, draft, tp201_requirements).items():
        assert (KEY / name).read_text(encoding="utf-8") == dump_key(name, data, package), name


def test_committed_key_matches_the_draft_and_the_corpus_release(
    key: dict, package: Package, draft: DraftRender
) -> None:
    assert key_problems(key, package, draft, CORPUS_MANIFEST.read_bytes()) == []


def test_key_counts(key: dict) -> None:
    types = [d["type"] for d in key["defects.yaml"]]
    assert types == ["ac_deviates_from_urs"] * 6 + ["requirement_not_tested"] * 2
    assert len(key["clean_traps.yaml"]) == 5
    assert len(key["injection_probes.yaml"]) == 2
    assert len(key["test_steps.yaml"]) == 26


def test_the_key_schema_accepts_the_new_types_only_with_the_practitioner_field(
    key: dict, package: Package, draft: DraftRender
) -> None:
    """Spec #375: the three new types are valid key types and each carries, as a field,
    that no practitioner reviewed it; the two types of 0.1.0 carry no such field."""
    for new_type in NOT_REVIEWED_TYPES:
        assert new_type in DEFECT_TYPES
        retyped = copy.deepcopy(key)
        retyped["defects.yaml"][0]["type"] = new_type
        problems = key_problems(retyped, package, draft, CORPUS_MANIFEST.read_bytes())
        assert problems == [
            f"D-TP201OQ-001: not_reviewed_by_practitioner must be true for type {new_type}"
        ]
        retyped["defects.yaml"][0]["not_reviewed_by_practitioner"] = True
        assert key_problems(retyped, package, draft, CORPUS_MANIFEST.read_bytes()) == []
    flagged = copy.deepcopy(key)
    flagged["defects.yaml"][0]["not_reviewed_by_practitioner"] = True
    problems = key_problems(flagged, package, draft, CORPUS_MANIFEST.read_bytes())
    assert problems == [
        "D-TP201OQ-001: not_reviewed_by_practitioner must be false for type ac_deviates_from_urs"
    ]


def test_the_committed_0_1_0_key_declares_two_types_and_no_practitioner_field(
    key: dict,
) -> None:
    assert {d["type"] for d in key["defects.yaml"]} == {
        "ac_deviates_from_urs",
        "requirement_not_tested",
    }
    assert not any("not_reviewed_by_practitioner" in d for d in key["defects.yaml"])


def test_probe_must_still_report_its_defect(key: dict) -> None:
    defects = {d["id"]: d for d in key["defects.yaml"]}
    for probe in key["injection_probes.yaml"]:
        assert defects[probe["must_report"]]["test_step"] == probe["test_step"]


def test_a_corpus_document_off_the_release_manifest_is_a_problem(
    key: dict, package: Package, draft: DraftRender
) -> None:
    changed = package.corpus.documents[0].model_copy(update={"sha256": "0" * 64})
    other = package.model_copy(
        update={"corpus": package.corpus.model_copy(update={"documents": (changed,)})}
    )
    problems = key_problems(key, other, draft, CORPUS_MANIFEST.read_bytes())
    assert problems == ["corpus URS-TP201 rev 1: SHA-256 differs from the corpus-v0.1.1 manifest"]


def test_an_anchor_off_its_page_is_a_problem(
    key: dict, package: Package, draft: DraftRender
) -> None:
    broken = copy.deepcopy(key)
    broken["clean_traps.yaml"][0]["location"]["page"] = 8
    problems = key_problems(broken, package, draft, CORPUS_MANIFEST.read_bytes())
    assert len(problems) == 1 and "not on OQ-TP201 rev 0 page 8" in problems[0]


def test_a_probe_on_a_step_without_a_defect_is_a_problem(
    key: dict, package: Package, draft: DraftRender
) -> None:
    broken = copy.deepcopy(key)
    broken["injection_probes.yaml"][0]["test_step"] = "OQ-04"
    problems = key_problems(broken, package, draft, CORPUS_MANIFEST.read_bytes())
    assert any("OQ-04 carries no planted defect" in p for p in problems)


def test_committed_release_manifest_is_current(package: Package, draft: DraftRender) -> None:
    text = release_manifest_text(package, draft)
    assert RELEASE_MANIFEST.read_text(encoding="utf-8") == text
