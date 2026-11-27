"""Safety of uploads before a live ceiling is set (#411): the flag, the runner's live adapter,
the batch deadline and the replay check. No database, no live call."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from traceq import audit
from traceq.ai.cloud import CloudLLM
from traceq.ai.port import LLMError, Prompt, Request
from traceq.app import cli
from traceq.uploads import UploadSettings, package_runner, runner
from traceq.uploads.api import has_model_recording
from traceq.uploads.store import Job


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-0.01"])
def test_serve_refuses_a_budget_that_is_not_finite_and_not_negative(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["serve", f"--upload-budget-usd={value}"]) == 2
    assert "--upload-budget-usd" in capsys.readouterr().err


def _job(reserved: str) -> Job:
    return Job(
        id=1,
        at=datetime.now(UTC),
        equipment="TP-201",
        rev=0,
        sha256="a" * 64,
        size_bytes=3,
        pages=1,
        status="running",
        reserved_usd=Decimal(reserved),
        cost_usd=None,
        run_id=None,
        message=None,
        started_at=None,
        finished_at=None,
        actor=audit.Actor(subject="s", issuer="i", name="n"),
    )


@pytest.mark.parametrize(
    ("reserved", "budget", "expect_live"),
    [("0", 0.05, False), ("0.02", 0.05, True), ("0.02", 0.0, False)],
)
def test_package_runner_passes_a_live_adapter_only_for_a_reserved_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reserved: str,
    budget: float,
    expect_live: bool,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manifest.json").write_text(json.dumps({"version": "1"}))
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    seen: dict[str, Any] = {}

    def fake_run(*_a: Any, **kw: Any) -> Any:
        seen.update(kw)
        return SimpleNamespace(metadata={"run_id": "r", "live_cost_usd": 0.0})

    monkeypatch.setattr(runner, "run", fake_run)
    sentinel: Any = object()
    settings = UploadSettings(
        equipment="TP-201",
        store=tmp_path / "store",
        corpus=corpus,
        recordings=tmp_path / "rec",
        package_recordings=tmp_path / "prec",
        model="m",
        budget_usd=budget,
        live=lambda: sentinel,
    )
    package_runner(settings, tmp_path / "runs")(_job(reserved), pdf)
    assert (seen["live"] is sentinel) is expect_live
    assert seen["live"] is None or seen["live"] is sentinel


# --- The batch deadline -----------------------------------------------------------------


class _Batches:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.polls = 0

    def create(self, **_kw: Any) -> Any:
        return SimpleNamespace(id="b1", processing_status="in_progress")

    def retrieve(self, _id: str) -> Any:
        self.polls += 1
        return SimpleNamespace(id="b1", processing_status="in_progress")

    def cancel(self, batch_id: str) -> Any:
        self.cancelled.append(batch_id)
        return SimpleNamespace(id=batch_id, processing_status="canceling")


def test_a_batch_past_its_deadline_is_cancelled_and_fails() -> None:
    batches = _Batches()
    client: Any = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    llm = CloudLLM("m", client=client, poll_seconds=0.01, deadline_seconds=0.05)
    prompt = Prompt(name="p", system="s", schema={"type": "object"}, max_tokens=10)
    request = Request(prompt=prompt, user="u", doc_sha256="d")
    with pytest.raises(LLMError, match="deadline"):
        llm.complete([request])
    assert batches.cancelled == ["b1"] and batches.polls >= 1


def test_the_serve_adapter_has_a_deadline() -> None:
    assert 0 < cli.UPLOAD_BATCH_DEADLINE_SECONDS <= 3600


# --- Replay needs the model recording ----------------------------------------------------


def test_an_ingest_file_alone_is_not_a_model_recording(tmp_path: Path) -> None:
    sha = "b" * 64
    (tmp_path / "ingest").mkdir()
    (tmp_path / "ingest" / f"{sha}-docling-1.json").write_text("{}")
    assert not has_model_recording(tmp_path, sha, "m")
    (tmp_path / "k1.json").write_text(json.dumps({"doc_sha256": "c" * 64, "model": "m"}))
    (tmp_path / "k2.json").write_text(json.dumps({"doc_sha256": sha, "model": "other"}))
    assert not has_model_recording(tmp_path, sha, "m")
    (tmp_path / "k3.json").write_text(json.dumps({"doc_sha256": sha, "model": "m"}))
    assert has_model_recording(tmp_path, sha, "m")
    assert not has_model_recording(tmp_path / "missing", sha, "m")
