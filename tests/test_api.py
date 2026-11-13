"""The read-only API over run folders (spec #29): contract tests over a fixture run folder.

``tests/fixtures/run/runs`` holds one run folder, with a scorer report beside its run
files; ``tests/fixtures/run/corpus`` is the corpus it read. ``web/openapi.json`` is the
schema the TypeScript client is generated from: it must match the app.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traceq.runs.api import create_app, openapi_schema
from traceq.runs.schemas import Matrix

ROOT = Path(__file__).parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "run"
RUNS = FIXTURE / "runs"
CORPUS = FIXTURE / "corpus"
RUN_ID = "20261113T090000Z-f1a2b3"
OPENAPI = ROOT / "web" / "openapi.json"
NEVER = "SCORER-REPORT-NEVER-SERVED"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(RUNS, CORPUS))


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
        }
    ]
    assert client.get(f"/runs/{RUN_ID}").json() == r.json()[0]


def test_serves_the_matrix_as_written(client: TestClient) -> None:
    r = client.get(f"/runs/{RUN_ID}/matrix")
    assert r.status_code == 200
    written = json.loads((RUNS / RUN_ID / "matrix.json").read_text(encoding="utf-8"))
    assert r.json() == written
    row = r.json()["requirements"][0]
    assert (row["coverage"], row["reason"].split(":")[0]) == ("partial", "FAT-M-02")
    ambiguous = row["evidence"][1]["observed_value"]
    assert ambiguous == {"type": "ambiguous", "readings": [1500.0, 1.5]}


def test_opens_the_cited_document_as_released(client: TestClient) -> None:
    r = client.get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content == (CORPUS / "FAT-TP201-M_rev0.pdf").read_bytes()


def test_a_document_the_run_did_not_read_is_not_served(client: TestClient, tmp_path: Path) -> None:
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
    other = TestClient(create_app(RUNS, corpus))
    assert other.get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0").status_code == 404
    # Without a corpus no document is served.
    assert (
        TestClient(create_app(RUNS)).get(f"/runs/{RUN_ID}/documents/FAT-TP201-M/0").status_code
        == 404
    )


@pytest.mark.parametrize(
    "path",
    [
        "/runs/nope",
        "/runs/nope/matrix",
        "/runs/..%2F..%2Ffixtures/matrix",
        f"/runs/{RUN_ID}/report.json",
        f"/runs/{RUN_ID}/report",
        f"/runs/{RUN_ID}/submission.json",
    ],
)
def test_unknown_paths_are_not_found(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_no_route_writes(client: TestClient) -> None:
    methods = {m for item in openapi_schema()["paths"].values() for m in item if m != "parameters"}
    assert methods == {"get"}
    assert client.post("/runs", json={}).status_code == 405


def test_never_exposes_scorer_output_answer_key_or_baselines(client: TestClient) -> None:
    """Every route, over a run folder with a scorer report beside it: nothing of the report,
    and no route names scores, answer key or baselines."""
    paths = set(openapi_schema()["paths"])
    assert paths == {
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/matrix",
        "/runs/{run_id}/documents/{doc_id}/{rev}",
    }
    schema = json.dumps(openapi_schema()).lower()
    assert all(w not in schema for w in ("score", "answer", "baseline", "gate", "report"))
    for path in ["/runs", f"/runs/{RUN_ID}", f"/runs/{RUN_ID}/matrix"]:
        assert NEVER not in client.get(path).text
    for d in ("URS-TP201", "FAT-TP201-M", "DS-TP201"):
        assert NEVER.encode() not in client.get(f"/runs/{RUN_ID}/documents/{d}/0").content


def test_the_fixture_matrix_is_a_matrix() -> None:
    text = (RUNS / RUN_ID / "matrix.json").read_text(encoding="utf-8")
    assert Matrix.model_validate_json(text).model_dump(mode="json") == json.loads(text)


def test_the_committed_openapi_schema_is_current() -> None:
    """``web/openapi.json`` feeds the generated TypeScript client; regenerate both with
    ``npm run generate`` in ``web/``."""
    assert json.loads(OPENAPI.read_text(encoding="utf-8")) == openapi_schema()
