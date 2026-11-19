"""The committed held-out live run of PW-001 (#241) replays to its recorded scores, hash only.

``recordings/PW-001/haiku-r10`` holds the one live run on PW-001 (A5 of #133): its LLM
recordings, its ingest cache, the run metadata (``run.json``) and the scorer report
(``report.json``). Replay needs only the release manifest ``recordings/corpus-0.2.0``, so CI
downloads no corpus and runs neither Docling nor the OCR model.

PW-001 is held out. A failing check names only itself, with a fixed message: never a value,
the key of an item that differs, or a diff. So the checks compare SHA-256 digests of canonical
JSON and fail through ``pytest.fail(..., pytrace=False)``, never a bare ``assert a == b``,
whose rewriting would print both sides. Run this file only through ``scripts/heldout_run.sh``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from traceq.runs.run import RunOutput, run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.score import score
from traceq_eval.submission import Submission

ROOT = Path(__file__).resolve().parents[1]
TAG = "PW-001"
RECORDINGS = ROOT / "recordings" / TAG / "haiku-r10"
MANIFEST = ROOT / "recordings" / "corpus-0.2.0"
WORLD = ROOT / "world" / "pw001.yaml"
KEY = ROOT / "answer_key" / TAG
MODEL = "claude-haiku-5-5"

SECTIONS_MISSING = "the scored report has sections the recorded report lacks"
SCORES_DIFFER = "scores differ from the recorded report"


def digest(obj: Any) -> str:
    """SHA-256 of the canonical JSON of ``obj`` (sorted keys, fixed separators)."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scores_mismatch(got: Mapping[str, Any], expected: Mapping[str, Any]) -> str | None:
    """A fixed message when ``got`` differs from ``expected`` restricted to ``got``'s keys,
    else None. The message holds no key, value or diff of the reports."""
    if not set(got) <= set(expected):
        return SECTIONS_MISSING
    if digest(dict(got)) != digest({k: expected[k] for k in got}):
        return SCORES_DIFFER
    return None


def test_scores_mismatch_names_only_the_check() -> None:
    marker = "MARKER-7f3a9c"
    recorded = {"gates": {"passed": True}, "items": [{"id": "X-001", "class": "ok"}]}
    altered = {"gates": {"passed": True}, "items": [{"id": "X-001", "class": marker}]}

    assert scores_mismatch(recorded, {**recorded, "metadata": {"run": "r"}}) is None
    msg = scores_mismatch(altered, recorded)
    assert msg == SCORES_DIFFER
    assert marker not in msg and "X-001" not in msg and "items" not in msg

    extra = scores_mismatch({**recorded, marker: 1}, recorded)
    assert extra == SECTIONS_MISSING
    assert marker not in extra


def _check(ok: bool, message: str) -> None:
    if not ok:
        pytest.fail(message, pytrace=False)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _replay(out_dir: Path) -> tuple[RunOutput, dict[str, Any]] | None:
    """The replayed run and its scores, or None when either raised (the error is dropped,
    since its message could hold held-out text)."""
    try:
        out = run(MANIFEST, out_dir, RECORDINGS, MODEL, equipment=TAG)
        sub = Submission.model_validate_json(
            (out.folder / "submission.json").read_text(encoding="utf-8")
        )
        return out, score(sub, load_key(KEY), PageTexts(build_corpus(load(WORLD))))
    except Exception:
        return None


def test_heldout_live_run_replays_to_its_recorded_scores(tmp_path: Path) -> None:
    live: dict[str, Any] = _json(RECORDINGS / "run.json")
    expected: dict[str, Any] = _json(RECORDINGS / "report.json")
    _check(live.get("mode") == "live", "run.json is not a live run")
    _check(live.get("settings", {}).get("vendor_reuse") is True, "run.json has vendor_reuse off")

    replayed = _replay(tmp_path)
    if replayed is None:
        pytest.fail("the replay or the scoring raised", pytrace=False)
    out, got = replayed

    total = live["calls"]["total"]
    calls_ok = out.metadata["calls"] == {"total": total, "replayed": total, "live": 0}
    _check(calls_ok, "calls differ: not every recorded call replayed with none live")
    _check(out.metadata["cost_usd"] == live["cost_usd"], "cost differs from run.json")
    mismatch = scores_mismatch(got, expected)
    if mismatch is not None:
        pytest.fail(mismatch, pytrace=False)
