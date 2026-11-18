"""The committed live Haiku runs (#45) replay to the scores they had live, at tolerance 0.

Each ``recordings/haiku-r<n>`` holds one live run per Equipment: its LLM recordings, its
ingest cache, the scorer report (``report-<tag>.json``) and the run metadata
(``run-<tag>.json``: cost, tokens, settings). Replay needs only the release manifest
(``recordings/corpus-0.1.1/manifest.json``): document hashes key the recordings and the
ingest cache, so CI downloads no corpus and runs neither Docling nor the OCR model.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import MissingRecording, Request, Response
from traceq.app import cli
from traceq.runs.run import run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.score import score
from traceq_eval.submission import Submission

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "recordings"
MANIFEST = RECORDINGS / "corpus-0.1.1"
MODEL = "claude-haiku-5-5"
WORLDS = {"TP-201": ROOT / "world" / "tp201.yaml", "TP-202": ROOT / "world" / "tp202.yaml"}
RUNS = ("haiku-r10",)


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
    assert out.metadata["prompts"] == live["prompts"]  # so ``system.prompt`` is unchanged
    assert got == {k: expected[k] for k in got}


# --- A Review Package run (spec #196, ticket #206) ----------------------------------------

PACKAGE = RECORDINGS / "TP-201-OQ-draft-0.1.0"
"""The committed release manifest of the Review Package: all the run reads of it so far."""
R10 = RECORDINGS / "haiku-r10"


def _stamps(root: Path) -> dict[str, int]:
    return {p.relative_to(root).as_posix(): p.stat().st_mtime_ns for p in root.rglob("*")}


class _NeverSends:
    """A live adapter that records what reaches it and fails the run if anything does."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.sent: list[Request] = []

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.sent += requests
        raise AssertionError("a Review Package run sent an Equipment call")


def test_review_package_run_replays_the_equipment_run_unchanged(tmp_path: Path) -> None:
    before = _stamps(R10)
    plain = run(MANIFEST, tmp_path / "plain", R10, MODEL, equipment="TP-201")
    out = run(
        MANIFEST,
        tmp_path / "runs",
        R10,
        MODEL,
        equipment="TP-201",
        review_package=PACKAGE,
        package_recordings=tmp_path / "package-rec",
    )

    assert _stamps(R10) == before  # the Equipment store is read, never written
    assert out.submission.model_dump(exclude={"system"}) == plain.submission.model_dump(
        exclude={"system"}
    )
    assert out.submission.system.prompt == plain.submission.system.prompt
    assert out.metadata["prompts"] == plain.metadata["prompts"]
    assert out.metadata["calls"] == plain.metadata["calls"]
    assert out.metadata["calls"]["live"] == 0
    assert out.metadata["cost_usd"] == plain.metadata["cost_usd"]
    assert out.metadata["review_package"] == {
        "package": "TP-201-OQ-draft",
        "version": "0.1.0",
        "corpus": {"release": "corpus-v0.1.1", "version": "0.1.1"},
        "equipment_recordings": "haiku-r10",
    }
    assert "review_package" not in plain.metadata


def test_live_review_package_run_fails_on_a_missing_equipment_recording(tmp_path: Path) -> None:
    """The Equipment stages are replay-only even in a live run: r10 holds no call for this
    model, so the first Equipment call fails the run before anything is sent."""
    before = _stamps(R10)
    live = _NeverSends("another-model")
    with pytest.raises(MissingRecording, match="replay only"):
        run(
            MANIFEST,
            tmp_path / "runs",
            R10,
            "another-model",
            equipment="TP-201",
            live=live,
            review_package=PACKAGE,
            package_recordings=tmp_path / "package-rec",
        )
    assert live.sent == []
    assert _stamps(R10) == before
    assert not (tmp_path / "runs").exists()


def _package(tmp_path: Path, field: tuple[str, ...], value: Any) -> Path:
    manifest = _json(PACKAGE / "manifest.json")
    node = manifest
    for key in field[:-1]:
        node = node[key]
    node[field[-1]] = value
    folder = tmp_path / "package"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        (("corpus", "manifest_sha256"), "0" * 64, "corpus release"),
        (("equipment",), "TP-999", "TP-999"),
        (("dataset",), "traceq-corpus", "not a Review Package"),
    ],
)
def test_a_package_that_does_not_fit_the_corpus_is_refused(
    tmp_path: Path, field: tuple[str, ...], value: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        run(
            MANIFEST,
            tmp_path / "runs",
            R10,
            MODEL,
            equipment="TP-201",
            review_package=_package(tmp_path, field, value),
            package_recordings=tmp_path / "package-rec",
        )
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("package_recordings", [None, R10, R10 / "."])
def test_a_package_run_never_writes_into_the_equipment_store(
    tmp_path: Path, package_recordings: Path | None
) -> None:
    with pytest.raises(ValueError, match="package recordings"):
        run(
            MANIFEST,
            tmp_path / "runs",
            R10,
            MODEL,
            equipment="TP-201",
            review_package=PACKAGE,
            package_recordings=package_recordings,
        )


def test_cli_refuses_a_package_run_without_package_recordings(tmp_path: Path) -> None:
    argv = ["run", str(MANIFEST), "--equipment", "TP-201", "--recordings", str(R10)]
    assert cli.main([*argv, "--out", str(tmp_path), "--review-package", str(PACKAGE)]) == 2
    assert not list(tmp_path.iterdir())
