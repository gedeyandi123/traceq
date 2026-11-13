"""Shared fixtures: the recorded OCR output of the TP-201 scans, and no OCR model, as in CI.

``tests/fixtures/ingest/<doc>_rev<n>.json`` is what PP-OCRv6 small read on each scan, in the
ingest cache's format. To regenerate them, with the OCR model installed
(``uv sync --extra ocr``), ingest a rendered corpus with a cache directory and copy each
scan's ``<sha256>-<version>.json`` to ``<doc>_rev<n>.json``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from traceq.documents import Corpus, OcrUnavailable, scan

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def _seed(corpus_dir: Path, cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for d in Corpus.load(corpus_dir).documents:
        if d.format != "scan":
            continue
        data = json.loads((FIXTURES / f"{d.doc_id}_rev{d.rev}.json").read_text("utf-8"))
        data["doc_sha256"] = d.sha256
        target = cache / f"{d.sha256}-{data['version']}.json"
        target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="session")
def seed_scans() -> Callable[[Path, Path], None]:
    """Put the recorded OCR output of every scan of a corpus into an ingest cache, keyed by
    the bytes the test rendered."""
    return _seed


@pytest.fixture
def no_ocr_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """As in CI: the OCR model is not installed."""

    def unavailable() -> None:
        raise OcrUnavailable("the OCR model is not installed")

    monkeypatch.setattr(scan, "_engine", unavailable)
