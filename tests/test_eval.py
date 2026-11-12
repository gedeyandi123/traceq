"""Eval scorer v0 (design section 9) against the committed TP-201 answer key: a perfect
submission, an empty one, and broken ones that each trip a known metric or gate."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.world import load
from traceq_eval import __main__ as cli
from traceq_eval.citations import PageTexts, Status, partial_ratio, value_in_quote
from traceq_eval.judge import Criterion, JudgeVerdict, UrsRequirement
from traceq_eval.oracle import perfect
from traceq_eval.report import markdown
from traceq_eval.score import CRITERIA, score
from traceq_eval.submission import Submission, TestStep

ROOT = Path(__file__).parents[1]
TP201 = ROOT / "world" / "tp201.yaml"
KEY = ROOT / "answer_key" / "TP-201"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return build_corpus(load(TP201))


@pytest.fixture(scope="module")
def pages(corpus: Corpus) -> PageTexts:
    return PageTexts(corpus)


@pytest.fixture(scope="module")
def key() -> dict:
    return load_key(KEY)


@pytest.fixture(scope="module")
def best(key: dict) -> dict[str, Any]:
    """The perfect submission as plain data, to copy and break."""
    return perfect(key, "TP-201").model_dump(mode="json", exclude_none=True)


def _req(sub: dict, rid: str) -> dict:
    return next(r for r in sub["requirements"] if r["id"] == rid)


def _metrics(report: dict) -> dict[str, dict]:
    return {s: report[s]["metrics"] for s in ("requirements", "defects", "ambiguous", "documents")}


# --- Fuzzy match and value in quote ------------------------------------------------------


def test_partial_ratio() -> None:
    page = "FAT-M-03 Main compression force ≥ 100 kN 96 kN Pass"
    assert partial_ratio("Main compression force", page) == 1.0
    assert partial_ratio("Main compresion force", page) >= 0.9  # one OCR slip
    assert partial_ratio("Pre-compression force", page) < 0.9
    assert partial_ratio("", page) == 0.0


def test_value_in_quote_number_forms_and_boundaries() -> None:
    assert value_in_quote({"type": "number", "value": 122400, "unit": "t/h"}, "122.400 tablets/h")
    assert value_in_quote({"type": "number", "value": 122400, "unit": "t/h"}, "122,400 tablets/h")
    assert value_in_quote({"type": "number", "value": 0.8, "unit": "µm"}, "Ra ≤ 0,8 µm")
    assert not value_in_quote({"type": "number", "value": 36, "unit": "st"}, "360 stations")
    assert not value_in_quote({"type": "number", "value": 1.5, "unit": "rpm"}, "1.500 rpm")
    assert value_in_quote({"type": "range", "min": 20, "max": 70, "unit": "rpm"}, "20–70 rpm")
    assert not value_in_quote({"type": "range", "min": 20, "max": 70, "unit": "rpm"}, "20–60 rpm")
    assert value_in_quote({"type": "one_of", "allowed": ["SS 316L"]}, "terbuat dari SS 316L.")
    assert value_in_quote({"type": "present"}, "anything")


def test_citation_statuses(pages: PageTexts, key: dict) -> None:
    r = key["requirements.yaml"][0]
    src, value = r["source"], r["value"]
    check = pages.check
    assert check(src["doc"], src["rev"], src["page"], r["text"], value).status is Status.VERIFIED
    assert check("NOPE", 0, 1, r["text"], None).status is Status.UNKNOWN_DOCUMENT
    assert check(src["doc"], src["rev"], 99, r["text"], None).status is Status.UNKNOWN_PAGE
    wrong = {"type": "range", "min": 40, "unit": "stations"}
    assert check(src["doc"], src["rev"], src["page"], r["text"], wrong).status is (
        Status.VALUE_NOT_IN_QUOTE
    )
    long = pages.pages((src["doc"], src["rev"]))[0][:250]
    assert check(src["doc"], src["rev"], src["page"], long, None).status is Status.TOO_LONG


def test_spreadsheet_page_is_a_sheet(pages: PageTexts, key: dict) -> None:
    risk = key["requirements.yaml"][0]["risk"]
    sheet = pages.pages((risk["doc"], risk["rev"]))[0]
    assert risk["sheet"] in sheet or "Tidak" in sheet
    assert pages.check(risk["doc"], risk["rev"], 1, sheet[200:320], None).status is Status.VERIFIED


def test_scan_is_checked_against_the_print_behind_the_pixels(pages: PageTexts) -> None:
    v = pages.check(
        "SAT-TP201",
        0,
        1,
        "122.400 tablets/h",
        {"type": "number", "value": 122400, "unit": "tablets/h"},
    )
    assert v.status is Status.VERIFIED


# --- Perfect and empty -------------------------------------------------------------------


def test_perfect_submission_scores_one_everywhere(key: dict, pages: PageTexts) -> None:
    report = score(perfect(key, "TP-201"), key, pages)
    assert report["gates"]["passed"]
    assert report["fabrication"]["fabricated"] == 0
    assert report["citations"]["verified_rate"] == 1.0
    m = _metrics(report)
    for name in (
        "coverage_accuracy",
        "coverage_macro_f1",
        "value_accuracy",
        "source_citation_rate",
        "evidence_precision",
        "evidence_recall",
    ):
        assert m["requirements"][name] == 1.0, name
    assert m["requirements"]["superseded_values"] == 0
    assert (m["defects"]["recall"], m["defects"]["precision"]) == (1.0, 1.0)
    assert m["defects"]["severity_agreement"] == 1.0
    assert m["ambiguous"]["asked_rate"] == 1.0
    assert (m["documents"]["recall"], m["documents"]["precision"]) == (1.0, 1.0)
    steps = report["test_steps"]["metrics"]
    assert steps["site_test_recall"] == 1.0
    assert steps["criteria_pass_rate"]["traces_to_requirement"] == 1.0
    assert steps["criteria_pass_rate"]["ac_sourced_or_empty"] == 1.0
    assert steps["criteria_pass_rate"]["witness_matches_sop"] == "not_scored"


def test_empty_submission_passes_gates_but_scores_zero(key: dict, pages: PageTexts) -> None:
    """Fabricating nothing is not a result: the ratchet, not the floor, catches it."""
    report = score(Submission(equipment="TP-201", system={"name": "empty"}), key, pages)
    assert report["gates"]["passed"]
    m = _metrics(report)
    assert m["requirements"]["coverage_accuracy"] == 0.0
    assert m["requirements"]["coverage_macro_f1"] == 0.0
    assert report["requirements"]["confusion"]["gap"]["missing"] == 7
    assert m["defects"]["recall"] == 0.0 and m["defects"]["f1"] == 0.0
    assert m["defects"]["precision"] is None  # nothing predicted: no precision, not 0
    assert m["ambiguous"]["asked_rate"] == 0.0
    assert m["documents"]["recall"] == 0.0
    assert report["test_steps"]["metrics"]["site_test_recall"] == 0.0
    assert set(report["test_steps"]["metrics"]["criteria_pass_rate"]) == set(CRITERIA)
    assert report["fabrication"]["rate"] is None


def test_wrong_equipment_is_refused(key: dict, pages: PageTexts) -> None:
    with pytest.raises(ValueError, match="TP-202"):
        score(Submission(equipment="TP-202", system={"name": "x"}), key, pages)


# --- Broken submissions --------------------------------------------------------------------


def test_fabricated_citations_trip_the_gate(best: dict, key: dict, pages: PageTexts) -> None:
    sub = copy.deepcopy(best)
    r1 = _req(sub, "URS-TP201-001")
    r1["citations"][0]["quote"] = "Mesin memiliki 48 stasiun punch dan dua turret."
    r1["citations"].append({**r1["citations"][0], "page": 9, "quote": "Mesin"})
    r1["citations"].append({**r1["citations"][0], "doc": "URS-TP999", "quote": "Mesin"})
    report = score(Submission.model_validate(sub), key, pages)
    gate = report["gates"]["fabricated_citation"]
    assert not report["gates"]["passed"]
    assert sorted(i["status"] for i in gate["items"]) == [
        "quote_not_found",
        "unknown_document",
        "unknown_page",
    ]
    assert report["requirements"]["metrics"]["source_citation_rate"] == pytest.approx(37 / 38, 1e-3)
    assert report["fabrication"]["fabricated"] == 3


def test_value_not_in_quote_is_unsupported_not_fabricated(
    best: dict, key: dict, pages: PageTexts
) -> None:
    sub = copy.deepcopy(best)
    _req(sub, "URS-TP201-002")["citations"][0]["value"] = {
        "type": "range",
        "min": 20,
        "max": 60,
        "unit": "rpm",
    }
    report = score(Submission.model_validate(sub), key, pages)
    assert report["gates"]["passed"]
    assert report["citations"]["by_status"]["value_not_in_quote"] == 1
    assert report["requirements"]["metrics"]["source_citation_rate"] < 1.0


def test_fabricated_evidence_trips_the_gate(best: dict, key: dict, pages: PageTexts) -> None:
    sub = copy.deepcopy(best)
    _req(sub, "URS-TP201-001")["evidence"].append(
        {"doc": "FAT-TP201-M", "rev": 0, "step": "FAT-M-99"}
    )
    _req(sub, "URS-TP201-001")["evidence"].append({"doc": "SAT-TP201", "rev": 0, "step": "SAT-01"})
    report = score(Submission.model_validate(sub), key, pages)
    gate = report["gates"]["fabricated_evidence"]
    assert [i["step"] for i in gate["items"]] == ["FAT-M-99"]
    m = report["requirements"]["metrics"]
    assert m["evidence_precision"] < 1.0  # SAT-01 exists but is not Evidence for URS-001
    assert m["evidence_recall"] == 1.0


def test_unsafe_covered_by_vendor_trips_the_gate(best: dict, key: dict, pages: PageTexts) -> None:
    sub = copy.deepcopy(best)
    for rid in ("URS-TP201-002", "URS-TP201-013", "URS-TP201-009", "URS-TP201-026"):
        _req(sub, rid)["coverage"] = "covered_by_vendor"  # partial, gap, conflict, site_only
    report = score(Submission.model_validate(sub), key, pages)
    gate = report["gates"]["unsafe_covered_by_vendor"]
    assert sorted((i["requirement"], i["expected"]) for i in gate["items"]) == [
        ("URS-TP201-002", "partial"),
        ("URS-TP201-009", "conflict"),
        ("URS-TP201-013", "gap"),
    ]
    m = report["requirements"]["metrics"]
    assert m["coverage_accuracy"] == pytest.approx(34 / 38, 1e-3)
    assert report["requirements"]["confusion"]["site_only"]["covered_by_vendor"] == 1


def test_fabricated_acceptance_criterion_trips_the_gate(
    best: dict, key: dict, pages: PageTexts
) -> None:
    sub = copy.deepcopy(best)
    s0, s1, s2 = sub["test_steps"][:3]
    s0.pop("acceptance_citation")  # AC with no source
    s1["acceptance"] = {"type": "range", "min": 1, "max": 999, "unit": "rpm"}  # not in quote
    s2.pop("acceptance")  # left empty for a human: allowed
    s2.pop("acceptance_citation")
    report = score(Submission.model_validate(sub), key, pages)
    gate = report["gates"]["fabricated_acceptance_criterion"]
    assert sorted(i["status"] for i in gate["items"]) == ["no_citation", "value_not_in_quote"]
    assert report["gates"]["fabricated_citation"]["passed"]
    assert report["fabrication"]["fabricated"] == 2
    rate = report["test_steps"]["metrics"]["criteria_pass_rate"]["ac_sourced_or_empty"]
    assert rate == pytest.approx(19 / 21, 1e-3)


def test_step_for_a_covered_requirement_does_not_trace(
    best: dict, key: dict, pages: PageTexts
) -> None:
    sub = copy.deepcopy(best)
    sub["test_steps"].append({"id": "OQ-X", "requirement": "URS-TP201-001"})
    sub["test_steps"].append({"id": "OQ-Y", "requirement": "URS-TP201-999"})
    report = score(Submission.model_validate(sub), key, pages)
    items = {i["id"]: i["criteria"]["traces_to_requirement"] for i in report["test_steps"]["items"]}
    assert (items["OQ-X"], items["OQ-Y"]) == (False, False)


def test_wrong_values_and_superseded_trap(best: dict, key: dict, pages: PageTexts) -> None:
    sub = copy.deepcopy(best)
    _req(sub, "URS-TP201-003")["value"] = {
        "type": "range",
        "min": 100000,
        "unit": "tablets/h",
    }  # rev 0
    _req(sub, "URS-TP201-002")["value"] = {"type": "range", "min": 20, "max": 60, "unit": "rpm"}
    sub["requirements"].append({"id": "URS-TP201-099", "coverage": "gap"})
    report = score(Submission.model_validate(sub), key, pages)
    m = report["requirements"]["metrics"]
    assert m["value_accuracy"] == pytest.approx(36 / 38, 1e-3)
    assert m["superseded_values"] == 1
    assert m["unknown_requirements"] == ["URS-TP201-099"]
    assert report["fabrication"]["fabricated"] == 1


def test_findings_mislabelled_missed_and_false_positive(
    best: dict, key: dict, pages: PageTexts, corpus: Corpus
) -> None:
    sub = copy.deepcopy(best)
    s5 = next(f for f in sub["findings"] if "96 kN" in f["citations"][0]["quote"])
    s5["type"] = "failed_result_no_deviation"  # located right, labelled wrong
    sub["findings"] = [f for f in sub["findings"] if f["type"] != "gdp_correction"]  # S1 missed
    fds = pages.pages(("FDS-TP201", 0))[0]
    sub["findings"].append(
        {
            "type": "missing_signature",
            "citations": [{"doc": "FDS-TP201", "rev": 0, "page": 1, "quote": fds[:80]}],
        }
    )
    sub["findings"].append(dict(sub["findings"][0]))  # a duplicate is not a false positive
    report = score(Submission.model_validate(sub), key, pages)
    m = report["defects"]["metrics"]
    assert m["recall"] == pytest.approx(5 / 7, 1e-3)
    assert m["recall_by_layer"]["vision"] == 0.0
    assert m["recall_by_severity"]["critical"] == 0.5
    assert (m["mislabelled"], m["false_positives"], m["false_positives_on_clean_documents"]) == (
        1,
        1,
        1,
    )
    assert m["precision"] == 0.75  # 5 originals + the duplicate, of 8
    assert report["gates"]["passed"]


def test_finding_on_the_right_page_but_wrong_text_does_not_match(
    key: dict, pages: PageTexts
) -> None:
    """Page is too coarse on a SAT form that carries four defects: the quote must hold the
    defect's location text."""
    sat = pages.pages(("SAT-TP201", 0))[0]
    sub = Submission.model_validate(
        {
            "equipment": "TP-201",
            "system": {"name": "x"},
            "findings": [
                {
                    "type": "gdp_correction",
                    "citations": [{"doc": "SAT-TP201", "rev": 0, "page": 1, "quote": sat[:60]}],
                }
            ],
        }
    )
    m = score(sub, key, pages)["defects"]["metrics"]
    assert (m["recall"], m["false_positives"]) == (0.0, 1)


