"""Optional dataset fields (ticket #199), on the invented fixture world FX-001.

- A URS in the ``matrix`` layout: one table per section, each row the document's own clause
  number, one or two requirement sentences and a critical column; key ids never printed.
- ``TestEvidence.acceptance_text``: a FAT/SAT step's Acceptance Criterion as written.
- ``VendorAssessment.areas``: the areas a Vendor Assessment rates, from world data.
- A FAT/SAT step recorded ``fail`` with no Deviation, and its defect-manifest entry.

Every field is optional; with its default TP-201 and TP-202 render byte-identical
(``test_corpus_bytes.py``). Tests check observable output: page text, placed spans, the
derived answer key, and the perfect submission scored by the existing scorer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import derive
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.render import (
    EVAL_T0,
    Rendered,
    render_fat,
    render_urs,
    render_vendor_assessment,
)
from traceq_dataset.schema import Equipment
from traceq_dataset.validate import answer_key_problems, missing_text, page_texts
from traceq_dataset.world import disagreements, load
from traceq_eval.citations import PageTexts, norm
from traceq_eval.oracle import perfect
from traceq_eval.score import score
from traceq_eval.submission import Submission

FX001 = Path(__file__).parent / "fixtures" / "world" / "fx001.yaml"
LONG = " ".join(
    ["the door raises an audible and visible alarm when it is left open longer than set"] * 6
)
"""A sentence several lines long, so a page ends inside a row unless rows cannot break."""


@pytest.fixture(scope="module")
def eq() -> Equipment:
    return load(FX001)


@pytest.fixture(scope="module")
def corpus(eq: Equipment) -> Corpus:
    return build_corpus(eq)


@pytest.fixture(scope="module")
def key(corpus: Corpus) -> dict[str, list[dict[str, Any]]]:
    return derive(corpus)


@pytest.fixture(scope="module")
def urs(corpus: Corpus) -> Rendered:
    return corpus.rendered[("URS-FX001", 0)]


def _with(eq: Equipment, edit: Callable[[dict[str, Any]], None]) -> Equipment:
    data = eq.model_dump(mode="json")
    edit(data)
    return Equipment.model_validate(data)


def _req(data: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in data["requirements"] if r["id"] == rid)


def _doc(data: dict[str, Any], doc_id: str) -> dict[str, Any]:
    return next(d for d in data["documents"] if d["id"] == doc_id)


def test_fixture_world_agrees_with_the_decision_table(eq: Equipment) -> None:
    assert disagreements(eq) == []


# --- Matrix URS -------------------------------------------------------------------------


def test_matrix_places_every_requirement_on_its_page(eq: Equipment, urs: Rendered) -> None:
    assert set(urs.placed) == {r.id for r in eq.requirements}
    assert missing_text(urs) == []


def test_matrix_prints_clause_numbers_and_no_key_ids(eq: Equipment, urs: Rendered) -> None:
    text = " ".join(page_texts(urs.pdf))
    assert not any(r.id in text for r in eq.requirements)
    for clause in ("3.1", "3.2", "4.1", "4.2", "5.1"):
        assert clause in text
    for section in ("3. Performance", "4. Construction", "5. Data"):
        assert section in text
    assert "Critical" in text
    assert "Kritis" not in text


def test_each_requirement_sentence_is_found_exactly_once_on_its_page(
    eq: Equipment, urs: Rendered
) -> None:
    pages = [norm(p) for p in page_texts(urs.pdf)]
    for r in eq.requirements:
        placed = urs.placed[r.id]
        assert pages[placed.page - 1].count(norm(placed.text)) == 1, r.id


def test_two_requirements_share_one_row_under_one_clause(urs: Rendered) -> None:
    first, second = urs.placed["URS-FX001-002"], urs.placed["URS-FX001-003"]
    assert first.page == second.page
    page = norm(page_texts(urs.pdf)[first.page - 1])
    row = f"3.2 {norm(first.text)} {norm(second.text)}"
    assert row in page
    assert page.count("3.2 ") == 1


def test_matrix_critical_column_in_the_document_language(eq: Equipment) -> None:
    def indonesian(d: dict[str, Any]) -> None:
        _doc(d, "URS-FX001")["language"] = "id"

    rendered = render_urs(_with(eq, indonesian), 0, EVAL_T0)
    text = " ".join(page_texts(rendered.pdf))
    assert "Kritis" in text and "Ya" in text and "Tidak" in text
    assert "Critical" not in text
    assert missing_text(rendered) == []


def test_matrix_rows_do_not_break_across_pages(eq: Equipment) -> None:
    """Enough rows for several pages: every row's clause, sentences and critical cell stay
    on one page (each placed sentence sits on the page that prints its clause)."""

    def many(d: dict[str, Any]) -> None:
        base = _req(d, "URS-FX001-005")
        d["requirements"] = [r for r in d["requirements"] if r["section"] != "4. Construction"] + [
            {
                **base,
                "id": f"URS-FX001-{n:03d}",
                "clause": f"4.{n}",
                "text": f"Alarm {n}: " + LONG,
                "param": f"door_alarm_{n}",
            }
            for n in range(10, 70)
        ]
        d["tests"] = [t for t in d["tests"] if t["requirement"] != "URS-FX001-005"]
        d["scenarios"] = []

    eq = _with(eq, many)
    rendered = render_urs(eq, 0, EVAL_T0)
    assert missing_text(rendered) == []
    pages = [norm(p) for p in page_texts(rendered.pdf)]
    assert len(pages) > 2
    rows: dict[str, list[str]] = {}
    for r in eq.requirements:
        rows.setdefault(r.clause or "", []).append(r.id)
    for clause, ids in rows.items():
        page = rendered.placed[ids[0]].page
        assert {rendered.placed[i].page for i in ids} == {page}, clause
        row = " ".join([clause, *(norm(rendered.placed[i].text) for i in ids)])
        assert row in pages[page - 1], clause


def test_derived_key_locates_requirements_by_their_sentence(
    key: dict[str, list[dict[str, Any]]], corpus: Corpus, urs: Rendered
) -> None:
    assert answer_key_problems(key, corpus) == []
    for r in key["requirements.yaml"]:
        assert r["source"]["doc"] == "URS-FX001"
        assert r["text"] == urs.placed[r["id"]].text


def _scored(sub: Submission, key: dict[str, Any], corpus: Corpus) -> dict[str, Any]:
    return score(sub, key, PageTexts(corpus))


def test_perfect_submission_span_matches_every_requirement(
    key: dict[str, list[dict[str, Any]]], corpus: Corpus
) -> None:
    report = _scored(perfect(key, "FX-001"), key, corpus)
    m = report["requirements"]["metrics"]
    assert report["gates"]["passed"]
    assert m["segmentation_recall"] == 1.0 and m["segmentation_precision"] == 1.0
    assert m["coverage_accuracy"] == 1.0 and m["value_accuracy"] == 1.0
    assert m["unknown_requirements"] == [] and m["extra_segments"] == []
    assert report["fabrication"]["fabricated"] == 0


def test_perfect_submission_under_own_names_matches_both_sentences_of_a_row(
    key: dict[str, list[dict[str, Any]]], corpus: Corpus
) -> None:
    """The matrix prints no key ids, so a system names requirements itself: both
    requirements of the shared row are still paired with their own key requirement."""
    sub = perfect(key, "FX-001").model_dump(mode="json", exclude_none=True)
    names = {r["id"]: f"R{n}" for n, r in enumerate(sub["requirements"], 1)}
    for r in sub["requirements"]:
        r["id"] = names[r["id"]]
    for s in sub["test_steps"]:
        s["requirement"] = names[s["requirement"]]
    report = _scored(Submission.model_validate(sub), key, corpus)
    m = report["requirements"]["metrics"]
    assert m["segmentation_recall"] == 1.0 and m["segmentation_precision"] == 1.0
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert items["URS-FX001-002"]["answer"] == names["URS-FX001-002"]
    assert items["URS-FX001-003"]["answer"] == names["URS-FX001-003"]
    assert items["URS-FX001-003"]["purity"] == 1.0


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: _req(d, "URS-FX001-006").pop("clause"), r"URS-FX001-006 needs a clause"),
        (
            lambda d: _req(d, "URS-FX001-006").update(clause="3.1", section="3. Performance"),
            r"clause 3\.1 .*consecutive",
        ),
        (
            lambda d: _req(d, "URS-FX001-001").update(clause="3.2"),
            r"clause 3\.2 holds more than two requirements",
        ),
        (
            lambda d: _req(d, "URS-FX001-003").update(critical=False),
            r"clause 3\.2 .*criticality",
        ),
        (
            lambda d: _doc(d, "URS-FX001").update(layout="standard"),
            r"clause URS-FX001-001 needs a matrix URS",
        ),
        (lambda d: _req(d, "URS-FX001-001").update(clause="URS-FX001-001"), r"clause"),
    ],
    ids=["missing", "apart", "three", "criticality", "standard", "not-a-number"],
)
def test_matrix_clause_rules(
    eq: Equipment, edit: Callable[[dict[str, Any]], Any], message: str
) -> None:
    def apply(d: dict[str, Any]) -> None:
        edit(d)

    with pytest.raises(ValidationError, match=message):
        _with(eq, apply)


# --- acceptance_text --------------------------------------------------------------------


def test_acceptance_text_is_printed_instead_of_the_spec(corpus: Corpus) -> None:
    fat = corpus.rendered[("FAT-FX001", 0)]
    assert fat.placed["FAT-01.acceptance"].text == "Holds every setpoint from 20 to 60 °C"
    assert fat.placed["FAT-02.acceptance"].text == "≤ 0.5 °C"
    assert missing_text(fat) == []
    row = "Holds every setpoint from 20 to 60 °C 20–60 °C Pass"
    assert row in " ".join(page_texts(fat.pdf))


def test_acceptance_text_in_the_answer_key(key: dict[str, list[dict[str, Any]]]) -> None:
    req = next(r for r in key["requirements.yaml"] if r["id"] == "URS-FX001-001")
    assert req["evidence"][0]["acceptance"] == "Holds every setpoint from 20 to 60 °C"


def _acceptance(step: str, text: str, language: str | None = None):
    def edit(d: dict[str, Any]) -> None:
        next(t for t in d["tests"] if t["step"] == step)["acceptance_text"] = text
        if language:
            _doc(d, "FAT-FX001")["language"] = language

    return edit


@pytest.mark.parametrize(
    ("step", "text", "language"),
    [
        ("FAT-01", "Holds every setpoint in the range", None),
        ("FAT-01", "Holds every setpoint from 20 to 160 °C", None),
        ("FAT-02", "Uniformity within 0,5 °C", None),
        ("FAT-02", "Uniformity within 0.5 °C", "id"),
    ],
    ids=["no-number", "part-of-a-number", "id-form-on-en", "en-form-on-id"],
)
def test_acceptance_text_must_state_the_spec_numbers(
    eq: Equipment, step: str, text: str, language: str | None
) -> None:
    with pytest.raises(ValidationError, match=rf"{step}: acceptance_text does not state"):
        _with(eq, _acceptance(step, text, language))


def test_acceptance_text_in_the_document_language_is_accepted(eq: Equipment) -> None:
    changed = _with(eq, _acceptance("FAT-02", "Keseragaman maksimal 0,5 °C", "id"))
    fat = render_fat(changed, "FAT-FX001", EVAL_T0)
    assert fat.placed["FAT-02.acceptance"].text == "Keseragaman maksimal 0,5 °C"
    assert missing_text(fat) == []


# --- Vendor Assessment areas ------------------------------------------------------------


def test_assessment_areas_from_world_data(eq: Equipment) -> None:
    va = render_vendor_assessment(eq, "VA-FX-01", EVAL_T0)
    assert missing_text(va) == []
    assert set(va.placed) == {"scope.thermal", "scope.mechanical", "scope.software"}
    text = " ".join(page_texts(va.pdf))
    assert "Thermal performance Ya Heating, cooling and temperature mapping tests." in text
    assert "Mechanical build Ya" in text
    assert "Controller software Tidak" in text
    assert "Mekanik (mechanical)" not in text
    assert "ruang lingkup terbatas" in text


def test_assessment_scope_must_name_an_area(eq: Equipment) -> None:
    def edit(d: dict[str, Any]) -> None:
        d["vendor"]["assessment"]["scope"] = ["thermal", "cleaning"]

    with pytest.raises(ValidationError, match=r"scope cleaning is not an area"):
        _with(eq, edit)


def test_assessment_area_keys_are_unique(eq: Equipment) -> None:
    def edit(d: dict[str, Any]) -> None:
        areas = d["vendor"]["assessment"]["areas"]
        areas.append(dict(areas[0]))

    with pytest.raises(ValidationError, match=r"duplicate area thermal"):
        _with(eq, edit)


# --- Failed result without Deviation ------------------------------------------------------


def test_failed_step_without_deviation_is_in_the_defect_manifest(
    key: dict[str, list[dict[str, Any]]], corpus: Corpus
) -> None:
    """Already supported: a step recorded fail, the FAT's Deviations section says none."""
    fat = " ".join(page_texts(corpus.rendered[("FAT-FX001", 0)].pdf))
    assert "Not present Fail" in fat
    assert "Deviations None recorded." in fat
    (defect,) = key["defects.yaml"]
    assert defect["type"] == "failed_result_no_deviation"
    assert defect["locations"][0]["field"] == "FAT-03.observed"
    report = _scored(perfect(key, "FX-001"), key, corpus)
    assert report["defects"]["metrics"]["recall"] == 1.0
