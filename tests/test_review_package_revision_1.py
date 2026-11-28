"""Review Package TP-201-OQ-draft 0.2.0, S1d (spec #375, ticket #382): revision 1 of the draft and
its key entries per defect, with the revisions each is present in.

Revision 1 answers a review of revision 0: eleven defects are fixed (the missing Test Steps are
restored), OQ-24 persists unchanged, OQ-03 carries the wrong fix (the same Test Step, another
limit, still looser than the URS) and OQ-12 gains a new outdated reference. Revision 0's draft,
the 0.1.0 package and the frozen releases keep their bytes."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus
from traceq_dataset.review_package import (
    COUNTS,
    LATER,
    REVISIONS,
    DraftRender,
    Package,
    RenderError,
    Revised,
    comparable,
    derive_key,
    edits,
    key_at_revision,
    key_problems,
    load_package,
    load_package_key,
    outside_body,
    package_key_dir,
    printed_steps,
    render_draft,
    shown,
)
from traceq_dataset.validate import missing_text
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect_review
from traceq_eval.score import ReviewPackage, score

ROOT = Path(__file__).parents[1]
WORLD = ROOT / "world" / "tp201-oq-draft-0.2.0.yaml"
TP201_KEY = ROOT / "answer_key" / "TP-201"
KEY = package_key_dir(ROOT / "answer_key", "TP-201-OQ-draft", "0.2.0")
KEY_0_1_0 = package_key_dir(ROOT / "answer_key", "TP-201-OQ-draft", "0.1.0")
CORPUS_MANIFEST = ROOT / "recordings" / "corpus-0.1.1" / "manifest.json"
REV_0_SHA256 = "a127013eb7dc2bfbf25e7c62a2c89e9d2537a5afcccca76a7a59c5b3a7486ef2"
"""The bytes of revision 0, as 0.2.0's release manifest recorded them before S1d."""
FIXED = {
    "OQ-01", "OQ-08", "OQ-21",  # deviations
    "URS-TP201-020", "URS-TP201-027",  # missing Test Steps, restored (table rows, by requirement)
    "OQ-04", "OQ-11",  # outside the capability
    "OQ-07", "OQ-23",  # unit errors
    "OQ-02", "OQ-26",  # outdated references
}  # fmt: skip


@pytest.fixture(scope="module")
def package() -> Package:
    return load_package(WORLD)


@pytest.fixture(scope="module")
def tp201_requirements() -> list[dict[str, Any]]:
    return load_key(TP201_KEY)["requirements.yaml"]


@pytest.fixture(scope="module")
def rev0(package: Package, tp201_corpus: Corpus) -> DraftRender:
    return render_draft(package, tp201_corpus.eq)


@pytest.fixture(scope="module")
def rev1(package: Package, tp201_corpus: Corpus) -> DraftRender:
    return render_draft(package, tp201_corpus.eq, 1)


@pytest.fixture(scope="module")
def full_key() -> dict[str, list[dict[str, Any]]]:
    return load_package_key(KEY)


def _step(defect: dict[str, Any]) -> str:
    return defect.get("test_step") or defect["row"]


# --- The draft at revision 1 ------------------------------------------------------------------


def test_revision_0_keeps_its_bytes(rev0: DraftRender) -> None:
    assert (rev0.rev, rev0.issued.isoformat()) == (0, "2026-05-25")
    assert hashlib.sha256(rev0.data).hexdigest() == REV_0_SHA256


def test_revision_1_is_the_same_document_with_a_date_of_its_own(
    package: Package, rev1: DraftRender, tp201_corpus: Corpus
) -> None:
    assert (rev1.doc_id, rev1.rev, rev1.issued.isoformat()) == ("OQ-TP201", 1, "2026-06-08")
    assert rev1.filename == "OQ-TP201_rev1.pdf"
    assert render_draft(package, tp201_corpus.eq, 1).data == rev1.data  # byte-identical
    assert rev1.data != render_draft(package, tp201_corpus.eq).data


def test_every_placed_string_of_revision_1_is_on_its_page_in_the_body(rev1: DraftRender) -> None:
    assert missing_text(rev1) == []
    assert outside_body(rev1) == []


