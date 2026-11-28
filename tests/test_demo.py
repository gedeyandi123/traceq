"""``scripts/demo.py``: refuses without the corpus, resets the database, brings the demo up (#115).

Nothing is sent to an LLM: the run is replayed from the committed recordings. The corpus is
the release manifest with empty placeholder documents, as replay needs only the document
hashes (see ``tests/test_recorded_runs.py``).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import ADMIN_URL
from sqlalchemy import create_engine, text

from traceq.app.demo import (
    DemoError,
    DemoSettings,
    bring_up,
    check_corpus,
    check_pair,
    reset_database,
    run_demo,
    serve_args,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "recordings" / "corpus-0.1.1" / "manifest.json"
R10 = ROOT / "recordings" / "haiku-r10"
PACKAGE = ROOT / "recordings" / "TP-201-OQ-draft-0.1.0"
PACKAGE_RUN = ROOT / "recordings" / "haiku-oq-draft-r3"


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
    settings = DemoSettings(corpus=tmp_path / "nowhere", equipment="TP-201", recordings=R10)
    assert run_demo(settings) == 2
    err = capsys.readouterr().err
    assert "manifest.json" in err and "corpus release" in err


def _release(tmp_path: Path, version: str = "0.2.0") -> Path:
    """A corpus release of another version whose documents match their manifest hashes."""
    corpus = tmp_path / "release"
    corpus.mkdir()
    docs = []
    for name, rev in (("URS-X_rev0.pdf", 0), ("URS-X_rev1.pdf", 1), ("SAT-X_rev0.pdf", 0)):
        data = name.encode()
        (corpus / "TP-201").mkdir(exist_ok=True)
        (corpus / "TP-201" / name).write_bytes(data)
        docs.append(
            {
                "path": f"TP-201/{name}",
                "equipment": "TP-201",
                "doc_id": name.split("_")[0],
                "rev": rev,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    (corpus / "manifest.json").write_text(json.dumps({"version": version, "documents": docs}))
    return corpus


def _recordings(tmp_path: Path, corpus: Path, skip: str | None = None) -> Path:
    """A recordings directory with an ingest entry for every document of ``corpus``."""
    rec = tmp_path / "rec"
    (rec / "ingest").mkdir(parents=True)
    for d in json.loads((corpus / "manifest.json").read_text())["documents"]:
        if d["path"] != skip:
            (rec / "ingest" / f"{d['sha256']}-docling-1.json").write_text("{}")
    return rec


def test_refuses_a_corpus_without_its_documents(tmp_path: Path) -> None:
    shutil.copy(MANIFEST, tmp_path / "manifest.json")
    with pytest.raises(DemoError, match="lacks"):
        check_corpus(tmp_path, "TP-201")


def test_check_accepts_any_release_and_names_its_version(tmp_path: Path) -> None:
    corpus = _release(tmp_path, "9.9.9")
    check_corpus(corpus, "TP-201")
    (corpus / "TP-201" / "SAT-X_rev0.pdf").unlink()
    with pytest.raises(DemoError, match=r"release 9\.9\.9"):
        check_corpus(corpus, "TP-201")


def test_refuses_a_document_whose_bytes_differ_from_the_manifest(tmp_path: Path) -> None:
    corpus = _release(tmp_path)
    (corpus / "TP-201" / "SAT-X_rev0.pdf").write_bytes(b"corrupted")
    with pytest.raises(DemoError, match=r"TP-201/SAT-X_rev0\.pdf"):
        check_corpus(corpus, "TP-201")


def test_pair_check_accepts_the_0_1_1_manifest_with_r10(tmp_path: Path) -> None:
    corpus = tmp_path / "c"
    corpus.mkdir()
    shutil.copy(MANIFEST, corpus / "manifest.json")
    check_pair(corpus, "TP-201", R10)


def test_pair_check_accepts_another_version_and_skips_superseded_revisions(
    tmp_path: Path,
) -> None:
    corpus = _release(tmp_path, "9.9.9")
    # URS rev0 is superseded by rev1: the run reads only the latest revision, so it has no entry
    check_pair(corpus, "TP-201", _recordings(tmp_path, corpus, skip="TP-201/URS-X_rev0.pdf"))


def test_pair_check_names_the_release_the_directory_and_the_first_missing_document(
    tmp_path: Path,
) -> None:
    corpus = _release(tmp_path, "9.9.9")
    rec = _recordings(tmp_path, corpus, skip="TP-201/SAT-X_rev0.pdf")
    with pytest.raises(DemoError, match=r"9\.9\.9") as e:
        check_pair(corpus, "TP-201", rec)
    assert str(rec) in str(e.value) and "SAT-X" in str(e.value)


def test_a_wrong_pair_is_refused_before_the_database_is_touched(
    demo_database: str, tmp_path: Path
) -> None:
    app_url = reset_database(ADMIN_URL, demo_database)
    engine = create_engine(app_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_trail (subject, issuer, name, action, record_type, record_id)"
                " VALUES ('s', 'i', 'n', 'a', 't', 'r')"
            )
        )
    corpus = _release(tmp_path)
    settings = DemoSettings(
        corpus=corpus,
        equipment="TP-201",
        recordings=tmp_path / "no-recordings",
        runs=tmp_path / "runs",
        database=demo_database,
        compose=False,
    )
    with pytest.raises(DemoError, match="recordings"):
        bring_up(settings)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_trail")).scalar_one() == 1
    engine.dispose()


def test_the_script_requires_the_recordings_argument() -> None:
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "demo.py"), "corpus"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2 and "--recordings" in done.stderr


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


def test_demo_comes_up_imported_and_a_second_run_resets(
    demo_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The placeholder documents are empty, so their bytes cannot match the manifest hashes;
    # the hash check is tested above on a release with real bytes.
    monkeypatch.setattr("traceq.app.demo.check_corpus", lambda *_a: None)
    settings = DemoSettings(
        corpus=_corpus(tmp_path),
        equipment="TP-201",
        recordings=R10,
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
            # r10, after #101 dropped 3 certificate findings: 45, and its 31 drafted Test
            # Steps (spec #247)
            kinds = [p["kind"] for p in got.json()]
            assert (len(kinds), kinds.count("test_step")) == (76, 31)
        finally:
            demo.stop()


def test_a_review_package_needs_its_recordings_before_anything_starts(tmp_path: Path) -> None:
    for package, recordings in ((PACKAGE, None), (None, PACKAGE_RUN)):
        settings = DemoSettings(
            corpus=tmp_path / "no-corpus",
            equipment="TP-201",
            recordings=R10,
            review_package=package,
            package_recordings=recordings,
        )
        with pytest.raises(DemoError, match="--review-package and --package-recordings"):
            bring_up(settings)


def test_the_demo_serves_uploads_in_replay_mode_with_a_zero_budget(tmp_path: Path) -> None:
    """Ticket #392: with a Review Package the API starts with uploads on, replaying only."""
    settings = DemoSettings(
        corpus=tmp_path / "corpus",
        equipment="TP-201",
        recordings=R10,
        uploads=tmp_path / "uploads",
        review_package=PACKAGE,
        package_recordings=PACKAGE_RUN,
    )
    args = serve_args(settings)
    assert args[args.index("--uploads") + 1] == str(tmp_path / "uploads")
    assert args[args.index("--upload-equipment") + 1] == "TP-201"
    assert args[args.index("--recordings") + 1] == str(R10)
    assert args[args.index("--package-recordings") + 1] == str(PACKAGE_RUN)
    assert args[args.index("--upload-budget-usd") + 1] == "0"
    assert args[args.index("--review-package") + 1] == str(PACKAGE)
    assert "--live" not in args
    bare = serve_args(DemoSettings(corpus=tmp_path, equipment="TP-201", recordings=R10))
    assert "--uploads" not in bare
    assert "--review-package" not in bare


