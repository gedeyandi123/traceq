"""OCR of handwritten entries on scans (design sections 6 and 9; ``traceq_eval.ocr``)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import load_key
from traceq_eval.ocr import cer, edits, expected_entries, iou, kind, score_ocr
from traceq_eval.oracle import perfect
from traceq_eval.submission import Submission

KEY = Path(__file__).parents[1] / "answer_key" / "TP-201"


@pytest.fixture(scope="module")
def key() -> dict:
    return load_key(KEY)


@pytest.fixture(scope="module")
def best(key: dict) -> dict[str, Any]:
    return perfect(key, "TP-201").model_dump(mode="json", exclude_none=True)


def _score(key: dict, sub: dict) -> dict[str, Any]:
    return score_ocr(Submission.model_validate(sub), key)


def _entry(sub: dict, text: str) -> dict:
    return next(e for e in sub["ocr"] if e["text"] == text)


def _item(report: dict, field: str) -> dict:
    return next(i for i in report["items"] if i["field"] == field)


# --- Helpers -----------------------------------------------------------------------------


def test_kind() -> None:
    assert kind("122.400 tablets/h") == kind("20,4 kN") == kind("1.500 rpm") == "number"
    assert kind("02/05/2026") == "date"
    assert kind("TACH-07 SW-03") == kind("RTP36-25-0471") == kind("KAL-2025-0412") == "id"
    assert kind("Lulus") == kind("Markus Brandt") == "text"


def test_edits_and_cer_keep_separators() -> None:
    assert edits("122.400", "121.400") == 1
    assert edits("1.500 rpm", "1,5 rpm") == 3  # "." → ",", "00" deleted
    assert edits("1.500 rpm", "1500 rpm") == 1  # a dropped separator is an error too
    assert cer("Ada  dan\nberfungsi", "Ada dan berfungsi") == 0.0  # whitespace collapses
    assert cer("Lulus", "lulus") == 0.2  # case-sensitive


def test_iou() -> None:
    q = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert iou(q, q) == 1.0
    assert iou(q, [(5, 0), (15, 0), (15, 10), (5, 10)]) == pytest.approx(1 / 3)
    assert iou(q, [(20, 20), (30, 20), (30, 30), (20, 30)]) == 0.0


def test_overwritten_original_is_not_expected(key: dict) -> None:
    fields = [e["field"] for e in expected_entries(key)]
    assert "SAT-01.observed" in fields and "SAT-01.observed.original" not in fields
    assert len(fields) == 36


def test_quad_needs_four_points(best: dict) -> None:
    sub = copy.deepcopy(best)
    sub["ocr"][0]["quad"] = sub["ocr"][0]["quad"][:3]
    with pytest.raises(ValidationError):
        Submission.model_validate(sub)


def test_submission_without_ocr_is_still_version_1(best: dict) -> None:
    sub = {k: v for k, v in best.items() if k != "ocr"}
    assert Submission.model_validate(sub).version == 1


# --- Scores ------------------------------------------------------------------------------


def test_perfect_reads_everything(key: dict, best: dict) -> None:
    m = _score(key, best)["metrics"]
    assert (m["entries"], m["matched"], m["unmatched_entries"]) == (36, 36, 0)
    assert m["entry_recall"] == m["localisation_rate"] == m["exact_match_rate"] == 1.0
    assert m["cer"] == 0.0
    assert m["cer_by_kind"] == dict.fromkeys(("number", "date", "id", "text"), 0.0)
    assert m["cer_by_level"] == {"light": None, "medium": 0.0}  # light scans hold no handwriting
    assert m["read_overwritten_original"] == 0


def test_empty_reads_nothing(key: dict) -> None:
    m = _score(key, {"equipment": "TP-201", "system": {"name": "empty"}})["metrics"]
    assert (m["submitted"], m["matched"]) == (0, 0)
    assert m["entry_recall"] == m["localisation_rate"] == m["exact_match_rate"] == 0.0
    assert m["cer"] == 1.0  # every expected character deleted
    assert m["cer_by_level"]["medium"] == 1.0


def test_misreads(key: dict, best: dict) -> None:
    """122.400 read as the overwritten 121.400 (S1); 1.500 rpm read as 1,5 rpm (S7)."""
    sub = copy.deepcopy(best)
    _entry(sub, "122.400 tablets/h")["text"] = "121.400 tablets/h"
    _entry(sub, "1.500 rpm")["text"] = "1,5 rpm"
    r = _score(key, sub)
    m = r["metrics"]
    s1, s7 = _item(r, "SAT-01.observed"), _item(r, "SAT-03.observed")
    assert (s1["edits"], s1["exact"], s1["read_overwritten_original"]) == (1, False, True)
    assert (s7["edits"], s7["exact"], s7["read_overwritten_original"]) == (3, False, False)
    assert s1["matched_by"] == s7["matched_by"] == "quad"
    assert m["entry_recall"] == 1.0
    assert m["exact_match_rate"] == round(34 / 36, 4)
    chars = sum(i["chars"] for i in r["items"])
    assert m["cer"] == round(4 / chars, 4)
    # 122.400 tablets/h, 20,4 kN, 1.500 rpm: 33 characters, two of three wrong
    assert m["cer_by_kind"]["number"] == round(4 / 33, 4)
    assert m["exact_match_by_kind"]["number"] == round(1 / 3, 4)
    assert m["cer_by_kind"]["text"] == m["cer_by_kind"]["date"] == 0.0
    assert m["read_overwritten_original"] == 1


def test_without_quads_entries_match_by_text(key: dict, best: dict) -> None:
    sub = copy.deepcopy(best)
    for e in sub["ocr"]:
        del e["quad"]
    m = _score(key, sub)["metrics"]
    assert m["entry_recall"] == m["exact_match_rate"] == 1.0
    assert (m["localisation_rate"], m["cer"]) == (0.0, 0.0)


def test_wrong_quad_falls_back_to_text_and_wrong_page_does_not_match(key: dict, best: dict) -> None:
    sub = copy.deepcopy(best)
    _entry(sub, "RTP36-25-0471")["quad"] = [[0, 0], [10, 0], [10, 10], [0, 10]]
    _entry(sub, "Tidak ada")["page"] = 1  # deviations is on page 2
    r = _score(key, sub)
    assert _item(r, "serial")["matched_by"] == "text"
    assert _item(r, "deviations")["got"] is None
    m = r["metrics"]
    assert (m["matched"], m["unmatched_entries"]) == (35, 1)
    assert m["localisation_rate"] == round(34 / 36, 4)


def test_text_match_needs_cer_at_most_half(key: dict) -> None:
    sub = {
        "equipment": "TP-201",
        "system": {"name": "x"},
        "ocr": [{"doc": "SAT-TP201", "rev": 0, "page": 2, "text": "Tidak tersedia"}],
    }
    r = _score(key, sub)
    assert r["metrics"]["matched"] == 0 and _item(r, "deviations")["got"] is None