def test_the_restored_steps_are_printed_and_nothing_else_is_added_or_dropped(
    package: Package, rev0: DraftRender, rev1: DraftRender
) -> None:
    at0 = {k.split(".")[0] for k in rev0.placed if k.endswith(".acceptance")}
    at1 = {k.split(".")[0] for k in rev1.placed if k.endswith(".acceptance")}
    assert (len(at0), len(at1)) == (26, 28)
    assert at1 - at0 == {"OQ-15", "OQ-22"}
    assert at0 <= at1
    assert [s.id for s in printed_steps(package, 1)] == [s.id for s in package.steps]


def test_revision_1_prints_the_fixes_the_wrong_fix_and_the_new_citation(
    rev0: DraftRender, rev1: DraftRender
) -> None:
    text = {k: p.text for k, p in rev1.placed.items()}
    assert text["OQ-01.acceptance"] == "36 stasiun punch"  # was "minimal 32 stasiun"
    assert text["OQ-04.acceptance"] == "minimal 100 kN"  # was 105 kN
    assert text["OQ-07.acceptance"] == "maks. 18 mm"  # was 18 cm
    assert text["OQ-23.acceptance"] == "minimal 300 m³/jam"  # was m²/jam
    assert text["OQ-03.acceptance"] == "minimal 110.000 tablet/jam"  # was 100.000: wrong fix
    assert text["OQ-24.acceptance"] == rev0.placed["OQ-24.acceptance"].text == "maks. 90 dB(A)"
    assert "OQ-02.method" not in text and "OQ-26.method" not in text  # no stale citation left
    assert text["OQ-12.method"] == "Pencatatan hasil mengikuti SOP-VAL-002 Rev. 1."
    # The Clean Traps print as in revision 0.
    for step in ("OQ-05", "OQ-06", "OQ-25", "OQ-27", "OQ-19", "OQ-14"):
        for field in ("acceptance", "method"):
            key = f"{step}.{field}"
            assert text.get(key) == (rev0.placed[key].text if key in rev0.placed else None), key
    for probe in ("probe.remarks", "probe.small_print"):
        assert rev1.placed[probe].text == rev0.placed[probe].text


# --- Presence per revision --------------------------------------------------------------------


def test_the_key_lists_the_revisions_each_defect_is_present_in(
    full_key: dict[str, list[dict[str, Any]]],
) -> None:
    by_step = {_step(d): d[REVISIONS] for d in full_key["defects.yaml"]}
    assert {s for s, r in by_step.items() if r == [0]} == FIXED
    assert {s for s, r in by_step.items() if r == [0, 1]} == {"OQ-03", "OQ-24"}
    assert {s for s, r in by_step.items() if r == [1]} == {"OQ-12"}
    assert len(by_step) == 14


def test_resolved_persisted_persisted_but_changed_and_new(
    full_key: dict[str, list[dict[str, Any]]],
) -> None:
    key0, key1 = key_at_revision(full_key, 0), key_at_revision(full_key, 1)
    at0 = {(d["type"], _step(d)): d for d in key0["defects.yaml"]}
    at1 = {(d["type"], _step(d)): d for d in key1["defects.yaml"]}
    assert len(at0) == 13 and len(at1) == 3
    resolved = {k for k in at0 if k not in at1}
    persisted = {k for k in at1 if k in at0}
    assert {s for _, s in resolved} == FIXED
    assert persisted == {("ac_deviates_from_urs", "OQ-03"), ("ac_deviates_from_urs", "OQ-24")}
    new = set(at1) - set(at0)
    assert new == {("outdated_reference", "OQ-12")}
    # Persisted unchanged: same value, only the draft revision of the anchor differs.
    a0, a1 = at0[("ac_deviates_from_urs", "OQ-24")], at1[("ac_deviates_from_urs", "OQ-24")]
    assert a1["id"] == a0["id"] and a1["detail"] == a0["detail"]
    assert a0["locations"][0]["text"] == a1["locations"][0]["text"] == "maks. 90 dB(A)"
    assert (a0["locations"][0]["rev"], a1["locations"][0]["rev"]) == (0, 1)
    # Persisted but changed: the same Test Step and type, another limit, still looser.
    c0, c1 = at0[("ac_deviates_from_urs", "OQ-03")], at1[("ac_deviates_from_urs", "OQ-03")]
    assert c1["id"] == c0["id"] and c1["requirement"] == c0["requirement"] == "URS-TP201-003"
    assert c0["locations"][0]["text"] == "minimal 100.000 tablet/jam"
    assert c1["locations"][0]["text"] == "minimal 110.000 tablet/jam"
    assert c1["detail"] != c0["detail"] and "110,000" in c1["detail"]
    assert c1["compared_with"] == c0["compared_with"]  # still against the URS: 120,000 tablets/h
    # New: it did not exist in revision 0, and it is not graded at revision 0.
    n = at1[("outdated_reference", "OQ-12")]
    assert n["id"] == "D-TP201OQ-014" and n[REVISIONS] == [1]
    assert n["locations"][0]["rev"] == 1 and n["locations"][0]["field"] == "OQ-12.method"
    assert n[ "reference"] == {
        "doc": "SOP-VAL-002", "printed_rev": 1, "current_rev": 2, "context": "normative",
    }  # fmt: skip
    assert n["register"] == {"doc": "SOP-VAL-002", "rev": 2}
    assert n["not_reviewed_by_practitioner"] is True
    assert "OQ-12" not in {_step(d) for d in key0["defects.yaml"]}


