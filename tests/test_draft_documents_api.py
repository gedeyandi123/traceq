"""Tests for serving Protocol Draft PDFs via runs/documents API (issue #455).

Covers ``extra_document`` in ``traceq.runs.api``, sequential resolution in
``traceq.app.api`` (``uploads.blobs`` then ``review_package/manifest.json``),
SHA-256 verification, path traversal & filename sanitization, ETag/304, and
``traceq serve --review-package``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import DemoIssuer
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from traceq.app import cli
from traceq.app.api import create_app
from traceq.identity import IdentitySettings, Verifier, authenticate
from traceq.runs.api import create_router
from traceq.uploads import UploadSettings
from traceq.uploads.store import save_blob

FIXTURE = Path(__file__).parent / "fixtures" / "run"
RUNS_FIXTURE = FIXTURE / "runs"
CORPUS_FIXTURE = FIXTURE / "corpus"
BASE_RUN_ID = "20261113T090000Z-f1a2b3"
DUMMY_DB = "postgresql+psycopg://u:p@127.0.0.1:5432/traceq_unused"
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _token(issuer: DemoIssuer) -> str:
    persona = httpx.get(f"{issuer.url}/demo/personas").json()[0]
    resp = httpx.post(f"{issuer.url}/demo/token", json={"username": persona["username"]})
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def _write_package_run(
    runs: Path,
    run_id: str,
    *,
    doc_id: str = "OQ-TP201",
    rev: int = 0,
    sha256: str,
    include_package: bool = True,
) -> Path:
    folder = runs / run_id
    folder.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = json.loads((RUNS_FIXTURE / BASE_RUN_ID / "run.json").read_text("utf-8"))
    meta["run_id"] = run_id
    if include_package:
        meta["review_package"] = {
            "package": "TP-201-OQ-draft",
            "version": "0.1.0",
            "document": {"doc_id": doc_id, "rev": rev, "sha256": sha256},
            "test_steps": 26,
        }
    else:
        meta.pop("review_package", None)
    (folder / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def _write_review_package(
    root: Path,
    *,
    package: str = "TP-201-OQ-draft",
    doc_id: str = "OQ-TP201",
    rev: int = 0,
    rel_disk_path: str = "OQ-TP201_rev0.pdf",
    manifest_path: str | None = None,
    pdf_bytes: bytes = PDF_BYTES,
    manifest_sha256: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    disk_file = root / rel_disk_path
    disk_file.parent.mkdir(parents=True, exist_ok=True)
    disk_file.write_bytes(pdf_bytes)
    sha = manifest_sha256 or hashlib.sha256(pdf_bytes).hexdigest()
    doc_path = manifest_path if manifest_path is not None else f"{package}/{rel_disk_path}"
    manifest = {
        "dataset": "traceq-review-package",
        "package": package,
        "version": "0.1.0",
        "equipment": "TP-201",
        "corpus": {"release": "corpus-v0.1.1", "version": "0.1.1", "manifest_sha256": "0" * 64},
        "documents": [
            {
                "path": doc_path,
                "doc_id": doc_id,
                "rev": rev,
                "type": "oq_protocol",
                "format": "born_digital",
                "language": "id",
                "sha256": sha,
            }
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _app_client(
    runs: Path,
    issuer: DemoIssuer,
    *,
    corpus: Path | None = None,
    uploads: UploadSettings | None = None,
    review_package: Path | None = None,
) -> TestClient:
    app = create_app(
        runs,
        corpus,
        identity=IdentitySettings(issuer=issuer.url, audience=issuer.audience),
        database=DUMMY_DB,
        uploads=uploads,
        review_package=review_package,
    )
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {_token(issuer)}"
    return client


def _upload_settings(tmp_path: Path, corpus: Path) -> UploadSettings:
    store = tmp_path / "uploads"
    (store / "files").mkdir(parents=True, exist_ok=True)
    return UploadSettings(
        equipment="TP-201",
        store=store,
        corpus=corpus,
        recordings=tmp_path / "rec",
        package_recordings=tmp_path / "pkg-rec",
        model="claude-haiku-5-5",
    )


def test_serves_draft_pdf_from_uploads_blobs_with_etag_and_304(
    tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=2, sha256=sha)
    uploads = _upload_settings(tmp_path, CORPUS_FIXTURE)
    save_blob(uploads.blobs, sha, PDF_BYTES)

    client = _app_client(runs, demo_issuer, corpus=CORPUS_FIXTURE, uploads=uploads)
    url = f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/2"

    head_res = client.head(url)
    assert head_res.status_code == 200
    assert head_res.content == b""
    assert head_res.headers["content-type"] == "application/pdf"
    assert head_res.headers["content-length"] == str(len(PDF_BYTES))
    assert head_res.headers["content-disposition"] == 'inline; filename="OQ-TP201_rev2.pdf"'
    assert head_res.headers["content-security-policy"] == "frame-ancestors 'self'"
    assert head_res.headers["cache-control"] == "private, max-age=300"
    assert head_res.headers["etag"] == f'"{sha}"'

    get_res = client.get(url)
    assert get_res.status_code == 200
    assert get_res.content == PDF_BYTES
    assert get_res.headers["content-type"] == "application/pdf"
    assert get_res.headers["etag"] == f'"{sha}"'

    assert client.head(url, headers={"If-None-Match": f'"{sha}"'}).status_code == 304
    not_mod = client.get(url, headers={"If-None-Match": f'"{sha}"'})
    assert not_mod.status_code == 304
    assert not_mod.content == b""
    assert not_mod.headers["etag"] == f'"{sha}"'
    assert not_mod.headers["cache-control"] == "private, max-age=300"


@pytest.mark.parametrize(
    ("rel_disk_path", "manifest_path"),
    [
        ("OQ-TP201_rev0.pdf", "TP-201-OQ-draft/OQ-TP201_rev0.pdf"),
        ("draft.pdf", "draft.pdf"),
    ],
)
def test_serves_draft_pdf_from_review_package_directory(
    tmp_path: Path,
    demo_issuer: DemoIssuer,
    rel_disk_path: str,
    manifest_path: str,
) -> None:
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=0, sha256=sha)
    pkg = _write_review_package(
        tmp_path / "package",
        rel_disk_path=rel_disk_path,
        manifest_path=manifest_path,
    )

    client = _app_client(runs, demo_issuer, corpus=CORPUS_FIXTURE, review_package=pkg)
    url = f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0"

    expected_name = Path(rel_disk_path).name
    head_res = client.head(url)
    assert head_res.status_code == 200
    assert head_res.headers["content-type"] == "application/pdf"
    assert head_res.headers["content-disposition"] == f'inline; filename="{expected_name}"'
    assert head_res.headers["etag"] == f'"{sha}"'

    get_res = client.get(url)
    assert get_res.status_code == 200
    assert get_res.content == PDF_BYTES
    assert client.get(url, headers={"If-None-Match": f'"{sha}"'}).status_code == 304


def test_falls_through_from_uploads_to_review_package_when_blob_absent(
    tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=0, sha256=sha)
    uploads = _upload_settings(tmp_path, CORPUS_FIXTURE)
    pkg = _write_review_package(tmp_path / "package")

    client = _app_client(
        runs, demo_issuer, corpus=CORPUS_FIXTURE, uploads=uploads, review_package=pkg
    )
    res = client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0")
    assert res.status_code == 200
    assert res.content == PDF_BYTES


def test_draft_document_returns_404_for_sha_mismatch_missing_or_wrong_doc(
    tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    other_bytes = b"%PDF-1.4\n%tampered\n"
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=0, sha256=sha)
    uploads = _upload_settings(tmp_path, CORPUS_FIXTURE)
    # Tampered blob stored under expected sha256
    save_blob(uploads.blobs, sha, other_bytes)

    client = _app_client(runs, demo_issuer, corpus=CORPUS_FIXTURE, uploads=uploads)
    assert client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0").status_code == 404
    assert client.head(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0").status_code == 404
    # Wrong revision or wrong doc_id
    assert client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/1").status_code == 404
    assert client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-OTHER/0").status_code == 404

    # Missing file on disk in review_package
    pkg_missing = _write_review_package(tmp_path / "pkg_missing")
    (pkg_missing / "OQ-TP201_rev0.pdf").unlink()
    c_missing = _app_client(runs, demo_issuer, corpus=CORPUS_FIXTURE, review_package=pkg_missing)
    assert c_missing.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0").status_code == 404

    # Tampered file on disk in review_package
    pkg_tampered = _write_review_package(tmp_path / "pkg_tampered")
    (pkg_tampered / "OQ-TP201_rev0.pdf").write_bytes(other_bytes)
    c_tampered = _app_client(runs, demo_issuer, corpus=CORPUS_FIXTURE, review_package=pkg_tampered)
    assert c_tampered.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0").status_code == 404

    # Run without review_package metadata
    runs_no_pkg = tmp_path / "runs_no_pkg"
    _write_package_run(runs_no_pkg, BASE_RUN_ID, sha256=sha, include_package=False)
    c_no_pkg = _app_client(runs_no_pkg, demo_issuer, corpus=CORPUS_FIXTURE, uploads=uploads)
    assert c_no_pkg.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0").status_code == 404


@pytest.mark.parametrize(
    "evil_path",
    [
        "../secret.pdf",
        "TP-201-OQ-draft/../../secret.pdf",
        "../../secret.pdf",
    ],
)
def test_review_package_rejects_path_traversal_in_manifest(
    tmp_path: Path, demo_issuer: DemoIssuer, evil_path: str
) -> None:
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(PDF_BYTES)
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=0, sha256=sha)
    pkg = _write_review_package(
        tmp_path / "pkg",
        manifest_path=evil_path,
        manifest_sha256=sha,
    )
    client = _app_client(runs, demo_issuer, corpus=CORPUS_FIXTURE, review_package=pkg)
    assert client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0").status_code == 404


def test_review_package_rejects_absolute_path_in_manifest(
    tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(PDF_BYTES)
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=0, sha256=sha)
    pkg = _write_review_package(
        tmp_path / "pkg",
        manifest_path=str(outside),
        manifest_sha256=sha,
    )
    client = _app_client(runs, demo_issuer, corpus=CORPUS_FIXTURE, review_package=pkg)
    assert client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0").status_code == 404


def test_extra_document_sanitizes_filename_in_content_disposition(
    tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=0, sha256=sha)

    def evil_name(_run_id: str, _doc_id: str, _rev: int, _sha: str) -> tuple[bytes, str]:
        return PDF_BYTES, '../evil"\r\n;name.pdf'

    app = FastAPI()
    verifier = Verifier(IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience))
    app.include_router(
        create_router(runs, None, extra_document=evil_name),
        dependencies=[Depends(authenticate(verifier))],
    )
    client = TestClient(app, headers={"Authorization": f"Bearer {_token(demo_issuer)}"})
    res = client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0")
    assert res.status_code == 200
    assert res.headers["content-disposition"] == 'inline; filename="OQ-TP201_rev0.pdf"'


def test_cli_serve_passes_review_package_to_create_app(
    tmp_path: Path, demo_issuer: DemoIssuer, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    runs = tmp_path / "runs"
    _write_package_run(runs, BASE_RUN_ID, doc_id="OQ-TP201", rev=0, sha256=sha)
    pkg = _write_review_package(tmp_path / "package")

    captured: dict[str, Any] = {}

    def fake_uvicorn_run(app: Any, **_kwargs: Any) -> None:
        captured["app"] = app

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)
    rc = cli.main(
        [
            "serve",
            "--runs",
            str(runs),
            "--corpus",
            str(CORPUS_FIXTURE),
            "--issuer",
            demo_issuer.url,
            "--audience",
            demo_issuer.audience,
            "--database",
            DUMMY_DB,
            "--review-package",
            str(pkg),
        ]
    )
    assert rc == 0
    client = TestClient(captured["app"], headers={"Authorization": f"Bearer {_token(demo_issuer)}"})
    res = client.get(f"/runs/{BASE_RUN_ID}/documents/OQ-TP201/0")
    assert res.status_code == 200
    assert res.content == PDF_BYTES
