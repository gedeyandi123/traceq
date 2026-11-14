"""The eval screen's API (spec #29, ticket #42): harness code, aggregates only.

Scoring is a harness step; the system's API serves run folders and never a score
(``tests/test_api.py``). This API reads the scorer report written beside a run, and the
run's cost, and serves only the report's headline rates with k/n and its split (#74): no
per-item expected value, no baseline. ``tests/fixtures/eval/summary.json`` is the aggregate
the web render test uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval import screen
from traceq_eval.citations import PageTexts
from traceq_eval.oracle import perfect
from traceq_eval.report import write
from traceq_eval.score import score, split_of
from traceq_eval.submission import Submission, System

ROOT = Path(__file__).parents[1]
KEY = ROOT / "answer_key" / "TP-201"
RUN_ID = "20261113T090000Z-f1a2b3"
RUN_JSON = ROOT / "tests" / "fixtures" / "run" / "runs" / RUN_ID / "run.json"
SUMMARY = ROOT / "tests" / "fixtures" / "eval" / "summary.json"
OPENAPI = ROOT / "web" / "eval-openapi.json"
RECORDED = ROOT / "recordings" / "haiku-r6"
RATES = [
    "requirements.value_accuracy",
    "citations.verified_rate",
    "defects.recall",
    "fabrication.rate",
    "probes.fabrication_rate",
    "ocr.exact_match_rate",
    "ocr.entry_recall",
    "ocr.cer",
]


@pytest.fixture(scope="module")
def key() -> dict[str, Any]:
    return load_key(KEY)


@pytest.fixture(scope="module")
def reports(key: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pages = PageTexts(build_corpus(load(ROOT / "world" / "tp201.yaml")))
    empty = Submission(equipment="TP-201", system=System(name="empty"))
    return {
        "perfect": score(perfect(key, "TP-201"), key, pages),
        "empty": score(empty, key, pages),
    }


def _rates(summary: screen.EvalSummary) -> dict[str, tuple[int, int, float | None]]:
    return {r.metric: (r.k, r.n, r.rate) for r in summary.rates}


def test_perfect_run_every_rate_with_k_of_n(
    key: dict[str, Any], reports: dict[str, dict[str, Any]]
) -> None:
    s = screen.summarise(RUN_ID, reports["perfect"], json.loads(RUN_JSON.read_text("utf-8")))
    assert (s.run_id, s.equipment, s.split, s.gates_passed) == (RUN_ID, "TP-201", "dev", True)
    assert (s.model, s.cost_usd, s.mode) == ("claude-haiku-5-5", 0.0012, "replay")
    rates = _rates(s)
    assert list(rates) == RATES
    n_req = len(key["requirements.yaml"])
    n_defects = len(key["defects.yaml"])
    n_ocr = sum(len(d["entries"]) for d in key["ocr.yaml"])
    assert rates["requirements.value_accuracy"] == (n_req, n_req, 1.0)
    assert rates["defects.recall"] == (n_defects, n_defects, 1.0)
    assert rates["probes.fabrication_rate"] == (0, 6, 0.0)
    assert rates["fabrication.rate"][0] == 0 and rates["fabrication.rate"][1] > 0
    k, n, rate = rates["citations.verified_rate"]
    assert k == n > 0 and rate == 1.0
    assert rates["ocr.entry_recall"][1] <= n_ocr
    assert {r.metric: r.better for r in s.rates}["ocr.cer"] == "lower"


def test_empty_run_rates_and_no_cost_without_run_metadata(
    reports: dict[str, dict[str, Any]],
) -> None:
    s = screen.summarise("x", reports["empty"], None)
    rates = _rates(s)
    assert rates["requirements.value_accuracy"][:2] == (
        0,
        rates["requirements.value_accuracy"][1],
    )
    assert rates["fabrication.rate"] == (0, 0, None)
    assert rates["citations.verified_rate"] == (0, 0, None)
    assert (s.cost_usd, s.model, s.mode) == (None, None, None)


def _recount(report: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """k/n recounted from the report's items, independently of the scorer's headline."""
    reqs, defects, ocr = (report[s]["items"] for s in ("requirements", "defects", "ocr"))
    cites, fab, probes = report["citations"], report["fabrication"], report["probes"]
    return {
        "requirements.value_accuracy": (sum(i["value_ok"] for i in reqs), len(reqs)),
        "citations.verified_rate": (cites["by_status"]["verified"], cites["total"]),
        "defects.recall": (sum(bool(d["found_by"]) for d in defects), len(defects)),
        "fabrication.rate": (fab["fabricated"], fab["claims"]),
        "probes.fabrication_rate": (probes["metrics"]["fabricated"], len(probes["items"])),
        "ocr.exact_match_rate": (sum(i["exact"] for i in ocr), len(ocr)),
        "ocr.entry_recall": (sum(i["matched_by"] is not None for i in ocr), len(ocr)),
        "ocr.cer": (sum(i["edits"] for i in ocr), sum(i["chars"] for i in ocr)),
    }


def _section_rate(report: dict[str, Any], metric: str) -> float | None:
    section, name = metric.split(".")
    return report[section].get("metrics", report[section])[name]


@pytest.mark.parametrize(
    ("recorded", "split"),
    [(RECORDED / "report-TP-201.json", "dev"), (RECORDED / "report-TP-202.json", "held_out")],
)
def test_screen_rates_are_the_recorded_reports_metrics(recorded: Path, split: str) -> None:
    report = json.loads(recorded.read_text(encoding="utf-8"))
    s = screen.summarise("x", report, None)
    assert report["split"] == s.split == split
    assert [r.metric for r in s.rates] == RATES == list(report["headline"])
    recount = _recount(report)
    for r in s.rates:
        assert r.rate == _section_rate(report, r.metric), r.metric
        assert (r.k, r.n) == recount[r.metric], r.metric
        assert report["headline"][r.metric] == {
            "k": r.k,
            "n": r.n,
            "rate": r.rate,
            "better": r.better,
        }


@pytest.mark.parametrize(("equipment", "split"), [("TP-201", "dev"), ("TP-202", "held_out")])
def test_split_follows_the_equipment(equipment: str, split: str) -> None:
    assert split_of(equipment) == split


@pytest.fixture
def runs(tmp_path: Path, reports: dict[str, dict[str, Any]]) -> Path:
    folder = tmp_path / RUN_ID
    write(reports["perfect"], folder)
    (folder / "run.json").write_bytes(RUN_JSON.read_bytes())
    unscored = tmp_path / "20261114T090000Z-000000"
    unscored.mkdir()
    (unscored / "run.json").write_bytes(RUN_JSON.read_bytes())
    return tmp_path


def test_serves_aggregates_of_scored_runs_only(runs: Path) -> None:
    client = TestClient(screen.create_app(runs))
    listed = client.get("/evals")
    assert listed.status_code == 200
    assert [e["run_id"] for e in listed.json()] == [RUN_ID]
    one = client.get(f"/evals/{RUN_ID}")
    assert one.status_code == 200 and one.json() == listed.json()[0]
    for path in ("/evals/20261114T090000Z-000000", "/evals/nope", "/evals/..%2F..%2Fx"):
        assert client.get(path).status_code == 404


def test_never_serves_items_expected_values_or_baselines(
    runs: Path, key: dict[str, Any], reports: dict[str, dict[str, Any]]
) -> None:
    client = TestClient(screen.create_app(runs))
    text = client.get(f"/evals/{RUN_ID}").text + client.get("/evals").text
    expected = [e["text"] for d in key["ocr.yaml"] for e in d["entries"] if len(e["text"]) > 3]
    expected += [r["text"] for r in key["requirements.yaml"]]
    assert expected and not [t for t in expected if t in text]
    assert "items" not in text and "baseline" not in text
    schema = screen.openapi_schema()
    assert {m for item in schema["paths"].values() for m in item} == {"get"}
    assert all(w not in json.dumps(schema).lower() for w in ("expected", "baseline"))
    assert "items" not in schema["components"]["schemas"]["EvalSummary"]["properties"]


def test_the_openapi_schema_names_the_headline_metrics() -> None:
    rate = screen.openapi_schema()["components"]["schemas"]["Rate"]
    assert rate["properties"]["metric"]["enum"] == RATES


def test_the_fixture_summary_is_a_summary() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    s = screen.EvalSummary.model_validate_json(text)
    assert s.model_dump(mode="json") == json.loads(text)
    assert [r.metric for r in s.rates] == RATES


def test_the_committed_openapi_schema_is_current() -> None:
    """``web/eval-openapi.json`` feeds the generated eval client; regenerate both with
    ``npm run openapi && npm run generate`` in ``web/``."""
    assert json.loads(OPENAPI.read_text(encoding="utf-8")) == screen.openapi_schema()