def test_the_demo_loads_the_review_package_draft_at_start(
    demo_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec #196, ticket #210: the draft is loaded with the package at start, no upload; its
    findings are imported with the run, and the stores it replays are only read."""
    monkeypatch.setattr("traceq.app.demo.check_corpus", lambda *_a: None)
    before = sorted(p.stat().st_mtime_ns for p in PACKAGE_RUN.rglob("*"))
    settings = DemoSettings(
        corpus=_corpus(tmp_path),
        equipment="TP-201",
        recordings=R10,
        runs=tmp_path / "runs",
        database=demo_database,
        issuer_port=_free_port(),
        api_port=_free_port(),
        compose=False,
        uploads=tmp_path / "uploads",
        review_package=PACKAGE,
        package_recordings=PACKAGE_RUN,
    )
    demo = bring_up(settings)
    try:
        token = httpx.post(f"{demo.issuer_url}/demo/token", json={"username": "citra"})
        assert httpx.get(f"{demo.api_url}/runs/{demo.run_id}").status_code == 401
        run = httpx.get(
            f"{demo.api_url}/runs/{demo.run_id}",
            headers={"Authorization": f"Bearer {token.json()['access_token']}"},
        )
        assert run.json()["review_package"] == {
            "package": "TP-201-OQ-draft",
            "version": "0.1.0",
            "doc_id": "OQ-TP201",
            "rev": 0,
        }
        got = httpx.get(
            f"{demo.api_url}/runs/{demo.run_id}/protocol-draft",
            headers={"Authorization": f"Bearer {token.json()['access_token']}"},
        ).json()
        assert got["imported"] is True and len(got["test_steps"]) == 26
        assert got["findings"] and all(f["proposal"] for f in got["findings"])
        ayu = httpx.post(f"{demo.issuer_url}/demo/token", json={"username": "ayu"})
        listed = httpx.get(
            f"{demo.api_url}/equipment/TP-201/drafts",
            headers={"Authorization": f"Bearer {ayu.json()['access_token']}"},
        )
        assert listed.status_code == 200
    finally:
        demo.stop()
    assert sorted(p.stat().st_mtime_ns for p in PACKAGE_RUN.rglob("*")) == before


def test_run_demo_prints_production_start_command_and_cleans_ready_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from traceq.app.demo import Demo, _write_ready_file

    ready = tmp_path / "demo-ready.json"
    _write_ready_file(
        ready,
        {
            "run_id": "r1",
            "api_url": "http://127.0.0.1:8000",
            "issuer_url": "http://127.0.0.1:9000",
        },
    )
    assert json.loads(ready.read_text(encoding="utf-8"))["run_id"] == "r1"

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    fake_demo = Demo(
        issuer=proc,
        api=proc,
        run_id="r1",
        issuer_url="http://127.0.0.1:9000",
        api_url="http://127.0.0.1:8000",
    )
    monkeypatch.setattr("traceq.app.demo.bring_up", lambda _s, log=None: fake_demo)
    monkeypatch.setattr(fake_demo, "stop", lambda: None)

    settings = DemoSettings(
        corpus=tmp_path,
        equipment="TP-201",
        recordings=R10,
        ready_file=ready,
    )
    assert run_demo(settings) == 1
    out = capsys.readouterr().out
    assert "npm run build && npm start" in out
    assert not ready.exists()


def test_run_demo_supports_keycloak_mode_with_none_issuer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from traceq.app.demo import Demo

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    fake_demo = Demo(
        issuer=None,
        api=proc,
        run_id="r1",
        issuer_url="http://127.0.0.1:8080/realms/traceq",
        api_url="http://127.0.0.1:8000",
    )
    monkeypatch.setattr("traceq.app.demo.bring_up", lambda _s, log=None: fake_demo)
    monkeypatch.setattr(fake_demo, "stop", lambda: None)

    settings = DemoSettings(
        corpus=tmp_path,
        equipment="TP-201",
        recordings=R10,
        idp="keycloak",
    )
    assert run_demo(settings) == 1


def test_keycloak_pkce_token_exchanges_code_with_s256_and_prompt_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from traceq.app.demo import keycloak_pkce_token

    seen: dict[str, Any] = {}

    class _FakeResp:
        def __init__(
            self,
            status_code: int,
            *,
            text: str = "",
            headers: dict[str, str] | None = None,
            json_data: Any = None,
            cookies: dict[str, str] | None = None,
        ) -> None:
            self.status_code = status_code
            self.text = text
            self.headers = headers or {}
            self._json = json_data
            self.cookies = cookies or {}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self) -> Any:
            return self._json

    class _FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def get(self, url: str, params: dict[str, str]) -> _FakeResp:
            seen["auth_url"] = url
            seen["auth_params"] = params
            return _FakeResp(
                200,
                text='<form action="http://127.0.0.1:8080/login-actions/authenticate?tab_id=1&amp;x=2">',
                cookies={"AUTH_SESSION_ID": "abc"},
            )

        def post(
            self,
            url: str,
            data: dict[str, str],
            headers: dict[str, str] | None = None,
        ) -> _FakeResp:
            if "login-actions" in url:
                seen["login_url"] = url
                seen["login_data"] = data
                seen["login_headers"] = headers
                return _FakeResp(
                    302,
                    headers={
                        "location": "http://127.0.0.1:3000/api/auth/callback?code=auth-code-1"
                    },
                )
            seen["token_url"] = url
            seen["token_data"] = data
            return _FakeResp(200, json_data={"access_token": "kc-pkce-tok"})

    monkeypatch.setattr("traceq.app.demo.httpx.Client", _FakeClient)
    tok = keycloak_pkce_token("http://127.0.0.1:8080/realms/traceq", "ayu")
    assert tok == "kc-pkce-tok"
    assert seen["auth_params"]["client_id"] == "traceq-web"
    assert seen["auth_params"]["code_challenge_method"] == "S256"
    assert seen["auth_params"]["prompt"] == "login"
    assert seen["auth_params"]["max_age"] == "0"
    assert seen["login_url"] == "http://127.0.0.1:8080/login-actions/authenticate?tab_id=1&x=2"
    assert seen["login_headers"] == {"Cookie": "AUTH_SESSION_ID=abc"}
    assert seen["token_data"]["grant_type"] == "authorization_code"
    assert seen["token_data"]["code"] == "auth-code-1"
    assert "code_verifier" in seen["token_data"]


def test_upload_drafts_mode_serves_uploads_in_replay_mode_with_zero_budget(
    tmp_path: Path,
) -> None:
    """Issue #449: --upload-drafts turns on replay-only uploads without a pre-loaded package."""
    settings = DemoSettings(
        corpus=tmp_path / "corpus",
        equipment="TP-201",
        recordings=R10,
        uploads=tmp_path / "uploads",
        upload_drafts=True,
        package_recordings=PACKAGE_RUN,
    )
    args = serve_args(settings)
    assert args[args.index("--uploads") + 1] == str(tmp_path / "uploads")
    assert args[args.index("--upload-equipment") + 1] == "TP-201"
    assert args[args.index("--recordings") + 1] == str(R10)
    assert args[args.index("--package-recordings") + 1] == str(PACKAGE_RUN)
    assert args[args.index("--upload-budget-usd") + 1] == "0"
    assert "--review-package" not in args
    assert "--live" not in args


def test_upload_drafts_requires_package_recordings_and_forbids_review_package(
    tmp_path: Path,
) -> None:
    """Issue #449: --upload-drafts needs --package-recordings and forbids --review-package."""
    no_rec = DemoSettings(
        corpus=tmp_path / "no-corpus",
        equipment="TP-201",
        recordings=R10,
        upload_drafts=True,
    )
    with pytest.raises(DemoError, match="--package-recordings"):
        bring_up(no_rec)

    both = DemoSettings(
        corpus=tmp_path / "no-corpus",
        equipment="TP-201",
        recordings=R10,
        upload_drafts=True,
        review_package=PACKAGE,
        package_recordings=PACKAGE_RUN,
    )
    with pytest.raises(DemoError, match="--review-package"):
        bring_up(both)
