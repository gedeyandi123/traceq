"""Held-out TP-202 slice (design sections 5, 6 and 9; spec #29): a different vendor and layout.

The URS is prose with unnumbered tables, so requirement ids are not printed; the FAT is a
test-record layout with an as-built data table and an attachment list. About 12
requirements, three planted defects (one each behind a `partial`, a `gap` and a `conflict`),
two hallucination probes, no scan. The vendor is assessed with limited scope.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import derive, dump, load_key
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.schema import CoverageClass, Equipment
from traceq_dataset.validate import answer_key_problems, missing_text, page_texts
from traceq_dataset.world import disagreements, load
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect
from traceq_eval.score import score

ROOT = Path(__file__).parents[1]
TP202 = ROOT / "world" / "tp202.yaml"
KEY = ROOT / "answer_key" / "TP-202"


@pytest.fixture(scope="module")
def eq() -> Equipment:
    return load(TP202)


@pytest.fixture(scope="module")
def corpus(eq: Equipment) -> Corpus:
    return build_corpus(eq)


@pytest.fixture(scope="module")
def key() -> dict:
    return load_key(KEY)


def _with(eq: Equipment, edit) -> Equipment:
    data = eq.model_dump(mode="json")
    edit(data)
    return Equipment.model_validate(data)


# --- World data -------------------------------------------------------------------------


def test_size_of_the_slice(eq: Equipment) -> None:
    assert 11 <= len(eq.requirements) <= 14
    assert len([s for s in eq.scenarios if s.finding]) == 3
    assert sorted(p.absent for p in eq.probes) == ["acceptance", "evidence"]


def test_vendor_assessed_with_limited_scope(eq: Equipment) -> None:
    """Design section 6: mechanical yes, control system/software no."""
    assert eq.vendor.assessment is not None
    scope = eq.vendor.assessment.scope
    assert "mechanical" in scope and "control" not in scope
    assert any(r.scope == "control" for r in eq.requirements)


def test_decision_table_reproduces_intent(eq: Equipment) -> None:
    assert disagreements(eq) == []
    assert set(Counter(r.intended_coverage for r in eq.requirements)) == set(CoverageClass)


def test_defects_sit_behind_a_partial_a_gap_and_a_conflict(eq: Equipment) -> None:
    reqs = {r.id: r for r in eq.requirements}
    behind = {}
    for s in eq.scenarios:
        assert s.finding is not None
        (req,) = [t for t in s.targets if t in reqs]
        behind[str(s.finding.type)] = reqs[req].intended_coverage
    assert behind == {
        "failed_result_no_deviation": CoverageClass.PARTIAL,
        "missing_attachment": CoverageClass.GAP,
        "design_conflict": CoverageClass.CONFLICT,
    }


def test_no_scan(eq: Equipment) -> None:
    assert all(d.scan is None for d in eq.documents)
    assert {d.type for d in eq.documents} == {"urs", "fat"}


def test_prose_urs_needs_a_table_for_a_critical_requirement(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        prose = next(r for r in d["requirements"] if r.get("table_label") is None)
        prose["critical"] = True

    with pytest.raises(ValidationError, match="critical, so it needs a table_label"):
        _with(eq, edit)


def test_layout_belongs_to_its_document_type(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        next(x for x in d["documents"] if x["type"] == "fat")["layout"] = "prose"

    with pytest.raises(ValidationError, match="layout prose is for a urs"):
        _with(eq, edit)


def test_attachments_only_on_a_fat(eq: Equipment) -> None:
    def edit(d: dict) -> None:
        next(x for x in d["documents"] if x["type"] == "urs")["attachments"] = ["Drawing"]

    with pytest.raises(ValidationError, match="only a FAT lists attachments"):
        _with(eq, edit)


# --- Rendering --------------------------------------------------------------------------


def test_every_document_validates(corpus: Corpus) -> None:
    assert [p for r in corpus.rendered.values() for p in missing_text(r)] == []


def test_urs_prints_no_requirement_numbers(eq: Equipment, corpus: Corpus) -> None:
    urs = corpus.rendered[("URS-TP202", 0)]
    text = " ".join(page_texts(urs.pdf))
    assert "URS-TP202-" not in text
    assert all(intro in text for intro in eq.urs_intros.values())
    assert {k for k in urs.placed} == {r.id for r in eq.requirements}


def test_fat_record_layout(eq: Equipment, corpus: Corpus) -> None:
    fat = corpus.rendered[("FAT-TP202", 0)]
    text = " ".join(page_texts(fat.pdf))
    assert "Machine data (as built)" in text
    params = {r.id: r.param for r in eq.requirements}
    as_built = [f for f in eq.designs if f.doc_id == "FAT-TP202"]
    assert as_built and all(f"as_built.{params[f.requirement]}" in fat.placed for f in as_built)
    assert fat.placed["attachment.1"].text.startswith("Attachment 1:")


# --- Answer key -------------------------------------------------------------------------


def test_committed_key_is_current(corpus: Corpus) -> None:
    """Regenerate with: uv run python -m traceq_dataset.answer_key world/tp202.yaml"""
    for name, data in derive(corpus).items():
        assert (KEY / name).read_text(encoding="utf-8") == dump(name, data, corpus), name


def test_committed_key_matches_the_documents(key: dict, corpus: Corpus) -> None:
    assert answer_key_problems(key, corpus) == []


def test_key_counts(key: dict) -> None:
    assert len(key["defects.yaml"]) == 3
    assert len(key["probes.yaml"]) == 2
    assert key["ambiguous.yaml"] == [] and key["ocr.yaml"] == []
    items = sum(len(key[f]) for f in ("requirements.yaml", "defects.yaml", "documents.yaml"))
    assert 0.08 <= len(key["probes.yaml"]) / items <= 0.12


def test_perfect_submission_passes(key: dict, corpus: Corpus) -> None:
    report = score(perfect(key, "TP-202"), key, PageTexts(corpus))
    assert report["gates"]["passed"]
    assert report["requirements"]["metrics"]["coverage_accuracy"] == 1.0
    assert report["defects"]["metrics"]["recall"] == 1.0
    assert report["citations"]["verified_rate"] == 1.0
