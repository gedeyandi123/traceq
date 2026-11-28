"""``scripts/demo.py``: brings the demo to a known state, and resets it when run again (spec #105).

In order: Postgres through Docker Compose, the two server roles, the database dropped and
recreated by the owning role, the migrations, the committed recordings of the dev Equipment
replayed into a run folder (no LLM call: nothing is sent), the demo issuer and the API as local
processes, and the run imported through the API as a persona. Demo data is the dev Equipment
only (named by the caller, never hard-coded in system code); the held-out Equipment is never
loaded.

With a Review Package (spec #196) the run is a Review Package run: the Equipment recordings
replay as before and the Protocol Draft is read from the package recordings, both only read
in replay, so the draft and its findings are loaded and imported at start. The API also
serves the browser upload of a Protocol Draft, replay only (budget 0: nothing is sent).
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import URL, create_engine, make_url, text

from traceq.db import APP_ROLE, OWNER_ROLE, ensure_roles, upgrade

MODEL = "claude-haiku-5-5"
DATABASE = "traceq"
DEMO_PERSONA = "ayu"
# A superuser connection to the local Compose Postgres; the test suite uses it too.
ADMIN_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres"


class DemoError(Exception):
    """The demo cannot start; the message says why and what to do."""


@dataclass(frozen=True)
class DemoSettings:
    corpus: Path
    equipment: str
    recordings: Path
    runs: Path = Path("runs-demo")
    admin_url: str = ADMIN_URL
    database: str = DATABASE
    issuer_port: int = 9000
    api_port: int = 8000
    compose: bool = True
    idp: Literal["demo", "keycloak"] = "demo"
    """Identity provider mode: ``demo`` (local demo-issuer) or ``keycloak`` (Compose IdP)."""
    keycloak_url: str = "http://127.0.0.1:8080/realms/traceq"
    """Issuer URL used when ``idp == 'keycloak'``."""
    uploads: Path = Path("uploads-demo")
    """Where uploaded drafts are stored; on only with a Review Package."""
    review_package: Path | None = None
    """A released Review Package directory for this corpus and Equipment."""
    package_recordings: Path | None = None
    """The recordings of the package's draft calls and ingest."""
    upload_drafts: bool = False
    """Enable replay-only draft uploads at budget 0 using ``package_recordings`` without
    pre-loading a Review Package draft at start."""
    ready_file: Path | None = None
    """Optional path written with JSON readiness metadata once the demo run is imported."""


def _manifest(corpus: Path) -> dict[str, Any]:
    manifest = corpus / "manifest.json"
    if not corpus.is_dir() or not manifest.is_file():
        raise DemoError(
            f"{corpus} is not an extracted corpus release: it has no manifest.json."
            " Download the corpus release asset from the GitHub Releases page and extract it,"
            " then pass its directory."
        )
    data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    return data


def check_corpus(corpus: Path, equipment: str) -> None:
    """Refuses unless ``corpus`` is an extracted corpus release holding every document of
    ``equipment`` with the SHA-256 of its manifest. The release is the manifest's own."""
    data = _manifest(corpus)
    version = data.get("version")
    docs = [d for d in data["documents"] if d["equipment"] == equipment]
    missing = [str(d["path"]) for d in docs if not (corpus / str(d["path"])).is_file()]
    if missing:
        raise DemoError(
            f"{corpus} lacks {len(missing)} {equipment} documents of corpus release {version}"
            f" (first: {missing[0]}); extract the whole corpus release"
        )
    for d in docs:
        if hashlib.sha256((corpus / str(d["path"])).read_bytes()).hexdigest() != d["sha256"]:
            raise DemoError(
                f"{d['path']} in {corpus} does not match the SHA-256 of corpus release"
                f" {version}; extract the release again"
            )


