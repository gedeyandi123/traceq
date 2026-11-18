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
from unittest.mock import ANY

import pytest

from traceq.ai import MissingRecording, Request, Response
from traceq.app import cli
from traceq.runs.run import RunOutput, run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.review_package import load_package, load_package_key, render_draft
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.score import ReviewPackage, score
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


# --- A Review Package run (spec #196, tickets #206 and #207) ------------------------------

PACKAGE = RECORDINGS / "TP-201-OQ-draft-0.1.0"
"""The committed release manifest of the Review Package: the run reads the draft's pages from
the ingest cache, so it needs no PDF."""
R10 = RECORDINGS / "haiku-r10"
PACKAGE_RUN = ROOT / "tests" / "fixtures" / "review-package-run"
"""Fixture recordings of the draft calls and the draft's ingest (see its README)."""


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


def test_review_package_run_replays_the_equipment_run_unchanged(
    runs: tuple[RunOutput, RunOutput],
) -> None:
    plain, out = runs

    package_only = {"system", "review_package", "draft_steps"}
    assert out.submission.model_dump(exclude=package_only) == plain.submission.model_dump(
        exclude=package_only
    )
    # The draft prompt's hash enters the prompt set only in a Review Package run.
    assert out.metadata["prompts"] == {**plain.metadata["prompts"], "protocol_draft": ANY}
    assert "protocol_draft" not in plain.metadata["prompts"]
    draft = out.metadata["review_package"]["calls"]["total"]
    assert draft == 8  # one call per page of the draft
    assert out.metadata["calls"] == {
        "total": plain.metadata["calls"]["total"] + draft,
        "replayed": plain.metadata["calls"]["total"] + draft,
        "live": 0,
    }
    assert out.metadata["live_cost_usd"] == 0.0
    assert out.metadata["review_package"] | {"calls": None} == {
        "package": "TP-201-OQ-draft",
        "version": "0.1.0",
        "corpus": {"release": "corpus-v0.1.1", "version": "0.1.1"},
        "equipment_recordings": "haiku-r10",
        "document": {
            "doc_id": "OQ-TP201",
            "rev": 0,
            "sha256": "8a8c6860d5e7ec7dcb9b69ec8c1cd5da4037f9db7fef66071868ab3849614116",
        },
        "calls": None,
        "tokens": ANY,
        "cost_usd": ANY,
        "test_steps": 26,
        "trace_rows": 28,
        "not_compared": 26,
        "ingest": ANY,
    }
    assert "review_package" not in plain.metadata
    assert "review_package" not in json.loads(
        (plain.folder / "submission.json").read_text(encoding="utf-8")
    )
    assert not (plain.folder / "protocol_draft.json").exists()


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[RunOutput, RunOutput]:
    """An Equipment run and a Review Package run, both replayed from the committed stores,
    which neither writes."""
    before = _stamps(R10), _stamps(PACKAGE_RUN)
    out_dir = tmp_path_factory.mktemp("package-run")
    plain = run(MANIFEST, out_dir / "plain", R10, MODEL, equipment="TP-201")
    out = run(
        MANIFEST,
        out_dir / "runs",
        R10,
        MODEL,
        equipment="TP-201",
        review_package=PACKAGE,
        package_recordings=PACKAGE_RUN,
    )
    assert (_stamps(R10), _stamps(PACKAGE_RUN)) == before
    return plain, out


def test_review_package_run_replays_at_tolerance_0(runs: tuple[RunOutput, RunOutput]) -> None:
    """Same submission, same scores, zero live calls, same cost as the run that recorded the
    fixture; the scorer's AC reading works end to end."""
    _, out = runs
    recorded: dict[str, Any] = _json(PACKAGE_RUN / "run.json")
    expected: dict[str, Any] = _json(PACKAGE_RUN / "report.json")
    sub = Submission.model_validate_json(
        (out.folder / "submission.json").read_text(encoding="utf-8")
    )
    package = load_package(ROOT / "world" / "tp201-oq-draft.yaml")
    corpus = build_corpus(load(WORLDS["TP-201"]))
    review = ReviewPackage.of(
        package,
        render_draft(package, corpus.eq),
        load_package_key(ROOT / "answer_key" / "TP-201-OQ-draft"),
    )
    got = score(
        sub,
        load_key(ROOT / "answer_key" / "TP-201"),
        PageTexts(corpus, extra=[review.draft]),
        package=review,
    )

    assert sub.review_package == "TP-201-OQ-draft"
    assert len(sub.draft_steps) == 26
    assert out.metadata["calls"]["live"] == 0
    assert out.metadata["cost_usd"] == recorded["cost_usd"]
    rp, rec = out.metadata["review_package"], recorded["review_package"]
    assert {k: rp[k] for k in ("tokens", "cost_usd", "not_compared")} == {
        k: rec[k] for k in ("tokens", "cost_usd", "not_compared")
    }
    assert rp["calls"] == {"total": 8, "replayed": 8, "live": 0}
    assert out.metadata["prompts"] == recorded["prompts"]
    assert out.metadata["dropped"] == recorded["dropped"]
    assert got["gates"] == expected["gates"]
    assert got["review_package"] == expected["review_package"]
    assert got["review_package"]["metrics"]["ac_read_right"] == 26
    assert [d["id"] for d in out.metadata["dropped"] if d["claim"] == "draft_step"] == [
        "OQ-TP201 p1 OQ-02"
    ]


def test_review_package_run_writes_the_draft_rows(runs: tuple[RunOutput, RunOutput]) -> None:
    _, out = runs
    rows: dict[str, Any] = _json(out.folder / "protocol_draft.json")
    assert rows["package"] == "TP-201-OQ-draft"
    first = rows["test_steps"][0]
    assert first["id"] == "OQ-01" and first["requirements"] == ["URS-TP201-001"]
    assert first["acceptance"]["citation"]["doc"] == "OQ-TP201"
    (traced,) = first["traced"]
    assert traced["requirement"] == "URS-TP201-001"
    assert traced["citation"]["doc"] == "URS-TP201" and traced["citation"]["rev"] == 1
    assert len(rows["trace_rows"]) == 28


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