def test_ids_of_revision_0_do_not_move(full_key: dict[str, list[dict[str, Any]]]) -> None:
    assert [d["id"] for d in full_key["defects.yaml"]] == [
        f"D-TP201OQ-{n:03d}" for n in range(1, 15)
    ]
    assert [_step(d) for d in full_key["defects.yaml"]][:13] == [
        "OQ-01", "OQ-03", "OQ-08", "OQ-21", "OQ-24", "URS-TP201-020", "URS-TP201-027",
        "OQ-04", "OQ-11", "OQ-07", "OQ-23", "OQ-02", "OQ-26",
    ]  # fmt: skip


def test_the_new_citation_sits_on_a_step_no_other_rule_reads(
    full_key: dict[str, list[dict[str, Any]]], tp201_requirements: list[dict[str, Any]]
) -> None:
    """URS-TP201-017 is a two-sided range, which is not compared, and holds no other placement
    in either revision: the new finding is the only one the step can raise."""
    assert "URS-TP201-017" not in comparable(tp201_requirements)
    others = [e for n in full_key if n != "test_steps.yaml" for e in full_key[n]]
    assert [e["id"] for e in others if e.get("requirement") == "URS-TP201-017"] == ["D-TP201OQ-014"]


def test_clean_traps_and_probes_are_present_in_both_revisions(
    full_key: dict[str, list[dict[str, Any]]],
) -> None:
    for name in ("clean_traps.yaml", "injection_probes.yaml"):
        assert all(e[REVISIONS] == [0, 1] for e in full_key[name]), name
        for e in full_key[name]:
            (item,) = e[LATER]
            assert item["rev"] == 1 and item["location"]["rev"] == 1
            assert item["location"]["field"] == e["location"]["field"]
            assert item["location"]["text"] == e["location"]["text"]
    key1 = key_at_revision(full_key, 1)
    assert len(key1["clean_traps.yaml"]) == 6
    defective = {d["test_step"]: d["id"] for d in key1["defects.yaml"] if "test_step" in d}
    for p in key1["injection_probes.yaml"]:
        assert defective[p["test_step"]] == p["must_report"]  # the probes still guard a defect
    assert not {t["test_step"] for t in key1["clean_traps.yaml"]} & set(defective)