def check_pair(corpus: Path, equipment: str, recordings: Path) -> None:
    """Refuses unless ``recordings`` was made on the corpus release of ``corpus``: every
    document of ``equipment`` has an ingest entry (``ingest/<sha256>-<reader version>.json``).
    A superseded revision (a higher revision of the same document exists) is skipped: the run
    reads only the latest revision of each document, so it never ingests the older one."""
    data = _manifest(corpus)
    docs = [d for d in data["documents"] if d["equipment"] == equipment]
    latest: dict[str, int] = {}
    for d in docs:
        latest[str(d["doc_id"])] = max(latest.get(str(d["doc_id"]), d["rev"]), d["rev"])
    ingested = {p.name[:64] for p in (recordings / "ingest").glob("*.json")}
    for d in docs:
        if d["rev"] < latest[str(d["doc_id"])] or d["sha256"] in ingested:
            continue
        raise DemoError(
            f"the recordings in {recordings} were not made on corpus release {data.get('version')}"
            f" (no ingest entry for {d['doc_id']} rev {d['rev']}); pass the recordings set of"
            " that release"
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
    """A running demo: local processes (``issuer`` is ``None`` in keycloak mode) and run ID."""

    issuer: subprocess.Popen[bytes] | None
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


def start_keycloak() -> None:
    try:
        subprocess.run(
            ["docker", "compose", "--profile", "keycloak", "up", "-d", "--wait", "keycloak"],
            check=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise DemoError(
            f"could not start Keycloak with Docker Compose ({e}); is Docker running?"
        ) from e


def keycloak_pkce_token(
    issuer_url: str,
    username: str,
    password: str = "demo",
    *,
    client_id: str = "traceq-web",
    redirect_uri: str = "http://127.0.0.1:3000/api/auth/callback",
) -> str:
    """Mint a fresh Keycloak access token via Authorization Code + PKCE (S256) with
    ``prompt=login&max_age=0`` so ``auth_time`` is populated and fresh."""
    base = issuer_url.rstrip("/")
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")
    nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")
    with httpx.Client(follow_redirects=False, timeout=15) as client:
        auth_resp = client.get(
            f"{base}/protocol/openid-connect/auth",
            params={
                "client_id": client_id,
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": redirect_uri,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "login",
                "max_age": "0",
            },
        )
        auth_resp.raise_for_status()
        match = re.search(r'action="([^"]+)"', auth_resp.text)
        if match is None:
            raise DemoError("Keycloak login form did not include an action URL")
        action_url = html.unescape(match.group(1))
        # Keycloak sets Secure cookies even on loopback http://127.0.0.1:8080; httpx does not
        # auto-send Secure cookies over http://, so forward them explicitly.
        cookie_header = "; ".join(f"{k}={v}" for k, v in auth_resp.cookies.items())
        post_resp = client.post(
            action_url,
            data={"username": username, "password": password, "credentialId": ""},
            headers={"Cookie": cookie_header} if cookie_header else {},
        )
        location: str | None = post_resp.headers.get("location")
        if (
            post_resp.status_code not in (301, 302, 303)
            or not isinstance(location, str)
            or not location
        ):
            raise DemoError(
                f"Keycloak PKCE login failed for {username!r} (status {post_resp.status_code})"
            )
        qs: dict[str, list[str]] = parse_qs(urlsplit(location).query)
        codes = qs.get("code")
        code = codes[0] if codes else None
        if not code:
            raise DemoError(f"Keycloak redirect did not include an authorization code: {location}")
        token_resp = client.post(
            f"{base}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
        token_resp.raise_for_status()
        return str(token_resp.json()["access_token"])


def _demo_import_token(issuer_url: str, idp: Literal["demo", "keycloak"], username: str) -> str:
    if idp == "keycloak":
        return keycloak_pkce_token(issuer_url, username)
    resp = httpx.post(f"{issuer_url}/demo/token", json={"username": username}, timeout=10)
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def bring_up(settings: DemoSettings, log: Callable[[str], None] = lambda _msg: None) -> Demo:
    """Everything the demo command does except waiting. Raises ``DemoError``."""
    if settings.upload_drafts:
        if settings.review_package is not None:
            raise DemoError("--upload-drafts cannot be combined with --review-package")
        if settings.package_recordings is None:
            raise DemoError("--upload-drafts needs --package-recordings")
    elif (settings.review_package is None) != (settings.package_recordings is None):
        raise DemoError("a Review Package needs both --review-package and --package-recordings")
    check_corpus(settings.corpus, settings.equipment)
    check_pair(settings.corpus, settings.equipment, settings.recordings)
    release = _manifest(settings.corpus).get("version")
    log(f"corpus release {release}, recordings {settings.recordings}")
    if settings.idp not in ("demo", "keycloak"):
        raise DemoError(f"unsupported idp {settings.idp!r}; expected 'demo' or 'keycloak'")
    ports_to_check: list[tuple[int, str]] = [(settings.api_port, "API")]
    if settings.idp == "demo":
        ports_to_check.insert(0, (settings.issuer_port, "issuer"))
    for port, what in ports_to_check:
        if not _port_free(port):
            raise DemoError(
                f"port {port} is in use; stop the earlier demo (Ctrl-C) before the {what} starts"
            )
    if settings.compose:
        log("starting Postgres (Docker Compose)")
        start_postgres()
        if settings.idp == "keycloak":
            log("starting Keycloak (Docker Compose)")
            start_keycloak()
    log("resetting the database")
    try:
        app_url = reset_database(settings.admin_url, settings.database)
    except Exception as e:  # driver, Alembic and SQLAlchemy errors share no base we can name
        raise DemoError(f"could not reset the database: {e}") from e

    log(f"replaying the {settings.equipment} recordings (nothing is sent to an LLM)")
    if settings.upload_drafts:
        log(
            f"uploads on (replay only, budget 0) with {settings.package_recordings};"
            " no draft pre-loaded"
        )
    elif settings.review_package is not None:
        log(f"Review Package {settings.review_package}: draft loaded, uploads on, replay only")
    from traceq.ai import MissingRecording
    from traceq.documents import OcrUnavailable
    from traceq.runs.run import run

    shutil.rmtree(settings.runs, ignore_errors=True)
    try:
        out = run(
            settings.corpus,
            settings.runs,
            settings.recordings,
            MODEL,
            equipment=settings.equipment,
            review_package=settings.review_package,
            package_recordings=None if settings.upload_drafts else settings.package_recordings,
        )
    except (MissingRecording, OcrUnavailable, FileNotFoundError, ValueError) as e:
        raise DemoError(f"the replay failed: {e}") from e
    run_id: str = out.metadata["run_id"]

    if settings.idp == "keycloak":
        issuer_url = settings.keycloak_url.rstrip("/")
        role_claim = "realm_access.roles"
    else:
        issuer_url = f"http://127.0.0.1:{settings.issuer_port}"
        role_claim = "roles"
    api_url = f"http://127.0.0.1:{settings.api_port}"
    cli = [sys.executable, "-m", "traceq.app.cli"]
    issuer: subprocess.Popen[bytes] | None = None
    if settings.idp == "demo":
        log("starting the demo issuer and the API")
        issuer = subprocess.Popen([*cli, "demo-issuer", "--port", str(settings.issuer_port)])
    else:
        log("starting the API (Keycloak IdP)")
    api: subprocess.Popen[bytes] | None = None
    try:
        if issuer is not None:
            _wait(f"{issuer_url}/demo/personas", "demo issuer", issuer)
        api = subprocess.Popen(
            [
                *cli,
                *serve_args(
                    settings,
                    issuer_url=issuer_url,
                    role_claim=role_claim,
                    database_url=app_url.render_as_string(hide_password=False),
                ),
            ]
        )
        _wait(f"{api_url}/openapi.json", "API", api)
        log(f"importing {run_id} as {DEMO_PERSONA}")
        access_token = _demo_import_token(issuer_url, settings.idp, DEMO_PERSONA)
        imported = httpx.post(
            f"{api_url}/runs/{run_id}/import",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60,
        )
        if imported.status_code != 200:
            raise DemoError(f"the import answered {imported.status_code}: {imported.text}")
        if settings.ready_file is not None:
            _write_ready_file(
                settings.ready_file,
                {
                    "run_id": run_id,
                    "api_url": api_url,
                    "issuer_url": issuer_url,
                    "idp": settings.idp,
                    "role_claim": role_claim,
                },
            )
    except BaseException:
        _stop(api, issuer)
        raise
    return Demo(issuer=issuer, api=api, run_id=run_id, issuer_url=issuer_url, api_url=api_url)


def serve_args(
    settings: DemoSettings,
    *,
    issuer_url: str = "",
    role_claim: str = "roles",
    database_url: str = "",
) -> list[str]:
    """The ``traceq`` arguments that start the API. With a Review Package, uploads are on in
    replay mode: the budget is 0, so no live call can be made."""
    args = [
        "serve",
        "--runs",
        str(settings.runs),
        "--corpus",
        str(settings.corpus),
        "--port",
        str(settings.api_port),
        "--issuer",
        issuer_url,
        "--role-claim",
        role_claim,
        "--database",
        database_url,
    ]
    if settings.review_package is not None:
        args += ["--review-package", str(settings.review_package)]
    if (
        settings.review_package is not None or settings.upload_drafts
    ) and settings.package_recordings is not None:
        args += [
            "--uploads",
            str(settings.uploads),
            "--upload-equipment",
            settings.equipment,
            "--recordings",
            str(settings.recordings),
            "--package-recordings",
            str(settings.package_recordings),
            "--upload-budget-usd",
            "0",
        ]
    return args


def _write_ready_file(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def run_demo(settings: DemoSettings) -> int:
    """The demo command: brings the demo up, then waits in the foreground until Ctrl-C.
    Exit code 0 after Ctrl-C, 1 when a process stopped, 2 when it could not start."""
    try:
        demo = bring_up(settings, log=lambda msg: print(f"demo: {msg}", flush=True))
    except DemoError as e:
        print(f"demo: {e}", file=sys.stderr)
        return 2
    print(
        f"demo: ready. Postgres 127.0.0.1:5432, issuer {demo.issuer_url}, API"
        f" {demo.api_url} (run {demo.run_id} imported). Start the web UI with"
        " `cd web && npm run build && npm start`. Ctrl-C stops the issuer and the API.",
        flush=True,
    )
    try:
        while demo.api.poll() is None and (demo.issuer is None or demo.issuer.poll() is None):
            time.sleep(0.5)
        print("demo: a process stopped; stopping the demo", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if settings.ready_file is not None:
            settings.ready_file.unlink(missing_ok=True)
        demo.stop()
