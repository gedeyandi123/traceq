"""Tolerant span matching of requirement segmentation (design section 9, "Segmentation").

TP-202's URS is prose with unnumbered tables, so a system names its requirements itself and
the scorer pairs each answer with an answer-key requirement by the URS text the answer
quotes. Scored against the committed TP-202 key: a perfect segmentation under the system's
own names, an empty one, and spans that are shifted, split and merged.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts, norm
from traceq_eval.oracle import perfect
from traceq_eval.score import score
from traceq_eval.submission import Submission, System

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def pages() -> PageTexts:
    return PageTexts(build_corpus(load(ROOT / "world" / "tp202.yaml")))


@pytest.fixture(scope="module")
def key() -> dict:
    return load_key(ROOT / "answer_key" / "TP-202")


@pytest.fixture(scope="module")
def own_names(key: dict) -> dict[str, Any]:
    """The perfect submission under names the system chose (R1, R2, ...): the URS prints
    none, so a system cannot know the answer key's ids."""
    sub = perfect(key, "TP-202").model_dump(mode="json", exclude_none=True)
    names = {r["id"]: f"R{n}" for n, r in enumerate(sub["requirements"], 1)}
    for r in sub["requirements"]:
        r["id"] = names[r["id"]]
    for s in sub["test_steps"]:
        s["requirement"] = names[s["requirement"]]
    return sub


def _score(sub: dict[str, Any], key: dict, pages: PageTexts) -> dict[str, Any]:
    return score(Submission.model_validate(sub), key, pages)


def _answer(sub: dict[str, Any], key: dict, rid: str) -> dict[str, Any]:
    """The answer for answer-key requirement ``rid`` (requirements keep the key's order)."""
    n = [r["id"] for r in key["requirements.yaml"]].index(rid)
    return sub["requirements"][n]


def _text(key: dict, rid: str) -> str:
    return next(r["text"] for r in key["requirements.yaml"] if r["id"] == rid)


def _window(pages: PageTexts, key: dict, rid: str, left: int = 0, right: int = 0) -> str:
    """The URS text of ``rid`` with its start moved by ``left`` and its end by ``right``
    characters (negative: earlier)."""
    r = next(r for r in key["requirements.yaml"] if r["id"] == rid)
    src = r["source"]
    text = norm(pages.pages((src["doc"], src["rev"]))[src["page"] - 1])
    start = text.index(norm(r["text"]))
    return text[start + left : start + len(norm(r["text"])) + right]


def _quote(answer: dict[str, Any], quote: str) -> None:
    """Replace the URS citation's quote (and drop its value, which may no longer be in it)."""
    urs = answer["citations"][0]
    urs["quote"] = quote
    urs.pop("value", None)


def test_perfect_segmentation_under_own_names(
    own_names: dict[str, Any], key: dict, pages: PageTexts
) -> None:
    report = _score(own_names, key, pages)
    m = report["requirements"]["metrics"]
    assert report["gates"]["passed"]
    assert m["coverage_accuracy"] == 1.0
    assert m["value_accuracy"] == 1.0
    assert m["source_citation_rate"] == 1.0
    assert m["unknown_requirements"] == []
    assert m["segmentation_recall"] == 1.0
    assert m["segmentation_precision"] == 1.0
    assert report["fabrication"]["fabricated"] == 0
    assert report["test_steps"]["metrics"]["site_test_recall"] == 1.0
    assert report["test_steps"]["metrics"]["criteria_pass_rate"]["traces_to_requirement"] == 1.0
    item = next(i for i in report["requirements"]["items"] if i["id"] == "URS-TP202-004")
    assert item["answer"] == "R4"


def test_empty_submission_matches_nothing(key: dict, pages: PageTexts) -> None:
    report = score(Submission(equipment="TP-202", system=System(name="empty")), key, pages)
    m = report["requirements"]["metrics"]
    assert m["segmentation_recall"] == 0.0
    assert m["segmentation_precision"] is None
    assert m["extra_segments"] == [] and m["unknown_requirements"] == []
    assert m["coverage_accuracy"] == 0.0
    assert all("answer" not in i for i in report["requirements"]["items"])


def test_shifted_spans_still_match(own_names: dict[str, Any], key: dict, pages: PageTexts) -> None:
    """A table cell quoted with its row label, and a sentence quoted from the end of the
    section intro but cut short, are still the requirement."""
    sub = copy.deepcopy(own_names)
    _quote(_answer(sub, key, "URS-TP202-004"), "Gaya tekan utama Minimal 80 kN.")
    _quote(_answer(sub, key, "URS-TP202-008"), _window(pages, key, "URS-TP202-008", -30, -20))
    report = _score(sub, key, pages)
    m = report["requirements"]["metrics"]
    assert m["segmentation_recall"] == 1.0 and m["segmentation_precision"] == 1.0
    assert m["coverage_accuracy"] == 1.0 and m["source_citation_rate"] == 1.0
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert (items["URS-TP202-004"]["cover"], items["URS-TP202-004"]["purity"]) == (1.0, 1.0)
    assert 0.5 < items["URS-TP202-008"]["cover"] < 1.0
    assert items["URS-TP202-008"]["purity"] == 1.0