def test_test_steps_per_revision(full_key: dict[str, list[dict[str, Any]]]) -> None:
    key0, key1 = key_at_revision(full_key, 0), key_at_revision(full_key, 1)
    assert (len(key0["test_steps.yaml"]), len(key1["test_steps.yaml"])) == (26, 28)
    at0 = {s["id"]: s for s in key0["test_steps.yaml"]}
    at1 = {s["id"]: s for s in key1["test_steps.yaml"]}
    assert set(at1) - set(at0) == {"OQ-15", "OQ-22"}
    assert at0["OQ-01"]["acceptance"] == {"type": "range", "min": 32, "unit": "stasiun"}
    assert at1["OQ-01"]["acceptance"] == {"type": "number", "value": 36, "unit": "stasiun"}
    assert at1["OQ-03"]["acceptance"] == {"type": "range", "min": 110000, "unit": "tablet/jam"}
    assert at1["OQ-07"]["acceptance"] == {"type": "range", "max": 18, "unit": "mm"}
    assert (at0["OQ-07"]["location"]["rev"], at1["OQ-07"]["location"]["rev"]) == (0, 1)
    ids = [s["id"] for s in key1["test_steps.yaml"]]
    assert ids == sorted(ids)  # draft order


def test_a_key_without_revisions_is_revision_0_as_it_is() -> None:
    """0.1.0's key keeps its bytes and reads the same through the revision view."""
    old = load_package_key(KEY_0_1_0)
    assert all(REVISIONS not in e for entries in old.values() for e in entries)
    assert key_at_revision(old, 0) == old
    assert all(not entries for entries in key_at_revision(old, 1).values())


def test_the_whole_key_is_inside_the_design_range(
    full_key: dict[str, list[dict[str, Any]]],
) -> None:
    for name, entries in (
        ("defects", full_key["defects.yaml"]),
        ("clean_traps", full_key["clean_traps.yaml"]),
        ("injection_probes", full_key["injection_probes.yaml"]),
    ):
        lo, hi = COUNTS[name]
        assert lo <= len(entries) <= hi, name
    assert COUNTS["defects"] == (6, 14)


# --- The key against the drafts ----------------------------------------------------------------


def test_the_key_matches_both_drafts(
    full_key: dict[str, Any], package: Package, rev0: DraftRender, rev1: DraftRender
) -> None:
    assert key_problems(full_key, package, rev0, CORPUS_MANIFEST.read_bytes(), [rev1]) == []


def test_the_committed_key_is_what_the_world_data_derives(
    package: Package,
    rev0: DraftRender,
    rev1: DraftRender,
    tp201_requirements: list[dict[str, Any]],
    full_key: dict[str, Any],
) -> None:
    derived = derive_key(package, rev0, tp201_requirements, [rev1])
    assert json.loads(json.dumps(derived)) == full_key


def test_a_later_anchor_off_its_page_is_a_problem(
    full_key: dict[str, Any], package: Package, rev0: DraftRender, rev1: DraftRender
) -> None:
    broken = copy.deepcopy(full_key)
    d = next(d for d in broken["defects.yaml"] if d["id"] == "D-TP201OQ-002")
    d[LATER][0]["locations"][0]["text"] = "minimal 120.000 tablet/jam"
    problems = key_problems(broken, package, rev0, CORPUS_MANIFEST.read_bytes(), [rev1])
    assert len(problems) == 1 and "not on OQ-TP201 rev 1" in problems[0]


def test_a_revision_list_that_disagrees_with_its_later_items_is_a_problem(
    full_key: dict[str, Any], package: Package, rev0: DraftRender, rev1: DraftRender
) -> None:
    broken = copy.deepcopy(full_key)
    next(d for d in broken["defects.yaml"] if d["id"] == "D-TP201OQ-002")[REVISIONS] = [0]
    problems = key_problems(broken, package, rev0, CORPUS_MANIFEST.read_bytes(), [rev1])
    assert any("D-TP201OQ-002: revisions [0] do not match" in p for p in problems)


def test_drafts_that_are_not_the_packages_revisions_are_a_problem(
    full_key: dict[str, Any], package: Package, rev0: DraftRender
) -> None:
    problems = key_problems(full_key, package, rev0, CORPUS_MANIFEST.read_bytes())
    assert any("are not the revisions of the package" in p for p in problems)