def test_ambiguous_value_silently_resolved(best: dict, key: dict, pages: PageTexts) -> None:
    sub = copy.deepcopy(best)
    sub["findings"] = [f for f in sub["findings"] if f["type"] != "ambiguous_value"]
    _req(sub, "URS-TP201-017")["citations"].append(
        {
            "doc": "SAT-TP201",
            "rev": 0,
            "page": 1,
            "quote": "1.500 rpm",
            "value": {"type": "number", "value": 1500, "unit": "rpm"},
        }
    )
    m = score(Submission.model_validate(sub), key, pages)["ambiguous"]["metrics"]
    assert (m["asked_rate"], m["silently_resolved"]) == (0.0, 1)


def test_missing_documents_flagged_wrong(best: dict, key: dict, pages: PageTexts) -> None:
    sub = copy.deepcopy(best)
    sub["missing_documents"] = [
        {"type": "iq_protocol", "stage": "IQ"},
        {"type": "sat", "stage": "SAT"},  # it is in the corpus
    ]
    m = score(Submission.model_validate(sub), key, pages)["documents"]["metrics"]
    assert (m["recall"], m["precision"]) == (0.5, 0.5)
    assert m["flagged_but_in_corpus"] == ["sat/SAT"]


def test_invalid_submissions_are_rejected(best: dict) -> None:
    with pytest.raises(ValidationError, match="duplicate requirement"):
        Submission.model_validate({**best, "requirements": best["requirements"][:1] * 2})
    with pytest.raises(ValidationError):
        Submission.model_validate({**best, "unexpected": 1})
    with pytest.raises(ValidationError):
        Submission.model_validate({**best, "findings": [{"type": "not_a_type", "citations": []}]})


