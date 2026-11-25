"""API tests for review rounds, round-over-round diff, closing, and PDF export (Step 6, #319)."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from test_proposals_api import OTHER_RUN, RUN_ID, add_run, bearer, configured, import_run, token
from test_protocol_approval_api import persona_token


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    add_run(path, RUN_ID)
    return path


@pytest.fixture
def client(runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases) -> TestClient:
    return TestClient(configured(runs, demo_issuer, fresh_database))


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    return persona_token(demo_issuer, "dewi")


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=False))


def test_import_opens_round_and_records_corpus_and_draft_documents(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def with_review_pkg(meta: dict[str, Any], _m: dict[str, Any], _f: dict[str, Any]) -> None:
        meta["review_package"] = {
            "package": "RP-1",
            "version": "1",
            "doc_id": "DRAFT-TP201",
            "rev": 2,
            "document": {
                "doc_id": "DRAFT-TP201",
                "rev": 2,
                "sha256": "f" * 64,
            },
        }

    add_run(runs, OTHER_RUN, edit=with_review_pkg)
    import_run(client, decider, OTHER_RUN)

    r = client.get(f"/runs/{OTHER_RUN}/rounds", headers=decider)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["equipment"] == "TP-201"
    assert len(body["rounds"]) == 1
    rnd = body["rounds"][0]
    assert rnd["round_number"] == 1
    assert rnd["status"] == "open"
    assert rnd["previous_round_id"] is None
    sources = {d["doc_id"]: d["source"] for d in rnd["documents"]}
    assert sources["URS-TP201"] == "corpus"
    assert sources["DRAFT-TP201"] == "review_package_draft"
    assert body["diff"] is None


def test_two_rounds_never_auto_close_round_1_and_compute_diff(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider, RUN_ID)

    def revise_urs(meta: dict[str, Any], _m: dict[str, Any], _f: dict[str, Any]) -> None:
        for d in meta["corpus"]["documents"]:
            if d["doc_id"] == "URS-TP201":
                d["rev"] = 1
                d["sha256"] = "e" * 64

    add_run(runs, OTHER_RUN, edit=revise_urs)
    import_run(client, decider, OTHER_RUN)

    r = client.get(f"/runs/{OTHER_RUN}/rounds", headers=decider)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["rounds"]) == 2
    r1, r2 = body["rounds"]
    assert r1["round_number"] == 1
    assert r1["status"] == "open"  # never auto-closed
    assert r2["round_number"] == 2
    assert r2["previous_round_id"] == r1["id"]
    assert body["diff"] is not None
    assert body["diff"]["previous_round_number"] == 1
    assert body["diff"]["documents_revised"] == ["URS-TP201"]


def test_close_round_rbac_validation_and_concurrency(
    client: TestClient, decider: dict[str, str], approver: dict[str, str]
) -> None:
    import_run(client, decider, RUN_ID)
    round_id = client.get(f"/runs/{RUN_ID}/rounds", headers=decider).json()["current_round_id"]

    # 401 without token, 403 for non-decider
    assert (
        client.post(f"/rounds/{round_id}/close", json={"outcome": "ready_for_protocol"}).status_code
        == 401
    )
    assert (
        client.post(
            f"/rounds/{round_id}/close",
            headers=approver,
            json={"outcome": "ready_for_protocol"},
        ).status_code
        == 403
    )

    # 422 when returned_for_revision lacks non-blank reason
    assert (
        client.post(
            f"/rounds/{round_id}/close",
            headers=decider,
            json={"outcome": "returned_for_revision", "reason": "   "},
        ).status_code
        == 422
    )

    # Concurrent close: exactly one 200 and one 409
    def _close() -> int:
        resp = client.post(
            f"/rounds/{round_id}/close",
            headers=decider,
            json={"outcome": "returned_for_revision", "reason": "Missing SAT document."},
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(lambda _: _close(), range(2)))
    assert codes == [200, 409]


def test_export_pre_review_pdf_rbac_and_byte_identical_download(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    reader: dict[str, str],
) -> None:
    import_run(client, decider, RUN_ID)
    round_id = client.get(f"/runs/{RUN_ID}/rounds", headers=decider).json()["current_round_id"]

    # 401 without token, 403 for reader (neither decider nor approver)
    assert client.post(f"/rounds/{round_id}/exports").status_code == 401
    assert client.post(f"/rounds/{round_id}/exports", headers=reader).status_code == 403

    # Decider and Approver can both export
    exp_decider = client.post(f"/rounds/{round_id}/exports", headers=decider)
    assert exp_decider.status_code == 201, exp_decider.text
    exp_approver = client.post(f"/rounds/{round_id}/exports", headers=approver)
    assert exp_approver.status_code == 201, exp_approver.text

    exp_data = exp_decider.json()
    export_id = exp_data["id"]

    # Any authenticated user (including reader) can download the PDF
    pdf_resp = client.get(f"/rounds/{round_id}/exports/{export_id}/pdf", headers=reader)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-")
    assert hashlib.sha256(pdf_resp.content).hexdigest() == exp_data["pdf_sha256"]


def test_rounds_are_non_blocking_toward_protocol_assembly(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    # Even with an open round, starting a protocol works (non-blocking toward Step 5a/5b).
    import_run(client, decider, RUN_ID)
    proto = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert proto.status_code == 201, proto.text
