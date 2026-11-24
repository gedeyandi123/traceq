"""Shared fixtures: TP-201 built and rendered once per session, the recorded ingest output of
its scans and born-digital PDFs, no OCR model, as in CI, a Postgres database per test session,
and the demo issuer on a free local port.

``tests/fixtures/ingest/<doc>_rev<n>.json`` is what PP-OCRv6 small read on each scan, and what
Docling read on each born-digital PDF, in the ingest cache's format. To regenerate them, with
the OCR model installed (``uv sync --extra ocr``), ingest a rendered TP-201 with a cache
directory and copy each document's ``<sha256>-<version>.json`` to ``<doc>_rev<n>.json``. A
scan's recording is seeded under the hash of the bytes a test rendered; a PDF's must hold the
hash of the bytes it was read from (``tests/test_pdf.py`` checks it is current).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from sqlalchemy import URL, Connection, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from traceq.app.demo import ADMIN_URL as DEMO_ADMIN_URL
from traceq.db import APP_ROLE, OWNER_ROLE, engine, ensure_roles, upgrade
from traceq.documents import Corpus, OcrUnavailable, scan
from traceq.identity.issuer import create_issuer, new_signing_key
from traceq_dataset import render
from traceq_dataset.corpus import Corpus as DatasetCorpus
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"

_DB_FIXTURES = frozenset({"postgres_admin", "new_database", "databases", "fresh_database"})
_SLOW_FILES = frozenset(
    {
        "test_render.py",
        "test_degrade.py",
        "test_pack_release.py",
        "test_ocr.py",
        "test_ingest.py",
        "test_pdf.py",
        "test_segmentation.py",
        "test_tp202.py",
        "test_pw001.py",
        "test_recorded_runs.py",
        "test_run.py",
        "test_no_llm.py",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Partition collected tests into db, slow, and fast (not slow and not db)."""
    for item in items:
        if isinstance(item, pytest.Function) and _DB_FIXTURES.intersection(item.fixturenames):
            item.add_marker(pytest.mark.db)
        if (isinstance(item, pytest.Function) and "tp201_dist" in item.fixturenames) or (
            item.path.name in _SLOW_FILES
        ):
            item.add_marker(pytest.mark.slow)


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


def _seed_born_digital(corpus_dir: Path, cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for d in Corpus.load(corpus_dir).documents:
        if d.format != "born_digital":
            continue
        source = FIXTURES / f"{d.doc_id}_rev{d.rev}.json"
        data = json.loads(source.read_text("utf-8"))
        if data["doc_sha256"] != d.sha256:
            pytest.fail(f"{source.name} was read from other bytes; regenerate it")
        shutil.copyfile(source, cache / f"{d.sha256}-{data['version']}.json")


@pytest.fixture(scope="session")
def seed_born_digital() -> Callable[[Path, Path], None]:
    """Put the recorded Docling output of every born-digital PDF of TP-201 into an ingest
    cache, so Docling does not run."""
    return _seed_born_digital


# --- TP-201 ---------------------------------------------------------------------------
# Built and rendered once per session. Both are shared: a test that writes copies them.
TP201 = Path(__file__).parents[1] / "world" / "tp201.yaml"


@pytest.fixture(scope="session")
def tp201_corpus() -> DatasetCorpus:
    """TP-201 as the dataset builds it: what the scorer reads."""
    return build_corpus(load(TP201))


@pytest.fixture(scope="session")
def tp201_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """TP-201 rendered as a released corpus directory: what the system reads. Read-only."""
    out = tmp_path_factory.mktemp("tp201-dist")
    assert render.main([str(TP201), "--out", str(out)]) == 0
    return next(out.glob("t0-*"))


@pytest.fixture
def no_ocr_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """As in CI: the OCR model is not installed."""

    def unavailable() -> None:
        raise OcrUnavailable("the OCR model is not installed")

    monkeypatch.setattr(scan, "_engine", unavailable)


# --- Postgres -------------------------------------------------------------------------
# A superuser connection to a server (Compose locally, the service container in CI). Each
# session creates databases with unique names and drops them at the end, because two
# implementers may share one server; the roles belong to the server and are never dropped.
ADMIN_URL = os.environ.get("TRACEQ_TEST_ADMIN_URL", DEMO_ADMIN_URL)


@dataclass(frozen=True)
class Databases:
    """One migrated database, as the role that owns it and as the application role."""

    owner: URL
    app: URL


_unreachable: list[str] = []


@pytest.fixture(scope="session")
def postgres_admin() -> Iterator[Connection]:
    # pytest runs a failed session fixture again for every test that needs it, and a refused
    # connection takes seconds on Windows: the first failure is remembered.
    if not _unreachable:
        try:
            conn = create_engine(
                ADMIN_URL, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5}
            ).connect()
        except OperationalError as e:
            where = make_url(ADMIN_URL).render_as_string(hide_password=True)
            _unreachable.append(
                f"Postgres is not reachable at {where} ({type(e).__name__}); start it with"
                " `docker compose up -d postgres` or set TRACEQ_TEST_ADMIN_URL"
            )
        else:
            with conn:
                ensure_roles(conn)
                yield conn
            return
    if os.environ.get("CI"):
        pytest.fail(_unreachable[0])
    pytest.skip(_unreachable[0])


@pytest.fixture(scope="session")
def new_database(postgres_admin: Connection) -> Iterator[Callable[[], Databases]]:
    """Creates a database owned by the owner role and migrated from zero."""
    created: list[str] = []

    def create() -> Databases:
        name = f"traceq_test_{uuid4().hex[:12]}"
        postgres_admin.execute(text(f'CREATE DATABASE "{name}" OWNER {OWNER_ROLE}'))
        created.append(name)
        server = make_url(ADMIN_URL).set(database=name)
        dbs = Databases(
            owner=server.set(username=OWNER_ROLE, password=OWNER_ROLE),
            app=server.set(username=APP_ROLE, password=APP_ROLE),
        )
        upgrade(dbs.owner)
        return dbs

    yield create
    for name in created:
        postgres_admin.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="session")
def databases(new_database: Callable[[], Databases]) -> Databases:
    """The session's database, shared by its tests."""
    return new_database()


@pytest.fixture
def fresh_database(new_database: Callable[[], Databases]) -> Iterator[Databases]:
    """A database of its own, just migrated from zero.

    ``traceq.db.engine`` keeps one engine (and pool) per URL for the process, so without the
    disposal every test would leave its pool's idle connections open until the session ends,
    and enough such tests exhaust the server's connection slots."""
    dbs = new_database()
    yield dbs
    for url in (dbs.app, dbs.owner):
        engine(url).dispose()


# --- Demo issuer ----------------------------------------------------------------------
# The demo issuer runs as its own application on a free local port, so the JWKS is fetched
# over HTTP as it will be from Keycloak. The tests hold its signing key to forge the tokens
# it would never sign (expired, another audience, another issuer).
@dataclass(frozen=True)
class DemoIssuer:
    url: str
    audience: str
    key: RSAPrivateKey


@pytest.fixture(scope="session")
def demo_issuer() -> Iterator[DemoIssuer]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    key = new_signing_key()
    audience = "traceq-test"
    server = uvicorn.Server(
        uvicorn.Config(create_issuer(url, audience=audience, key=key), log_level="warning")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("the demo issuer did not start")
        time.sleep(0.01)
    try:
        yield DemoIssuer(url=url, audience=audience, key=key)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
