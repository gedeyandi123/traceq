"""``traceq demo``: refuses without the corpus, resets the database, brings the demo up (#115).

Nothing is sent to an LLM: the run is replayed from the committed recordings. The corpus is
the release manifest with empty placeholder documents, as replay needs only the document
hashes (see ``tests/test_recorded_runs.py``).
"""

from __future__ import annotations

import json
import shutil
import socket
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from conftest import ADMIN_URL
from sqlalchemy import create_engine, text

from traceq.app.demo import (
    DemoError,
    DemoSettings,
    bring_up,
    check_corpus,
    reset_database,
    run_demo,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "recordings" / "corpus-0.1.0" / "manifest.json"


def _corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    shutil.copy(MANIFEST, corpus / "manifest.json")
    for d in json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]:
        if d["equipment"] == "TP-201":
            (corpus / d["path"]).parent.mkdir(parents=True, exist_ok=True)
            (corpus / d["path"]).write_bytes(b"")
    return corpus


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _drop(name: str) -> None:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def demo_database(postgres_admin: object, tmp_path: Path) -> Iterator[str]:
    name = f"traceq_demo_test_{tmp_path.name[-8:].lower().replace('-', '_')}"
    yield name
    _drop(name)


def test_refuses_without_the_corpus_and_says_what_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_demo(DemoSettings(corpus=tmp_path / "nowhere", equipment="TP-201")) == 2
    err = capsys.readouterr().err
    assert "manifest.json" in err and "corpus release 0.1.0" in err


def test_refuses_a_corpus_without_its_documents(tmp_path: Path) -> None:
    shutil.copy(MANIFEST, tmp_path / "manifest.json")
    with pytest.raises(DemoError, match="lacks"):
        check_corpus(tmp_path, "TP-201")


def test_refuses_another_corpus_release(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text('{"version": "0.2.0", "documents": []}', "utf-8")
    with pytest.raises(DemoError, match=r"needs 0\.1\.0"):
        check_corpus(tmp_path, "TP-201")


def test_check_accepts_the_corpus(tmp_path: Path) -> None:
    check_corpus(_corpus(tmp_path), "TP-201")


def test_resetting_twice_gives_the_same_empty_state(demo_database: str) -> None:
    for _ in range(2):
        engine = create_engine(reset_database(ADMIN_URL, demo_database))
        with engine.begin() as conn:
            audit = conn.execute(text("SELECT count(*) FROM audit_trail")).scalar_one()
            tables = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
            ).scalar_one()
        engine.dispose()
        assert audit == 0 and tables > 0


def test_demo_comes_up_imported_and_a_second_run_resets(demo_database: str, tmp_path: Path) -> None:
    settings = DemoSettings(
        corpus=_corpus(tmp_path),
        equipment="TP-201",
        recordings=ROOT / "recordings" / "haiku-r7",
        runs=tmp_path / "runs",
        database=demo_database,
        issuer_port=_free_port(),
        api_port=_free_port(),
        compose=False,
    )
    for _ in range(2):
        demo = bring_up(settings)
        try:
            token = httpx.post(f"{demo.issuer_url}/demo/token", json={"username": "ayu"})
            got = httpx.get(
                f"{demo.api_url}/runs/{demo.run_id}/proposals",
                headers={"Authorization": f"Bearer {token.json()['access_token']}"},
            )
            assert got.status_code == 200
            assert len(got.json()) == 47
        finally:
            demo.stop()