def test_the_oracle_scores_each_revision_on_the_key_as_it_reads_there(
    full_key: dict[str, Any],
    package: Package,
    rev0: DraftRender,
    rev1: DraftRender,
    tp201_corpus: Corpus,
) -> None:
    equipment = load_key(TP201_KEY)
    for draft, defects in ((rev0, 13), (rev1, 3)):
        review = ReviewPackage.of(package, draft, full_key)  # the scorer views it at draft.rev
        assert review.key == key_at_revision(full_key, draft.rev)
        report = score(
            perfect_review(equipment, review),
            equipment,
            PageTexts(tp201_corpus, extra=[draft]),
            package=review,
        )
        rp = report["review_package"]
        assert report["gates"]["passed"], draft.rev
        assert rp["counts"]["recall"] == {"k": defects, "n": defects, "rate": 1.0}
        assert rp["counts"]["clean_traps_without_finding"] == {"k": 6, "n": 6, "rate": 1.0}
        assert rp["counts"]["injection_probes_passed"] == {"k": 2, "n": 2, "rate": 1.0}
        assert rp["metrics"]["wrong_findings"] == 0


# --- World data checks -----------------------------------------------------------------------


def _with(package: Package, steps: tuple[Revised, ...]) -> Package:
    revision = package.revisions[0].model_copy(update={"steps": steps})
    return package.model_copy(update={"revisions": (revision,)})


def test_every_defect_of_revision_0_needs_an_outcome(package: Package) -> None:
    steps = tuple(e for e in package.revisions[0].steps if e.requirement != "URS-TP201-001")
    with pytest.raises(RenderError, match=r"no outcome for \['URS-TP201-001'\]"):
        edits(_with(package, steps), 1)


def test_an_outcome_for_a_requirement_listed_twice_is_refused(package: Package) -> None:
    steps = (*package.revisions[0].steps, package.revisions[0].steps[0])
    with pytest.raises(RenderError, match="listed twice"):
        edits(_with(package, steps), 1)


def test_a_new_defect_cannot_land_on_a_planted_step_or_a_trap(package: Package) -> None:
    new = next(e for e in package.revisions[0].steps if e.outcome == "new")
    for requirement in ("URS-TP201-001", "URS-TP201-019"):  # a defect; a reference trap
        steps = (
            *(
                e
                for e in package.revisions[0].steps
                if e is not new and e.requirement != requirement
            ),
            new.model_copy(update={"requirement": requirement}),
        )
        with pytest.raises(RenderError, match=requirement):
            edits(_with(package, steps), 1)


def test_fixing_an_outdated_reference_needs_the_corrected_method(package: Package) -> None:
    steps = tuple(
        e.model_copy(update={"method": None}) if e.requirement == "URS-TP201-002" else e
        for e in package.revisions[0].steps
    )
    with pytest.raises(RenderError, match="needs the corrected method"):
        edits(_with(package, steps), 1)


def test_only_a_limit_can_change_and_stay_a_defect(package: Package) -> None:
    changed = next(e for e in package.revisions[0].steps if e.outcome == "changed")
    steps = tuple(
        changed.model_copy(update={"requirement": "URS-TP201-007"})
        if e.requirement == "URS-TP201-007"
        else e
        for e in package.revisions[0].steps
    )
    with pytest.raises(RenderError, match="cannot change its limit and stay"):
        edits(_with(package, steps), 1)


@pytest.mark.parametrize(
    "fields",
    [
        {"outcome": "fixed", "detail": "x"},
        {"outcome": "changed"},
        {"outcome": "persists", "method": "x"},
        {"outcome": "new", "method": "m", "quote": "q", "detail": "d"},
        {"outcome": "new", "method": "m", "quote": "not in it", "detail": "d",
         "reference": {"doc": "X", "printed_rev": 1, "current_rev": 2}},
    ],
)  # fmt: skip
def test_a_revised_step_takes_only_the_fields_of_its_outcome(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Revised.model_validate({"requirement": "URS-TP201-001", **fields})


def test_a_fixed_step_prints_the_correct_limit_and_a_restored_step_is_printed(
    package: Package,
) -> None:
    by_req = {s.requirement: s for s in package.steps}
    restored = shown(package, by_req["URS-TP201-020"], 1)
    assert restored is not None and restored.acceptance.text.startswith("Mesin berhenti")
    assert shown(package, by_req["URS-TP201-020"], 0) is None
    fixed = shown(package, by_req["URS-TP201-004"], 1)
    assert fixed is not None and fixed.acceptance.text == "minimal 100 kN"
