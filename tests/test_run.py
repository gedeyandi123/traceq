"""``traceq run`` end to end (spec #29, primary seam): a released corpus in, a run folder out,
the submission scored by the real scorer. The LLM is a scripted fake; nothing is sent."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import BudgetExceeded, PriceTable, Request, Response
from traceq.ai.cost import Price
from traceq.runs import cli
from traceq.runs.run import RunOutput, run
from traceq_dataset import render
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.score import score
from traceq_eval.submission import Submission

ROOT = Path(__file__).parents[1]
TP201 = ROOT / "world" / "tp201.yaml"
KEY = ROOT / "answer_key" / "TP-201"
MODEL = "scripted"
PRICES = PriceTable(batch_discount=0.5, models={MODEL: Price(1.0, 2.0)})

FABRICATED_QUOTE = "Gaya pra-kompresi yang dapat dicapai minimal 50 kN."
SCRIPT: dict[str, dict[str, Any]] = {
    "URS-TP201-001": {"kind": "range", "min": 36, "unit": "stations"},
    "URS-TP201-002": {"kind": "range", "min": 20, "max": 70, "unit": "rpm"},
    "URS-TP201-004": {"kind": "range", "min": 100, "unit": "kN"},
    # Not on the page: the citation check must drop it.
    "URS-TP201-005": {"kind": "range", "min": 50, "unit": "kN", "quote": FABRICATED_QUOTE},
    # Quote on the page, but it says 25 mm: the value is not in the quote.
    "URS-TP201-006": {"kind": "range", "max": 30, "unit": "mm"},
}
INVENTED = {"id": "URS-TP201-999", "text": "Mesin dapat terbang.", "quote": "Mesin dapat terbang."}


class ScriptedLLM:
    """Segments by the printed requirement numbers, extracts from ``SCRIPT``."""

    def __init__(self) -> None:
        self.sent: list[Request] = []

    @property
    def model(self) -> str:
        return MODEL

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.sent += requests
        return [Response(self._answer(r), MODEL, len(r.user) // 4, 40) for r in requests]

    def _answer(self, r: Request) -> str:
        if r.prompt.name == "segment":
            page = r.user.split("<page>\n", 1)[1].rsplit("\n</page>", 1)[0]
            found = [
                {"id": m[1], "text": m[2], "quote": m[2]}
                for m in re.finditer(r"^(URS-\w+-\d{3}) (?:Ya|Tidak) (.+?)\s*$", page, re.M)
            ]
            if "page 1." in r.user:
                found.append(INVENTED)
            return json.dumps({"requirements": found})
        head = json.loads(r.user.split("\n\n", 1)[0])
        blank = {"kind": "none", "min": None, "max": None, "number": None, "unit": None}
        answer = {**blank, "allowed": [], "text": None, "quote": head["requirement"]}
        return json.dumps(answer | SCRIPT.get(head["id"], {}))


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    assert render.main([str(TP201), "--out", str(out)]) == 0
    return next(out.glob("t0-*"))


@pytest.fixture(scope="module")
def recorded(corpus_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    tmp = tmp_path_factory.mktemp("live")
    return run(
        corpus_dir, tmp / "runs", tmp / "recordings", MODEL, live=ScriptedLLM(), prices=PRICES
    )


def _req(sub: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in sub["requirements"] if r["id"] == rid)


def test_submission_validates_and_passes_the_scorer_gates(recorded: RunOutput) -> None:
    text = (recorded.folder / "submission.json").read_text(encoding="utf-8")
    sub = Submission.model_validate_json(text)
    report = score(sub, load_key(KEY), PageTexts(build_corpus(load(TP201))))

    assert report["gates"]["passed"], report["gates"]
    items = {i["id"]: i for i in report["requirements"]["items"]}
    assert [rid for rid in SCRIPT if items[rid]["value_ok"]] == [
        "URS-TP201-001",
        "URS-TP201-002",
        "URS-TP201-004",
    ]
    assert report["requirements"]["metrics"]["source_citation_rate"] == 1.0
    assert report["requirements"]["metrics"]["unknown_requirements"] == []


def test_an_unverifiable_claim_never_reaches_the_submission(recorded: RunOutput) -> None:
    text = (recorded.folder / "submission.json").read_text(encoding="utf-8")
    sub = json.loads(text)
    assert FABRICATED_QUOTE not in text
    assert INVENTED["id"] not in text
    for rid in ("URS-TP201-005", "URS-TP201-006"):
        r = _req(sub, rid)
        assert "value" not in r, rid
        assert [c.get("value") for c in r["citations"]] == [None], rid
    dropped = {(d["claim"], d["id"]) for d in recorded.metadata["dropped"]}
    assert dropped == {
        ("requirement", "URS-TP201-999"),
        ("value", "URS-TP201-005"),
        ("value", "URS-TP201-006"),
    }


def test_run_metadata_records_model_prompts_tokens_and_cost(recorded: RunOutput) -> None:
    meta = json.loads((recorded.folder / "run.json").read_text(encoding="utf-8"))
    assert meta["model"] == MODEL
    assert meta["mode"] == "live"
    assert set(meta["prompts"]) == {"segment", "extract"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in meta["prompts"].values())
    calls = 2 + 38  # one segmentation call per URS page, one extraction per requirement
    assert meta["calls"] == {"total": calls, "replayed": 0, "live": calls}
    assert meta["tokens"]["output"] == 40 * calls
    expected = (meta["tokens"]["input"] * 1.0 + meta["tokens"]["output"] * 2.0) / 1e6 * 0.5
    assert meta["cost_usd"] == pytest.approx(expected, abs=1e-6)
    assert meta["live_cost_usd"] == pytest.approx(expected, abs=1e-6)
    assert [(d["doc_id"], d["rev"]) for d in meta["corpus"]["documents"]] == [("URS-TP201", 1)]


def test_replay_reproduces_the_run_without_sending(
    recorded: RunOutput, corpus_dir: Path, tmp_path: Path
) -> None:
    recordings = recorded.folder.parents[1] / "recordings"
    argv = ["run", str(corpus_dir), "--out", str(tmp_path), "--recordings", str(recordings)]
    assert cli.main([*argv, "--model", MODEL]) == 0
    (folder,) = tmp_path.iterdir()
    replayed = json.loads((folder / "submission.json").read_text(encoding="utf-8"))
    assert (
        replayed["requirements"]
        == recorded.submission.model_dump(mode="json", exclude_none=True)["requirements"]
    )
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert meta["calls"]["live"] == 0
    assert meta["tokens"] == recorded.metadata["tokens"]


def test_replay_fails_on_a_missing_recording(corpus_dir: Path, tmp_path: Path) -> None:
    argv = ["run", str(corpus_dir), "--out", str(tmp_path / "runs")]
    assert cli.main([*argv, "--recordings", str(tmp_path / "none"), "--model", MODEL]) == 2
    assert not (tmp_path / "runs").exists()


def test_live_run_over_budget_refuses_before_sending(corpus_dir: Path, tmp_path: Path) -> None:
    llm = ScriptedLLM()
    with pytest.raises(BudgetExceeded):
        run(
            corpus_dir,
            tmp_path / "runs",
            tmp_path / "rec",
            MODEL,
            live=llm,
            max_usd=0.0001,
            prices=PRICES,
        )
    assert llm.sent == []
    assert not (tmp_path / "rec").exists()


def test_live_run_with_an_unpriced_model_refuses(corpus_dir: Path, tmp_path: Path) -> None:
    llm = ScriptedLLM()
    with pytest.raises(BudgetExceeded, match="no price"):
        run(corpus_dir, tmp_path / "runs", tmp_path / "rec", MODEL, live=llm)
    assert llm.sent == []