def test_span_shifted_off_its_requirement_is_an_extra_segment(
    own_names: dict[str, Any], key: dict, pages: PageTexts
) -> None:
    """The last third of one sentence and the start of the next quote neither by half."""
    sub = copy.deepcopy(own_names)
    _quote(_answer(sub, key, "URS-TP202-010"), _window(pages, key, "URS-TP202-010", 50, 16))
    report = _score(sub, key, pages)
    m = report["requirements"]["metrics"]
    assert m["segmentation_recall"] == round(12 / 13, 4)
    assert m["segmentation_precision"] == round(12 / 13, 4)
    assert m["extra_segments"] == ["R10"] and m["unknown_requirements"] == []
    assert report["fabrication"]["fabricated"] == 0
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert items["URS-TP202-010"]["got"] is None and "answer" not in items["URS-TP202-010"]


def test_split_requirement_matches_its_larger_part(
    own_names: dict[str, Any], key: dict, pages: PageTexts
) -> None:
    sub = copy.deepcopy(own_names)
    head = "Minimal 300.000 tablet/jam pada kecepatan"
    assert len(head) / len(_text(key, "URS-TP202-003")) > 0.5
    _quote(_answer(sub, key, "URS-TP202-003"), head)
    tail = {"doc": "URS-TP202", "rev": 0, "page": 1, "quote": "turret maksimum."}
    sub["requirements"].append({"id": "R3b", "citations": [tail]})
    report = _score(sub, key, pages)
    m = report["requirements"]["metrics"]
    assert m["segmentation_recall"] == 1.0
    assert m["segmentation_precision"] == round(13 / 14, 4)
    assert m["extra_segments"] == ["R3b"] and m["unknown_requirements"] == []
    assert m["coverage_accuracy"] == 1.0
    assert report["fabrication"]["fabricated"] == 0


def test_merged_requirements_match_one_and_miss_the_other(
    own_names: dict[str, Any], key: dict, pages: PageTexts
) -> None:
    """Two table rows quoted as one answer: an even split of requirement text, so the
    earlier requirement in key order takes it."""
    sub = copy.deepcopy(own_names)
    merged = "Minimal 80 kN. Ya Gaya pra-kompresi Minimal 20 kN."
    _quote(_answer(sub, key, "URS-TP202-004"), merged)
    sub["requirements"].remove(_answer(sub, key, "URS-TP202-005"))
    report = _score(sub, key, pages)
    m = report["requirements"]["metrics"]
    assert m["segmentation_recall"] == round(12 / 13, 4)
    assert m["segmentation_precision"] == 1.0
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert (items["URS-TP202-004"]["answer"], items["URS-TP202-004"]["purity"]) == ("R4", 0.5)
    assert items["URS-TP202-005"]["got"] is None


def test_span_over_several_requirements_matches_none(
    own_names: dict[str, Any], key: dict, pages: PageTexts
) -> None:
    """No requirement holds half of the requirement text a three-row quote holds."""
    sub = copy.deepcopy(own_names)
    page = norm(pages.pages(("URS-TP202", 0))[0])
    start = page.index(_text(key, "URS-TP202-001"))
    end = page.index(_text(key, "URS-TP202-003")) + len(_text(key, "URS-TP202-003"))
    rows = page[start:end]
    assert len(rows) <= 200
    first = _answer(sub, key, "URS-TP202-001")
    _quote(first, rows)
    for rid in ("URS-TP202-002", "URS-TP202-003"):
        sub["requirements"].remove(_answer(sub, key, rid))
    report = _score(sub, key, pages)
    m = report["requirements"]["metrics"]
    assert m["segmentation_recall"] == round(10 / 13, 4)
    assert m["extra_segments"] == ["R1"]


def test_the_name_never_decides_the_match(
    own_names: dict[str, Any], key: dict, pages: PageTexts
) -> None:
    """An answer named like another key requirement is still scored by what it quotes."""
    sub = copy.deepcopy(own_names)
    _answer(sub, key, "URS-TP202-011")["id"] = "URS-TP202-010"
    report = _score(sub, key, pages)
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert items["URS-TP202-010"]["answer"] == "R10"
    assert items["URS-TP202-011"]["answer"] == "URS-TP202-010"
    assert report["requirements"]["metrics"]["coverage_accuracy"] == 1.0


def test_answer_quoting_no_urs_text_is_unknown(
    own_names: dict[str, Any], key: dict, pages: PageTexts
) -> None:
    sub = copy.deepcopy(own_names)
    fat = {"doc": "FAT-TP202", "rev": 0, "page": 1, "quote": "41 stations"}
    sub["requirements"].append({"id": "R99", "citations": [fat]})
    report = _score(sub, key, pages)
    m = report["requirements"]["metrics"]
    assert m["unknown_requirements"] == ["R99"] and m["extra_segments"] == []
    assert report["fabrication"]["fabricated"] == 1
