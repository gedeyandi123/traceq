"""Starting and reading an Execution of an Approved Protocol, over HTTP with a real Postgres
and the demo issuer (ADR 0013, spec #270, #271).

Each test copies the fixture run of ``tests/test_protocol_submission_api.py``: three requirements
(``002`` proposed ``partial`` with two FAT steps, ``026`` ``site_only``, ``030`` with no class),
drafts for ``002`` and ``030``, and completeness.json.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import (
    OTHER_RUN,
    RUN_ID,
    bearer,
    configured,
    import_run,
    token,
)
from test_protocol_approval_api import persona_token
from test_protocol_submission_api import make_ready, submit
from test_test_step_proposals import add_drafted_run

from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.identity import EXECUTING_ROLE


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    add_drafted_run(path)
    (path / RUN_ID / "completeness.json").write_text(json.dumps(COMPLETENESS), encoding="utf-8")
    return path


@pytest.fixture
def client(runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases) -> TestClient:
    return TestClient(configured(runs, demo_issuer, fresh_database))


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Ayu: holds both qualification-decider and qualification-executor."""
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def bima(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Bima: holds both qualification-decider and qualification-executor."""
    return persona_token(demo_issuer, "bima")


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Citra: holds no roles."""
    return bearer(token(demo_issuer, decider=False))


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Dewi: holds only qualification-approver."""
    return persona_token(demo_issuer, "dewi")


@pytest.fixture
def draft_protocol(client: TestClient, decider: dict[str, str]) -> Any:
    import_run(client, decider)
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def submitted_protocol(client: TestClient, decider: dict[str, str], draft_protocol: Any) -> Any:
    make_ready(client, decider, draft_protocol)
    return submit(client, decider, draft_protocol)


@pytest.fixture
def approved_protocol(client: TestClient, approver: dict[str, str], submitted_protocol: Any) -> Any:
    sub = submitted_protocol["submission"]
    r = client.post(
        f"/protocols/{submitted_protocol['id']}/approve",
        headers=approver,
        json={"submission_event_id": sub["event_id"], "hash": sub["hash"]},
    )
    assert r.status_code == 200, r.text
    return r.json()


def execution_url(protocol_id: int) -> str:
    return f"/protocols/{protocol_id}/execution"


# --- Auth & Roles ---------------------------------------------------------------------


def test_demo_issuer_gives_executing_role_to_ayu_and_bima_only(demo_issuer: DemoIssuer) -> None:
    import httpx

    personas = {
        p["username"]: p["roles"] for p in httpx.get(f"{demo_issuer.url}/demo/personas").json()
    }
    assert EXECUTING_ROLE in personas["ayu"]
    assert EXECUTING_ROLE in personas["bima"]
    assert EXECUTING_ROLE not in personas["citra"]
    assert EXECUTING_ROLE not in personas["dewi"]


def test_starting_and_reading_require_token_and_proper_roles(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    approved_protocol: Any,
) -> None:
    pid = approved_protocol["id"]
    # 401 without token
    assert client.post(execution_url(pid)).status_code == 401
    assert client.get(f"/runs/{RUN_ID}/execution").status_code == 401

    # 403 for citra (reader) and dewi (approver) on start
    assert client.post(execution_url(pid), headers=reader).status_code == 403
    assert client.post(execution_url(pid), headers=approver).status_code == 403

    # 404 before any Execution exists
    assert client.get(f"/runs/{RUN_ID}/execution", headers=reader).status_code == 404

    # Start succeeds for executor (ayu)
    started = client.post(execution_url(pid), headers=decider)
    assert started.status_code == 201, started.text

    # 200 on read for any signed-in role (citra, dewi, ayu)
    assert client.get(f"/runs/{RUN_ID}/execution", headers=reader).status_code == 200
    assert client.get(f"/runs/{RUN_ID}/execution", headers=approver).status_code == 200
    assert client.get(f"/runs/{RUN_ID}/execution", headers=decider).status_code == 200


# --- Start & Read ---------------------------------------------------------------------


def test_start_execution_of_approved_protocol_and_read_frozen_rows(
    client: TestClient,
    bima: dict[str, str],
    approved_protocol: Any,
    fresh_database: Databases,
) -> None:
    pid = approved_protocol["id"]
    sub = approved_protocol["submission"]

    r = client.post(execution_url(pid), headers=bima)
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["protocol_id"] == pid
    assert body["equipment"] == approved_protocol["equipment"]
    assert body["run_id"] == RUN_ID
    assert body["submission_event_id"] == sub["event_id"]
    assert body["submission_hash"] == sub["hash"]
    assert body["status"] == "in_progress"
    assert len(body["events"]) == 1
    assert body["events"][0]["event"] == "started"
    assert body["events"][0]["status"] == "in_progress"
    assert body["events"][0]["name"] == "Bima Arya Nugraha"

    # Rows match the frozen copy in order
    frozen_rows = sub["frozen_copy"]["rows"]
    assert [row["requirement"] for row in body["rows"]] == [fr["requirement"] for fr in frozen_rows]
    for row, fr in zip(body["rows"], frozen_rows, strict=True):
        assert row["kind"] == fr["kind"]
        assert row["text"] == fr["text"]
        assert row["source"] == fr["source"]
        if fr["kind"] == "vendor_reference":
            assert row["evidence"] == fr["evidence"]
            assert row["test_step"] is None
        else:
            assert row["test_step"] is not None
            assert row["test_step"]["description"] == fr["test_step"]["description"]
            assert row["test_step"]["method"] == fr["test_step"]["method"]
            assert row["test_step"]["instrument"] == fr["test_step"]["instrument"]
            assert row["test_step"]["acceptance"] == fr["test_step"]["acceptance"]

    # GET returns identical view
    got = client.get(f"/runs/{RUN_ID}/execution", headers=bima)
    assert got.status_code == 200
    assert got.json() == body

    # Audit Trail entry recorded in the same transaction
    with transaction(engine(fresh_database.app)) as s:
        log = [
            e for e in entries(s) if e.record_type == "execution" and e.record_id == str(body["id"])
        ]
    assert len(log) == 1
    assert log[0].action == "execution started"
    assert isinstance(log[0].new_value, dict)
    assert log[0].new_value["submission_event_id"] == sub["event_id"]
    assert log[0].new_value["submission_hash"] == sub["hash"]


def test_unknown_run_or_protocol_returns_404(client: TestClient, decider: dict[str, str]) -> None:
    assert client.post(execution_url(999999), headers=decider).status_code == 404
    assert client.get(f"/runs/{OTHER_RUN}/execution", headers=decider).status_code == 404


# --- Refusals (409) -------------------------------------------------------------------


def test_refused_for_draft_protocol(
    client: TestClient, decider: dict[str, str], draft_protocol: Any
) -> None:
    r = client.post(execution_url(draft_protocol["id"]), headers=decider)
    assert r.status_code == 409
    assert "draft" in r.json()["detail"].lower()


def test_refused_for_submitted_protocol(
    client: TestClient, decider: dict[str, str], submitted_protocol: Any
) -> None:
    r = client.post(execution_url(submitted_protocol["id"]), headers=decider)
    assert r.status_code == 409
    assert "submitted" in r.json()["detail"].lower()


def test_refused_for_returned_to_draft_protocol(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    submitted_protocol: Any,
) -> None:
    pid = submitted_protocol["id"]
    ret = client.post(
        f"/protocols/{pid}/return", headers=approver, json={"reason": "Perlu perbaikan langkah uji"}
    )
    assert ret.status_code == 200
    assert ret.json()["status"] == "draft"

    r = client.post(execution_url(pid), headers=decider)
    assert r.status_code == 409
    assert "draft" in r.json()["detail"].lower()


def test_refused_for_withdrawn_protocol(
    client: TestClient, decider: dict[str, str], draft_protocol: Any
) -> None:
    pid = draft_protocol["id"]
    w = client.post(
        f"/protocols/{pid}/withdraw", headers=decider, json={"reason": "Run baru tersedia"}
    )
    assert w.status_code == 200
    assert w.json()["status"] == "withdrawn"

    r = client.post(execution_url(pid), headers=decider)
    assert r.status_code == 409
    assert "withdrawn" in r.json()["detail"].lower()


def test_refuses_second_execution_even_concurrently(
    client: TestClient,
    decider: dict[str, str],
    bima: dict[str, str],
    approved_protocol: Any,
) -> None:
    pid = approved_protocol["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(client.post, execution_url(pid), headers=decider)
        f2 = pool.submit(client.post, execution_url(pid), headers=bima)
        statuses = sorted([f1.result().status_code, f2.result().status_code])

    assert statuses == [201, 409]

    # Sequential second attempt also refused 409
    again = client.post(execution_url(pid), headers=decider)
    assert again.status_code == 409
    assert "one execution per protocol" in again.json()["detail"].lower()


# --- Append-only DB enforcement -------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "update_col"),
    [("protocol_executions", "submission_hash"), ("execution_events", "event")],
)
def test_execution_tables_refuse_update_delete_and_truncate(
    client: TestClient,
    decider: dict[str, str],
    approved_protocol: Any,
    fresh_database: Databases,
    table: str,
    update_col: str,
) -> None:
    r = client.post(execution_url(approved_protocol["id"]), headers=decider)
    assert r.status_code == 201

    # App role cannot UPDATE, DELETE, or TRUNCATE
    for stmt in (
        f"UPDATE {table} SET {update_col} = {update_col}",
        f"DELETE FROM {table}",
        f"TRUNCATE {table}",
    ):
        with (
            pytest.raises((DBAPIError, ProgrammingError)),
            transaction(engine(fresh_database.app)) as s,
        ):
            s.execute(text(stmt))

    # Even owner role is refused by triggers
    for stmt in (
        f"UPDATE {table} SET {update_col} = {update_col}",
        f"DELETE FROM {table}",
        f"TRUNCATE {table} CASCADE",
    ):
        with (
            pytest.raises(DBAPIError, match="append-only"),
            transaction(engine(fresh_database.owner)) as s,
        ):
            s.execute(text(stmt))
