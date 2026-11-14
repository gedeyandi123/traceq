"""The committed live Haiku runs (#45) replay to the scores they had live, at tolerance 0.

Each ``recordings/haiku-r<n>`` holds one live run per Equipment: its LLM recordings, its
ingest cache, the scorer report (``report-<tag>.json``) and the run metadata
(``run-<tag>.json``: cost, tokens, settings). Replay needs only the release manifest
(``recordings/corpus-0.1.0/manifest.json``): document hashes key the recordings and the
ingest cache, so CI downloads no corpus and runs neither Docling nor the OCR model.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from traceq.runs.run import run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.score import score
from traceq_eval.submission import Submission

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "recordings"
MANIFEST = RECORDINGS / "corpus-0.1.0"
MODEL = "claude-haiku-5-5"
WORLDS = {"TP-201": ROOT / "world" / "tp201.yaml", "TP-202": ROOT / "world" / "tp202.yaml"}
RUNS = ("haiku-r1", "haiku-r2", "haiku-r3")


@cache
def _pages(tag: str) -> PageTexts:
    return PageTexts(build_corpus(load(WORLDS[tag])))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("tag", sorted(WORLDS))
@pytest.mark.parametrize("name", RUNS)
def test_recorded_live_run_replays_to_its_live_scores(name: str, tag: str, tmp_path: Path) -> None:
    recordings = RECORDINGS / name
    live: dict[str, Any] = _json(recordings / f"run-{tag}.json")
    expected: dict[str, Any] = _json(recordings / f"report-{tag}.json")

    out = run(MANIFEST, tmp_path, recordings, MODEL, equipment=tag)
    sub = Submission.model_validate_json(
        (out.folder / "submission.json").read_text(encoding="utf-8")
    )
    got = score(sub, load_key(ROOT / "answer_key" / tag), _pages(tag))

    assert live["mode"] == "live" and live["settings"]["vendor_reuse"] is True
    assert out.metadata["calls"] == {
        "total": live["calls"]["total"],
        "replayed": live["calls"]["total"],
        "live": 0,
    }
    assert out.metadata["cost_usd"] == live["cost_usd"]
    assert got == {k: expected[k] for k in got}
