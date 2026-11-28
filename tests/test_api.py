"""The read-only API over run folders (spec #29): contract tests over a fixture run folder.

``tests/fixtures/run/runs`` holds one run folder, with a scorer report beside its run
files; ``tests/fixtures/run/corpus`` is the corpus it read. ``web/openapi.json`` is the
schema the TypeScript client is generated from: it must match the app.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import DemoIssuer, runs_client
from fastapi import FastAPI
from fastapi.testclient import TestClient

from traceq.app.api import create_app, openapi_schema
from traceq.runs.api import create_router
from traceq.runs.schemas import Findings, Matrix

ROOT = Path(__file__).parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "run"
RUNS = FIXTURE / "runs"
CORPUS = FIXTURE / "corpus"
RUN_ID = "20261113T090000Z-f1a2b3"
OPENAPI = ROOT / "web" / "openapi.json"
NEVER = "SCORER-REPORT-NEVER-SERVED"


def run_folder_schema() -> dict[str, Any]:
    """The read-only run-folder API alone; the composed application adds the database routes
    (``tests/test_proposals_api.py``)."""
    app = FastAPI()
    app.include_router(create_router(RUNS, CORPUS))
    return app.openapi()


@pytest.fixture
def client(demo_issuer: DemoIssuer) -> TestClient:
    return runs_client(RUNS, CORPUS, demo_issuer)


def test_every_run_route_needs_a_bearer_token(demo_issuer: DemoIssuer) -> None:
    anonymous = runs_client(RUNS, CORPUS, demo_issuer, signed_in=False)
    for path in (
        "/runs",
        f"/runs/{RUN_ID}",
        f"/runs/{RUN_ID}/matrix",
        f"/runs/{RUN_ID}/findings",
        f"/runs/{RUN_ID}/dropped",
        f"/runs/{RUN_ID}/completeness",
        f"/runs/{RUN_ID}/documents/FAT-TP201-M/0",
    ):
        r = anonymous.get(path)
        assert r.status_code == 401, path
        assert r.headers["www-authenticate"] == "Bearer"
    assert anonymous.head(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert anonymous.get("/runs", headers=bad).status_code == 401


def test_the_composed_application_without_an_issuer_serves_no_run() -> None:
    bare = TestClient(create_app(RUNS, CORPUS))
    assert bare.get("/runs").status_code == 401
    assert bare.get(f"/runs/{RUN_ID}/matrix").status_code == 401


def test_lists_runs_without_scores(client: TestClient) -> None:
    r = client.get("/runs")
    assert r.status_code == 200
    assert r.json() == [
        {
            "run_id": RUN_ID,
            "created": "2026-11-13T09:00:00+00:00",
            "equipment": "TP-201",
            "model": "claude-haiku-5-5",
            "mode": "replay",
            "pipeline_version": "0.2.0",
            "review_package": None,
        }
    ]
    assert client.get(f"/runs/{RUN_ID}").json() == r.json()[0]


def test_a_review_package_run_names_its_package_and_draft(
    tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    """So a run screen can link to the Protocol Draft without a token (spec #196, ticket
    #210): the package, its version and the draft document, from ``run.json``."""
    folder = tmp_path / RUN_ID
    folder.mkdir()
    meta = json.loads((RUNS / RUN_ID / "run.json").read_text(encoding="utf-8"))
    meta["review_package"] = {
        "package": "TP-201-OQ-draft",
        "version": "0.1.0",
        "document": {"doc_id": "OQ-TP201", "rev": 0, "sha256": "ab" * 32},
        "test_steps": 26,
    }
    (folder / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    got = runs_client(tmp_path, None, demo_issuer).get(f"/runs/{RUN_ID}").json()
    assert got["review_package"] == {
        "package": "TP-201-OQ-draft",
        "version": "0.1.0",
        "doc_id": "OQ-TP201",
        "rev": 0,
    }


def test_serves_the_matrix_as_written(client: TestClient) -> None:
    r = client.get(f"/runs/{RUN_ID}/matrix")
    assert r.status_code == 200
    written = json.loads((RUNS / RUN_ID / "matrix.json").read_text(encoding="utf-8"))
    assert r.json() == written
    row = r.json()["requirements"][0]
    assert (row["coverage"], row["reason"].split(":")[0]) == ("partial", "FAT-M-02")
    ambiguous = row["evidence"][1]["observed_value"]
    assert ambiguous == {"type": "ambiguous", "readings": [1500.0, 1.5]}


def test_serves_the_findings_as_written(client: TestClient) -> None:
    r = client.get(f"/runs/{RUN_ID}/findings")
    assert r.status_code == 200
    written = json.loads((RUNS / RUN_ID / "findings.json").read_text(encoding="utf-8"))
    assert r.json() == written
    assert {f["layer"] for f in r.json()["check_findings"]} == {"check"}
    assert [f["reviewer_action"] for f in r.json()["ai_findings"]] == ["pending"]
    assert [d["doc_id"] for d in r.json()["missing_documents"]] == ["IQ-TP201", "OQ-TP201"]


def test_serves_the_dropped_claims_with_their_reasons(client: TestClient) -> None:
    r = client.get(f"/runs/{RUN_ID}/dropped")
    assert r.status_code == 200
    assert r.json() == [
        {"claim": "requirement", "id": "URS-TP201 p2", "reason": "bad answer"},
        {"claim": "value", "id": "URS-TP201-005", "reason": "quote not on page or value not in it"},
    ]
    reason = openapi_schema()["components"]["schemas"]["DroppedClaim"]["properties"]["reason"]
    assert reason["type"] == "string" and "enum" not in reason


def test_serves_the_completeness_check_as_written(client: TestClient) -> None:
    r = client.get(f"/runs/{RUN_ID}/completeness")
    assert r.status_code == 200
    written = json.loads((RUNS / RUN_ID / "completeness.json").read_text(encoding="utf-8"))
    assert r.json() == written
    assert r.json()["urs"][0]["missed"] == [{"number": "URS-TP201-003", "page": 1}]


def test_a_run_written_before_the_completeness_check_has_none(
    tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    folder = tmp_path / RUN_ID
    folder.mkdir()
    for name in ("run.json", "matrix.json", "findings.json"):
        (folder / name).write_bytes((RUNS / RUN_ID / name).read_bytes())
    r = runs_client(tmp_path, None, demo_issuer).get(f"/runs/{RUN_ID}/completeness")
    assert r.status_code == 404
    assert "did not run" in r.json()["detail"]


def test_opens_the_cited_document_as_released(client: TestClient) -> None:
    r = client.get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content == (CORPUS / "FAT-TP201-M_rev0.pdf").read_bytes()


def test_document_headers_and_head_precheck(client: TestClient) -> None:
    expected_bytes = (CORPUS / "FAT-TP201-M_rev0.pdf").read_bytes()
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    get_res = client.get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0")
    assert get_res.status_code == 200
    assert get_res.headers["content-security-policy"] == "frame-ancestors 'self'"
    assert get_res.headers["cache-control"] == "private, max-age=300"
    assert get_res.headers["etag"] == f'"{expected_sha256}"'

    head_res = client.head(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0")
    assert head_res.status_code == 200
    assert head_res.content == b""
    assert head_res.headers["content-type"] == "application/pdf"
    assert head_res.headers["content-length"] == str(len(expected_bytes))
    assert head_res.headers["content-security-policy"] == "frame-ancestors 'self'"
    assert head_res.headers["cache-control"] == "private, max-age=300"
    assert head_res.headers["etag"] == f'"{expected_sha256}"'

    assert client.head(f"/runs/{RUN_ID}/documents/SAT-TP201/0").status_code == 404


@pytest.mark.parametrize("method", ["get", "head"])
def test_document_answers_304_for_a_matching_etag_only(client: TestClient, method: str) -> None:
    url = f"/runs/{RUN_ID}/documents/FAT-TP201-M/0"
    call = getattr(client, method)
    etag = call(url).headers["etag"]
    hit = call(url, headers={"If-None-Match": etag})
    assert hit.status_code == 304
    assert hit.content == b""
    assert hit.headers["etag"] == etag
    assert hit.headers["cache-control"] == "private, max-age=300"
    assert call(url, headers={"If-None-Match": f'W/{etag}, "other"'}).status_code == 304
    assert call(url, headers={"If-None-Match": '"other"'}).status_code == 200
    # An unknown document is never a 304, even with a matching-looking tag.
    missing = f"/runs/{RUN_ID}/documents/SAT-TP201/0"
    assert call(missing, headers={"If-None-Match": etag}).status_code == 404


def test_a_document_the_run_did_not_read_is_not_served(
    client: TestClient, tmp_path: Path, demo_issuer: DemoIssuer
) -> None:
    assert client.get(f"/runs/{RUN_ID}/documents/SAT-TP201/0").status_code == 404
    assert client.get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/1").status_code == 404
    # The served corpus holds other bytes than the run read: not the page it cited.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    for d in manifest["documents"]:
        data = (CORPUS / d["path"]).read_bytes() + b"%changed\n"
        (corpus / d["path"]).write_bytes(data)
        d["sha256"] = hashlib.sha256(data).hexdigest()
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    other = runs_client(RUNS, corpus, demo_issuer)
    assert other.get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0").status_code == 404
    # Without a corpus no document is served.
    no_corpus = runs_client(RUNS, None, demo_issuer)
    assert no_corpus.get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/runs/nope",
        "/runs/nope/matrix",
        "/runs/nope/findings",
        "/runs/nope/dropped",
        "/runs/nope/completeness",
        "/runs/..%2F..%2Ffixtures/matrix",
        f"/runs/{RUN_ID}/report.json",
        f"/runs/{RUN_ID}/report",
        f"/runs/{RUN_ID}/submission.json",
    ],
)
def test_unknown_paths_are_not_found(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_no_run_folder_route_writes(client: TestClient) -> None:
    paths = run_folder_schema()["paths"]
    methods = {m for item in paths.values() for m in item if m != "parameters"}
    assert methods == {"get"}
    assert client.post("/runs", json={}).status_code == 405


def test_never_exposes_scorer_output_answer_key_or_baselines(client: TestClient) -> None:
    """Every route, over a run folder with a scorer report beside it: nothing of the report,
    and no route of the composed application names scores, answer key or baselines."""
    paths = set(run_folder_schema()["paths"])
    assert paths == {
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/matrix",
        "/runs/{run_id}/findings",
        "/runs/{run_id}/dropped",
        "/runs/{run_id}/completeness",
        "/runs/{run_id}/documents/{doc_id}/{rev}",
    }
    schema = json.dumps(openapi_schema()).lower()
    assert all(
        w not in schema
        for w in ("score", "answer", "baseline", "gate", "scorer_report", "report.json")
    )
    for path in [
        "/runs",
        f"/runs/{RUN_ID}",
        f"/runs/{RUN_ID}/matrix",
        f"/runs/{RUN_ID}/findings",
        f"/runs/{RUN_ID}/dropped",
        f"/runs/{RUN_ID}/completeness",
    ]:
        assert NEVER not in client.get(path).text
    for d in ("URS-TP201", "FAT-TP201-M", "DS-TP201"):
        assert NEVER.encode() not in client.get(f"/runs/{RUN_ID}/documents/{d}/0").content


def test_the_fixture_matrix_is_a_matrix() -> None:
    text = (RUNS / RUN_ID / "matrix.json").read_text(encoding="utf-8")
    assert Matrix.model_validate_json(text).model_dump(mode="json") == json.loads(text)


def test_the_fixture_findings_are_findings() -> None:
    text = (RUNS / RUN_ID / "findings.json").read_text(encoding="utf-8")
    assert Findings.model_validate_json(text).model_dump(mode="json") == json.loads(text)


def test_the_committed_openapi_schema_is_current() -> None:
    """``web/openapi.json`` feeds the generated TypeScript client; regenerate with
    ``npm run openapi`` then ``npm run generate`` in ``web/``."""
    assert json.loads(OPENAPI.read_text(encoding="utf-8")) == openapi_schema()
