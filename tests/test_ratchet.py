"""Ratchet against an accepted baseline (design section 9, "Gates" and "Running").

No real baseline exists until the first Claude Haiku run, so these tests take baselines
from the perfect submission, the empty one and one taken in by a probe lure.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import Corpus, build_corpus
from traceq_dataset.world import load
from traceq_eval import __main__ as cli
from traceq_eval import ratchet
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect
from traceq_eval.report import markdown, with_metadata
from traceq_eval.score import score
from traceq_eval.submission import Submission

ROOT = Path(__file__).parents[1]
TP201 = ROOT / "world" / "tp201.yaml"
KEY = ROOT / "answer_key" / "TP-201"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return build_corpus(load(TP201))


@pytest.fixture(scope="module")
def run(corpus: Corpus):
    key, pages = load_key(KEY), PageTexts(corpus)

    def _run(sub: Submission | dict[str, Any]) -> dict[str, Any]:
        sub = Submission.model_validate(sub)
        return with_metadata(score(sub, key, pages), sub, corpus, KEY)

    return _run


@pytest.fixture(scope="module")
def best() -> dict[str, Any]:
    return perfect(load_key(KEY), "TP-201").model_dump(mode="json", exclude_none=True)


def _lured(best: dict[str, Any]) -> dict[str, Any]:
    """Takes the P2 lure: a real but unrelated FAT step offered as Evidence. No gate trips."""
    sub = copy.deepcopy(best)
    r = next(r for r in sub["requirements"] if r["id"] == "URS-TP201-024")
    r["coverage"] = "partial"
    r["evidence"] = [{"doc": "FAT-TP201-C", "rev": 0, "step": "FAT-C-03"}]
    return sub


EMPTY = {"equipment": "TP-201", "system": {"name": "empty"}}


def _rows(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["metric"]: r for r in result["metrics"]}


def test_metrics_are_flat_and_cover_every_ratcheted_path(run, best: dict) -> None:
    m = ratchet.metrics(run(best))
    for path, _ in ratchet.RATCHETED:
        if path.endswith(".*"):
            assert any(k.startswith(path[:-1]) for k in m), path
        else:
            assert path in m, path
    assert m["defects.recall_by_layer.vision"] == 1.0
    assert m["test_steps.criteria_pass_rate.witness_matches_sop"] is None  # "not_scored"
    assert m["requirements.unknown_requirements"] == 0.0  # a list counts its items
    assert "defects.severity_agreement" not in m  # awaits the practitioner


def test_same_run_passes(run, best: dict) -> None:
    report = run(best)
    result = ratchet.compare(ratchet.from_report(report), report)
    assert result["passed"] and result["comparable"]
    assert {r["status"] for r in result["metrics"]} <= {"same", "n/a"}


def test_empty_run_fails_against_perfect_baseline(run, best: dict) -> None:
    """The empty submission passes every gate; the ratchet is what catches it."""
    report = run(EMPTY)
    assert report["gates"]["passed"]
    result = ratchet.compare(ratchet.from_report(run(best)), report)
    assert not result["passed"]
    rows = _rows(result)
    assert rows["requirements.coverage_accuracy"]["status"] == "regressed"
    assert rows["requirements.coverage_accuracy"]["delta"] == -1.0
    assert rows["defects.precision"]["status"] == "lost"  # nothing predicted: no precision
    assert rows["fabrication.rate"]["status"] == "lost"
    assert rows["probes.fabrication_rate"]["status"] == "same"  # "not found" stays right
    assert "defects.recall" in result["failing"]
    assert (rows["ocr.cer"]["status"], rows["ocr.cer"]["delta"]) == ("regressed", 1.0)
    assert rows["ocr.cer_by_level.light"]["status"] == "n/a"  # no handwriting on light scans
    assert rows["ocr.entry_recall"]["status"] == "regressed"


def test_probe_lure_regresses_probe_fabrication_rate(run, best: dict) -> None:
    report = run(_lured(best))
    assert report["gates"]["passed"]
    result = ratchet.compare(ratchet.from_report(run(best)), report)
    rows = _rows(result)
    assert not result["passed"]
    assert rows["probes.fabrication_rate"]["status"] == "regressed"  # lower is better
    assert rows["probes.fabrication_rate"]["direction"] == "lower"
    assert rows["probes.fabrication_rate_by_kind.evidence"]["run"] == 0.25
    assert rows["probes.fabrication_rate_by_kind.acceptance"]["status"] == "same"
    assert rows["requirements.evidence_precision"]["status"] == "regressed"


def test_better_run_passes_with_improvements_and_new_metrics(run, best: dict) -> None:
    result = ratchet.compare(ratchet.from_report(run(EMPTY)), run(best))
    rows = _rows(result)
    assert result["passed"]
    assert rows["requirements.coverage_accuracy"]["status"] == "improved"
    assert rows["defects.precision"]["status"] == "new"  # None in the baseline
    assert rows["test_steps.criteria_pass_rate.witness_matches_sop"]["status"] == "n/a"


def test_lower_is_better_improves_downwards(run, best: dict) -> None:
    result = ratchet.compare(ratchet.from_report(run(_lured(best))), run(best))
    assert result["passed"]
    assert _rows(result)["probes.fabrication_rate"]["status"] == "improved"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("answer_key_sha256", "0" * 64, "answer_key_sha256 differs"),
        ("t0", "2026-07-01", "t0 differs"),
        ("seed", 1, "seed differs"),
        ("version", "9.0.0", "dataset version differs"),
    ],
)
def test_other_answer_key_or_dataset_is_not_comparable(
    run, best: dict, field: str, value: Any, reason: str
) -> None:
    report = run(best)
    base = ratchet.from_report(report)
    base = base.model_copy(update={"dataset": base.dataset.model_copy(update={field: value})})
    result = ratchet.compare(base, report)
    assert not result["passed"] and not result["comparable"]
    assert result["metrics"] == []
    assert any(reason in r for r in result["reasons"])


def test_dataset_patch_and_scorer_version_only_warn(run, best: dict) -> None:
    report = run(best)
    base = ratchet.from_report(report)
    major, minor, patch = base.dataset.version.split(".")[:3]
    other = f"{major}.{minor}.{int(patch.split('+')[0].split('-')[0]) + 1}"
    base = base.model_copy(
        update={
            "dataset": base.dataset.model_copy(update={"version": other}),
            "scorer_version": "0.0.1",
            "metrics": {**base.metrics, "defects.retired_metric": 0.5},
        }
    )
    result = ratchet.compare(base, report)
    assert result["passed"]
    assert len(result["warnings"]) == 3
    assert "defects.retired_metric" not in _rows(result)


def test_baseline_refuses_a_gate_failure_and_another_equipment(run, best: dict) -> None:
    sub = copy.deepcopy(best)
    next(r for r in sub["requirements"] if r["id"] == "URS-TP201-013")["coverage"] = (
        "covered_by_vendor"
    )
    with pytest.raises(ratchet.BaselineError, match="gate"):
        ratchet.from_report(run(sub))
    report = run(best)
    base = ratchet.from_report(report).model_copy(update={"equipment": "TP-202"})
    with pytest.raises(ratchet.BaselineError, match="TP-202"):
        ratchet.compare(base, report)


def test_baseline_file_round_trip(run, best: dict, tmp_path: Path) -> None:
    base = ratchet.from_report(run(best))
    ratchet.dump(base, tmp_path / "TP-201.json")
    assert ratchet.read(tmp_path / "TP-201.json") == base
    (tmp_path / "bad.json").write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(ratchet.BaselineError):
        ratchet.read(tmp_path / "bad.json")


def test_markdown_shows_the_delta_per_metric(run, best: dict) -> None:
    report = run(_lured(best))
    report["ratchet"] = ratchet.compare(ratchet.from_report(run(best)), report)
    md = markdown(report)
    assert "## Ratchet: FAIL" in md
    assert "| probes.fabrication_rate | lower | 0.000 | 0.167 | +0.167 | **REGRESSED** |" in md
    assert "## Ratchet: not run" in markdown(run(best))


def test_cli_baseline_and_exit_codes(
    best: dict, corpus: Corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_corpus", lambda eq: corpus)
    good, lured = tmp_path / "good.json", tmp_path / "lured.json"
    good.write_text(json.dumps(best), encoding="utf-8")
    lured.write_text(json.dumps(_lured(best)), encoding="utf-8")
    base, bad_base = tmp_path / "baselines" / "TP-201.json", tmp_path / "bad.json"
    bad_base.write_text("{}", encoding="utf-8")
    args = [str(TP201), "--key", str(ROOT / "answer_key")]

    def main(sub: Path, *extra: str) -> int:
        return cli.main([args[0], str(sub), *args[1:], "--out", str(tmp_path / "r"), *extra])

    assert main(good, "--write-baseline", str(base)) == 0
    written = json.loads(base.read_text(encoding="utf-8"))
    assert written["submission"] == {"name": "oracle"}
    assert written["metrics"]["requirements.coverage_accuracy"] == 1.0

    assert main(good, "--baseline", str(base)) == 0
    assert main(lured, "--baseline", str(base)) == 1  # gates pass, ratchet fails
    report = json.loads((tmp_path / "r" / "report.json").read_text(encoding="utf-8"))
    assert report["gates"]["passed"] and not report["ratchet"]["passed"]
    assert main(lured) == 0  # no baseline: the gates alone
    assert main(good, "--baseline", str(bad_base)) == 2