# --- Judge interface -----------------------------------------------------------------------


class RecordingJudge:
    name = "recording"

    def __init__(self) -> None:
        self.seen: list[UrsRequirement | None] = []

    def judge(
        self, step: TestStep, requirement: UrsRequirement | None, criterion: Criterion
    ) -> JudgeVerdict:
        self.seen.append(requirement)
        return JudgeVerdict(
            passed=criterion is not Criterion.INSTRUMENT, critique="no instrument named"
        )


def test_judge_scores_criteria_3_to_5_without_the_answer_key(
    best: dict, key: dict, pages: PageTexts
) -> None:
    judge = RecordingJudge()
    report = score(Submission.model_validate(best), key, pages, judge)
    rates = report["test_steps"]["metrics"]["criteria_pass_rate"]
    assert (
        rates["limits_or_worst_case"],
        rates["names_instrument"],
        rates["executable_method"],
    ) == (1.0, 0.0, 1.0)
    assert report["test_steps"]["metrics"]["judge"] == "recording"
    assert (
        report["test_steps"]["items"][0]["critiques"]["names_instrument"] == "no instrument named"
    )
    assert all(set(vars(r)) == {"id", "text", "value"} for r in judge.seen if r)


# --- CLI and report ------------------------------------------------------------------------


def test_cli_writes_report_and_exit_codes(
    best: dict, corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_corpus", lambda eq: corpus)
    good, bad, invalid = tmp_path / "good.json", tmp_path / "bad.json", tmp_path / "invalid.json"
    good.write_text(json.dumps(best), encoding="utf-8")
    broken = copy.deepcopy(best)
    _req(broken, "URS-TP201-013")["coverage"] = "covered_by_vendor"
    bad.write_text(json.dumps(broken), encoding="utf-8")
    invalid.write_text("{}", encoding="utf-8")
    args = [str(TP201), "--key", str(ROOT / "answer_key")]

    assert cli.main([args[0], str(good), *args[1:], "--out", str(tmp_path / "g")]) == 0
    report = json.loads((tmp_path / "g" / "report.json").read_text(encoding="utf-8"))
    assert report["dataset"]["t0"] == "2026-06-01"
    assert len(report["dataset"]["answer_key_sha256"]) == 64
    assert report["submission"] == {"name": "oracle"}
    assert "## Gates: PASS" in (tmp_path / "g" / "report.md").read_text(encoding="utf-8")

    assert cli.main([args[0], str(bad), *args[1:], "--out", str(tmp_path / "b")]) == 1
    md = (tmp_path / "b" / "report.md").read_text(encoding="utf-8")
    assert "## Gates: FAIL" in md and "| unsafe_covered_by_vendor | 1 | FAIL |" in md

    assert cli.main([args[0], str(invalid), *args[1:], "--out", str(tmp_path / "i")]) == 2


def test_markdown_without_metadata(key: dict, pages: PageTexts) -> None:
    md = markdown(score(Submission(equipment="TP-201", system={"name": "empty"}), key, pages))
    assert md.startswith("# Eval report: TP-201")
    assert "Coverage confusion" in md
