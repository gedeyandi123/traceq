"""``traceq demo``: brings the demo to a known state, and resets it when run again (spec #105).

In order: Postgres through Docker Compose, the two server roles, the database dropped and
recreated by the owning role, the migrations, the committed recordings of the dev Equipment
replayed into a run folder (no LLM call: nothing is sent), the demo issuer and the API as local
processes, and the run imported through the API as a persona. Demo data is the dev Equipment
only (named by the caller, never hard-coded in system code); the held-out Equipment is never
loaded.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import URL, create_engine, make_url, text

from traceq.db import APP_ROLE, OWNER_ROLE, ensure_roles, upgrade

CORPUS_VERSION = "0.1.0"
MODEL = "claude-haiku-5-5"
DATABASE = "traceq"
DEMO_PERSONA = "ayu"
ADMIN_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres"


class DemoError(Exception):
    """The demo cannot start; the message says why and what to do."""


@dataclass(frozen=True)
class DemoSettings:
    corpus: Path
    equipment: str
    recordings: Path = Path("recordings/haiku-r7")
    runs: Path = Path("runs-demo")
    admin_url: str = ADMIN_URL
    database: str = DATABASE
    issuer_port: int = 9000
    api_port: int = 8000
    compose: bool = True


def check_corpus(corpus: Path, equipment: str) -> None:
    """Refuses unless ``corpus`` is the extracted corpus release 0.1.0 with the documents of
    ``equipment``."""
    manifest = corpus / "manifest.json"
    if not corpus.is_dir() or not manifest.is_file():
        raise DemoError(
            f"{corpus} is not the extracted corpus release {CORPUS_VERSION}: it has no"
            " manifest.json. Download the corpus release asset from the GitHub Releases page"
            " and extract it, then pass its directory."
        )
    data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("version") != CORPUS_VERSION:
        raise DemoError(
            f"{corpus} holds corpus release {data.get('version')}, the demo needs {CORPUS_VERSION}"
        )
    missing = [
        str(d["path"])
        for d in data["documents"]
        if d["equipment"] == equipment and not (corpus / str(d["path"])).is_file()
    ]
    if missing:
        raise DemoError(
            f"{corpus} lacks {len(missing)} {equipment} documents (first: {missing[0]});"
            " extract the whole corpus release"
        )


def database_urls(admin_url: str, database: str) -> tuple[URL, URL, URL]:
    """The maintenance database as the owner role, and ``database`` as the owner role and as
    the application role."""
    server = make_url(admin_url)
    owner = server.set(username=OWNER_ROLE, password=OWNER_ROLE)
    return (
        owner,
        owner.set(database=database),
        server.set(username=APP_ROLE, password=APP_ROLE, database=database),
    )


def reset_database(admin_url: str, database: str) -> URL:
    """Creates the roles if missing, drops ``database`` and recreates it as the owner role,
    and applies the migrations. Returns the application role's URL. Dropping the database is
    what resets the decisions (and the Audit Trail: the limit the README names)."""
    admin = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5}
    )
    try:
        with admin.connect() as conn:
            ensure_roles(conn)
    finally:
        admin.dispose()
    maintenance_url, owner, app = database_urls(admin_url, database)
    maintenance = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with maintenance.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{database}" OWNER {OWNER_ROLE}'))
    finally:
        maintenance.dispose()
    upgrade(owner)
    return app


def _port_free(port: int) -> bool:
    with closing(socket.socket()) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait(url: str, what: str, proc: subprocess.Popen[bytes], timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise DemoError(f"the {what} stopped at start-up (exit code {proc.returncode})")
        try:
            httpx.get(url, timeout=2).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise DemoError(f"the {what} did not answer at {url} within {timeout:.0f} s")


def _stop(*procs: subprocess.Popen[bytes] | None) -> None:
    """Stops the processes. On Windows the virtual environment's launcher starts the real
    interpreter as a child, so the whole tree goes (``terminate`` would orphan the server)."""
    for p in procs:
        if p is None or p.poll() is not None:
            continue
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, check=False
            )
        else:
            p.terminate()
    for p in procs:
        if p is not None:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


@dataclass
class Demo:
    """A running demo: the two local processes and what was imported."""

    issuer: subprocess.Popen[bytes]
    api: subprocess.Popen[bytes]
    run_id: str
    issuer_url: str
    api_url: str

    def stop(self) -> None:
        _stop(self.api, self.issuer)


def start_postgres() -> None:
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait", "postgres"], check=True, timeout=300
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise DemoError(
            f"could not start Postgres with Docker Compose ({e}); is Docker running?"
        ) from e


def bring_up(settings: DemoSettings, log: Callable[[str], None] = lambda _msg: None) -> Demo:
    """Everything the demo command does except waiting. Raises ``DemoError``."""
    check_corpus(settings.corpus, settings.equipment)
    for port, what in ((settings.issuer_port, "issuer"), (settings.api_port, "API")):
        if not _port_free(port):
            raise DemoError(
                f"port {port} is in use; stop the earlier demo (Ctrl-C) before the {what} starts"
            )
    if settings.compose:
        log("starting Postgres (Docker Compose)")
        start_postgres()
    log("resetting the database")
    try:
        app_url = reset_database(settings.admin_url, settings.database)
    except Exception as e:  # driver, Alembic and SQLAlchemy errors share no base we can name
        raise DemoError(f"could not reset the database: {e}") from e

    log(f"replaying the {settings.equipment} recordings (nothing is sent to an LLM)")
    from traceq.ai import MissingRecording
    from traceq.documents import OcrUnavailable
    from traceq.runs.run import run

    shutil.rmtree(settings.runs, ignore_errors=True)
    try:
        out = run(
            settings.corpus, settings.runs, settings.recordings, MODEL, equipment=settings.equipment
        )
    except (MissingRecording, OcrUnavailable, FileNotFoundError, ValueError) as e:
        raise DemoError(f"the replay failed: {e}") from e
    run_id: str = out.metadata["run_id"]

    issuer_url = f"http://127.0.0.1:{settings.issuer_port}"
    api_url = f"http://127.0.0.1:{settings.api_port}"
    cli = [sys.executable, "-m", "traceq.app.cli"]
    log("starting the demo issuer and the API")
    issuer = subprocess.Popen([*cli, "demo-issuer", "--port", str(settings.issuer_port)])
    api: subprocess.Popen[bytes] | None = None
    try:
        _wait(f"{issuer_url}/demo/personas", "demo issuer", issuer)
        api = subprocess.Popen(
            [
                *cli,
                "serve",
                "--runs",
                str(settings.runs),
                "--corpus",
                str(settings.corpus),
                "--port",
                str(settings.api_port),
                "--issuer",
                issuer_url,
                "--database",
                app_url.render_as_string(hide_password=False),
            ]
        )
        _wait(f"{api_url}/runs", "API", api)
        log(f"importing {run_id} as {DEMO_PERSONA}")
        token = httpx.post(f"{issuer_url}/demo/token", json={"username": DEMO_PERSONA}, timeout=10)
        token.raise_for_status()
        imported = httpx.post(
            f"{api_url}/runs/{run_id}/import",
            headers={"Authorization": f"Bearer {token.json()['access_token']}"},
            timeout=60,
        )
        if imported.status_code != 200:
            raise DemoError(f"the import answered {imported.status_code}: {imported.text}")
    except BaseException:
        _stop(api, issuer)
        raise
    return Demo(issuer=issuer, api=api, run_id=run_id, issuer_url=issuer_url, api_url=api_url)
