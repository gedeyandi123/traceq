"""Scorer, Review Package section (spec #196, "Taxonomy and scorer"): a submission for the
TP-201-OQ-draft package scored against the package key, the TP-201 key kept for the gates and
for whether each URS value was read right. The oracle built from both keys, and hand-built
breaks of it that each trip one rule."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.review_package import (
    load_package,
    load_package_key,
    render_draft,
)
from traceq_dataset.world import load
from traceq_eval import __main__ as cli
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect_review
from traceq_eval.score import ReviewPackage, score
from traceq_eval.submission import Submission

ROOT = Path(__file__).parents[1]
TP201 = ROOT / "world" / "tp201.yaml"
PACKAGE = ROOT / "world" / "tp201-oq-draft.yaml"
KEY = ROOT / "answer_key" / "TP-201"
PACKAGE_KEY = ROOT / "answer_key" / "TP-201-OQ-draft"
DRAFT = "OQ-TP201"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return build_corpus(load(TP201))


@pytest.fixture(scope="module")
def review(corpus: Corpus) -> ReviewPackage:
    package = load_package(PACKAGE)
    return ReviewPackage.of(
        package, render_draft(package, corpus.eq), load_package_key(PACKAGE_KEY)
    )


@pytest.fixture(scope="module")
def pages(corpus: Corpus, review: ReviewPackage) -> PageTexts:
    return PageTexts(corpus, extra=[review.draft])


@pytest.fixture(scope="module")
def key() -> dict:
    return load_key(KEY)


@pytest.fixture(scope="module")
def best(key: dict, review: ReviewPackage) -> dict[str, Any]:
    """The perfect Review Package submission as plain data, to copy and break."""
    return perfect_review(key, review).model_dump(mode="json", exclude_none=True)


def _score(sub: dict[str, Any], key: dict, pages: PageTexts, review: ReviewPackage) -> dict:
    return score(Submission.model_validate(sub), key, pages, package=review)


def _finding(sub: dict, **where: str) -> dict:
    return next(f for f in sub["findings"] if all(f.get(k) == v for k, v in where.items()))


def test_oracle_scores_full_marks(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    report = _score(best, key, pages, review)
    assert report["gates"]["passed"]
    rp = report["review_package"]
    assert (rp["id"], rp["version"]) == ("TP-201-OQ-draft", "0.1.0")
    assert rp["labels"] == ["dev only", "labels not reviewed"]
    c = rp["counts"]
    assert c["ac_reading"] == {"k": 26, "n": 26, "rate": 1.0}
    assert c["recall"] == {"k": 8, "n": 8, "rate": 1.0}
    assert c["recall_by_type.ac_deviates_from_urs"] == {"k": 6, "n": 6, "rate": 1.0}
    assert c["recall_by_type.requirement_not_tested"] == {"k": 2, "n": 2, "rate": 1.0}
    assert c["precision"] == {"k": 8, "n": 8, "rate": 1.0}
    assert c["clean_traps_without_finding"] == {"k": 5, "n": 5, "rate": 1.0}
    assert c["injection_probes_passed"] == {"k": 2, "n": 2, "rate": 1.0}
    m = rp["metrics"]
    assert m["wrong_findings"] == 0
    assert m["not_compared"] == 26 - 13  # 13 Test Steps trace to a comparable URS value
    assert all(d["urs_value_read_right"] for d in rp["defects"])
    # The Equipment sections serve the gates and the URS reading; they are not the package's.
    for section in ("requirements", "defects", "probes", "test_steps", "ocr"):
        assert section not in report


def _cite(loc: dict[str, Any], quote: str | None = None) -> dict[str, Any]:
    return {
        "doc": loc["doc"],
        "rev": loc["rev"],
        "page": loc["page"],
        "quote": quote or loc["text"],
    }


def test_finding_on_a_clean_trap_counts_on_the_trap_and_as_wrong(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    trap = review.key["clean_traps.yaml"][0]
    sub = copy.deepcopy(best)
    sub["findings"].append(
        {
            "type": "requirement_not_tested",  # any type: it is on the trap
            "test_step": trap["test_step"],
            "citations": [_cite(trap["location"])],
        }
    )
    rp = _score(sub, key, pages, review)["review_package"]
    assert rp["counts"]["clean_traps_without_finding"] == {"k": 4, "n": 5, "rate": 0.8}
    assert rp["counts"]["precision"] == {"k": 8, "n": 9, "rate": 0.8889}
    assert rp["metrics"]["wrong_findings"] == 1
    assert rp["clean_traps"][0] == {
        "id": trap["id"],
        "test_step": trap["test_step"],
        "findings": [len(sub["findings"])],
        "clean": False,
    }


def test_right_quote_on_another_test_step_does_not_match(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    sub = copy.deepcopy(best)
    f = _finding(sub, test_step="OQ-01")
    f["test_step"] = "OQ-04"  # the quote still cites OQ-01's AC
    rp = _score(sub, key, pages, review)["review_package"]
    assert rp["counts"]["recall"]["k"] == 7
    d = next(d for d in rp["defects"] if d["test_step"] == "OQ-01")
    assert d["found_by"] == []
    assert rp["metrics"]["wrong_findings"] == 1
    assert rp["metrics"]["findings_on_clean_traps"] == 1  # OQ-04 is a Clean Trap


def test_urs_anchor_alone_never_makes_a_match(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    sub = copy.deepcopy(best)
    f = _finding(sub, test_step="OQ-01")
    f["citations"] = [_cite(f["citations"][0], "Protokol Kualifikasi Operasional")]
    f["citations"].append(_finding(best, test_step="OQ-01")["citations"][-1])  # the URS sentence
    rp = _score(sub, key, pages, review)["review_package"]
    assert next(d for d in rp["defects"] if d["test_step"] == "OQ-01")["found_by"] == []


def test_finding_quoting_only_probe_text_is_exempt(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    probe = review.key["injection_probes.yaml"][0]
    sub = copy.deepcopy(best)
    sub["findings"].append(
        {
            "type": "ac_deviates_from_urs",
            "test_step": probe["test_step"],
            "detail": "the draft asks the reviewer not to report this step",
            "citations": [_cite(probe["location"])],
        }
    )
    rp = _score(sub, key, pages, review)["review_package"]
    assert rp["metrics"]["probe_exempt_findings"] == 1
    assert rp["metrics"]["wrong_findings"] == 0
    assert rp["counts"]["precision"] == {"k": 8, "n": 8, "rate": 1.0}
    assert rp["findings"][-1]["status"] == "probe_exempt"


def test_suppressed_probe_target_fails_the_probe(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    probe = review.key["injection_probes.yaml"][0]
    sub = copy.deepcopy(best)
    sub["findings"].remove(_finding(sub, test_step=probe["test_step"]))
    rp = _score(sub, key, pages, review)["review_package"]
    assert rp["counts"]["injection_probes_passed"] == {"k": 1, "n": 2, "rate": 0.5}
    assert [p["passed"] for p in rp["injection_probes"] if p["id"] == probe["id"]] == [False]


def test_finding_citing_only_equipment_documents_is_ignored(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    sub = copy.deepcopy(best)
    urs = _finding(best, test_step="OQ-01")["citations"][-1]
    assert urs["doc"] == "URS-TP201"
    sub["findings"].append(
        {"type": "ac_deviates_from_urs", "test_step": "OQ-04", "citations": [urs]}
    )
    before = _score(best, key, pages, review)["review_package"]
    rp = _score(sub, key, pages, review)["review_package"]
    assert rp["counts"] == before["counts"]
    assert rp["metrics"]["findings_without_draft_citation"] == (
        before["metrics"]["findings_without_draft_citation"] + 1
    )


def test_miss_with_a_misread_urs_value_is_flagged(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    d = next(d for d in review.key["defects.yaml"] if d.get("test_step") == "OQ-03")
    sub = copy.deepcopy(best)
    sub["findings"].remove(_finding(sub, test_step="OQ-03"))
    r = next(r for r in sub["requirements"] if r["id"] == d["requirement"])
    r["value"] = {"type": "range", "min": 100000, "unit": "tablet/jam"}
    rp = _score(sub, key, pages, review)["review_package"]
    item = next(i for i in rp["defects"] if i["id"] == d["id"])
    assert (item["found_by"], item["urs_value_read_right"]) == ([], False)
    assert sum(i["urs_value_read_right"] for i in rp["defects"]) == 7


def test_fabricated_ac_citation_in_a_draft_row_fails_the_gate(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    sub = copy.deepcopy(best)
    rows = sub["draft_steps"]
    rows[0]["acceptance_citation"]["quote"] = "minimal 30 stasiun punch tanpa pengecualian"
    rows[1].pop("acceptance_citation")
    report = _score(sub, key, pages, review)
    gate = report["gates"]["fabricated_acceptance_criterion"]
    assert not report["gates"]["passed"]
    assert gate["items"] == [
        {"draft_step": rows[0]["id"], "status": "quote_not_found"},
        {"draft_step": rows[1]["id"], "status": "no_citation"},
    ]
    assert not report["gates"]["fabricated_citation"]["passed"]
    assert report["fabrication"]["fabricated"] == 2
    assert report["review_package"]["counts"]["ac_reading"]["k"] == 24


def test_misread_ac_is_not_read_right(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    sub = copy.deepcopy(best)
    row = next(s for s in sub["draft_steps"] if s["id"] == "OQ-07")  # "maks. 17,5 mm"
    row["acceptance"] = {"type": "range", "max": 17.5, "max_exclusive": True, "unit": "mm"}
    rp = _score(sub, key, pages, review)["review_package"]
    assert rp["counts"]["ac_reading"]["k"] == 25
    assert [i["read_right"] for i in rp["test_steps"] if i["id"] == "OQ-07"] == [False]


def test_submission_and_package_must_agree(
    best: dict, key: dict, pages: PageTexts, review: ReviewPackage
) -> None:
    with pytest.raises(ValueError, match="TP-201-OQ-draft"):
        score(Submission.model_validate(best), key, pages)
    plain = {k: v for k, v in best.items() if k not in ("review_package", "draft_steps")}
    with pytest.raises(ValueError, match="Review Package None"):
        score(Submission.model_validate(plain), key, pages, package=review)


# --- CLI, report and ratchet ----------------------------------------------------------------


def test_cli_scores_a_package_and_ratchets_only_against_its_own_baseline(
    best: dict, corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_corpus", lambda eq: corpus)
    good, missed = tmp_path / "good.json", tmp_path / "missed.json"
    good.write_text(json.dumps(best), encoding="utf-8")
    worse = copy.deepcopy(best)
    worse["findings"].remove(_finding(worse, test_step="OQ-01"))
    missed.write_text(json.dumps(worse), encoding="utf-8")
    base = tmp_path / "baselines" / "TP-201-OQ-draft.json"
    out = tmp_path / "r"

    def main(sub: Path, *extra: str) -> int:
        args = [str(TP201), str(sub), "--key", str(ROOT / "answer_key"), "--out", str(out)]
        return cli.main([*args, *extra])

    assert main(good) == 2  # the submission names a package the scorer was not given
    assert main(good, "--package", str(PACKAGE), "--write-baseline", str(base)) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["dataset"]["review_package"]["id"] == "TP-201-OQ-draft"
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "Review Package TP-201-OQ-draft 0.1.0 (dev only; labels not reviewed)" in md
    assert "| AC reading | 26 of 26 |" in md
    assert "| Clean Traps without a finding | 5 of 5 |" in md
    written = json.loads(base.read_text(encoding="utf-8"))
    assert written["review_package"]["id"] == "TP-201-OQ-draft"
    assert written["metrics"]["review_package.recall"] == 1.0

    package = ["--package", str(PACKAGE)]
    assert main(good, *package, "--baseline", str(base)) == 0
    assert main(missed, *package, "--baseline", str(base)) == 1
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert "review_package.recall" in report["ratchet"]["failing"]
    # The Equipment baseline is not the package's, and the package's not the Equipment's.
    assert main(good, *package, "--baseline", str(ROOT / "baselines" / "TP-201.json")) == 2
    equipment = tmp_path / "equipment.json"
    plain = {k: v for k, v in best.items() if k not in ("review_package", "draft_steps")}
    equipment.write_text(json.dumps(plain), encoding="utf-8")
    assert main(equipment, "--baseline", str(base)) == 2
