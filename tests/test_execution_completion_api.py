"""Completing an Execution: blocking checklist, frozen copy and its SHA-256 hash (ADR 0013,
spec #270, #275), over HTTP with a real Postgres and the demo issuer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_execution_results_api import _start_execution
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, token
from test_protocol_approval_api import persona_token
from test_protocol_submission_api import R002
from test_test_step_proposals import add_drafted_run

from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.execution.completion import ExecutionCopy, hash_of


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
    """Ayu: holds qualification-decider and qualification-executor."""
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Citra: holds no roles."""
    return bearer(token(demo_issuer, decider=False))


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Dewi: holds only qualification-approver."""
    return persona_token(demo_issuer, "dewi")


@pytest.fixture
def witness(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Eko: holds only qualification-witness."""
    return persona_token(demo_issuer, "eko")


def _pass_value(acceptance: dict[str, Any]) -> dict[str, Any]:
    kind = acceptance["type"]
    if kind == "range":
        return {"type": "number", "value": (acceptance["min"] + acceptance["max"]) / 2}
    if kind == "number":
        return {"type": "number", "value": acceptance["value"]}
    if kind == "one_of":
        return {"type": "one_of", "value": acceptance["options"][0], "not_one_of": False}
    if kind == "present":
        return {"type": "present", "value": True}
    raise AssertionError(f"unexpected acceptance type: {kind!r}")


def _record_pass_for_row(
    client: TestClient, headers: dict[str, str], execution_id: int, row: dict[str, Any]
) -> Any:
    step = row["test_step"]
    payload: dict[str, Any] = {
        "outcome_kind": "value",
        "value": _pass_value(step["acceptance"]),
        "evidence": ["LOG-001"],
    }
    if step["instrument"]:
        payload["instruments"] = [
            {"identifier": step["instrument"], "calibration_due_date": "2099-12-31"}
        ]
    r = client.post(
        f"/executions/{execution_id}/rows/{row['requirement']}/attempts",
        headers=headers,
        json=payload,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _record_pass_for_all_rows(
    client: TestClient,
    headers: dict[str, str],
    ex: dict[str, Any],
    *,
    skip: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    latest = ex
    for row in ex["rows"]:
        if row["kind"] == "test_step" and row["requirement"] not in skip:
            latest = _record_pass_for_row(client, headers, ex["id"], row)
    return latest


def _record_fail_for_002(client: TestClient, headers: dict[str, str], execution_id: int) -> Any:
    r = client.post(
        f"/executions/{execution_id}/rows/{R002}/attempts",
        headers=headers,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 99},
            "instruments": [{"identifier": "TACH-07", "calibration_due_date": "2099-12-31"}],
            "evidence": ["LOG-002"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _close_deviation(
    client: TestClient,
    executor: dict[str, str],
    approver: dict[str, str],
    execution_id: int,
    deviation_id: int,
) -> Any:
    inv = client.post(
        f"/executions/{execution_id}/deviations/{deviation_id}/investigations",
        headers=executor,
        json={
            "investigation": "Turret speed out of range during initial run.",
            "deviation_class": "minor",
            "capa": "Recalibrate drive.",
        },
    )
    assert inv.status_code == 201, inv.text
    sub = client.post(
        f"/executions/{execution_id}/deviations/{deviation_id}/submit",
        headers=executor,
    )
    assert sub.status_code == 200, sub.text
    closed = client.post(
        f"/executions/{execution_id}/deviations/{deviation_id}/close",
        headers=approver,
    )
    assert closed.status_code == 200, closed.text
    return closed.json()


# --- Auth & Roles ---------------------------------------------------------------------


def test_complete_requires_executing_role_for_dewi_citra_and_eko(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    reader: dict[str, str],
    witness: dict[str, str],
) -> None:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]

    assert client.post(f"/executions/{ex_id}/complete").status_code == 401
    for headers in (approver, reader, witness):
        r = client.post(f"/executions/{ex_id}/complete", headers=headers)
        assert r.status_code == 403


# --- Blockers & Completion Rules ------------------------------------------------------


def test_complete_refused_with_rows_without_result_and_vendor_reference_never_blocks(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
) -> None:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]
    test_step_reqs = [r["requirement"] for r in ex["rows"] if r["kind"] == "test_step"]

    # Initially, all test_step rows have no result; vendor_reference rows are not in blockers.
    blockers = ex["completion_blockers"]
    assert blockers["blocked"] is True
    assert blockers["rows_without_result"]["count"] == len(test_step_reqs)
    assert blockers["rows_without_result"]["requirements"] == test_step_reqs
    assert blockers["open_deviations"]["count"] == 0
    assert blockers["open_deviations"]["items"] == []

    r = client.post(f"/executions/{ex_id}/complete", headers=decider)
    assert r.status_code == 409
    assert R002 in r.json()["detail"]


def test_complete_refused_with_open_or_submitted_deviation(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
) -> None:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]
    _record_pass_for_all_rows(client, decider, ex)

    # Open a manual Deviation -> status is open -> blocks completion
    dev_res = client.post(
        f"/executions/{ex_id}/deviations",
        headers=decider,
        json={"requirement": None, "description": "Power flicker during test."},
    )
    assert dev_res.status_code == 201
    body = dev_res.json()
    dev_id = body["deviations"][0]["id"]
    assert body["completion_blockers"]["blocked"] is True
    assert body["completion_blockers"]["rows_without_result"]["count"] == 0
    assert body["completion_blockers"]["open_deviations"] == {
        "count": 1,
        "items": [{"deviation_number": 1, "status": "open"}],
    }

    r_open = client.post(f"/executions/{ex_id}/complete", headers=decider)
    assert r_open.status_code == 409
    assert "#1" in r_open.json()["detail"]

    # Add investigation and submit -> status is submitted -> still blocks completion
    assert (
        client.post(
            f"/executions/{ex_id}/deviations/{dev_id}/investigations",
            headers=decider,
            json={"investigation": "Checked UPS log.", "deviation_class": "minor"},
        ).status_code
        == 201
    )
    sub_res = client.post(
        f"/executions/{ex_id}/deviations/{dev_id}/submit",
        headers=decider,
    )
    assert sub_res.status_code == 200
    assert sub_res.json()["completion_blockers"]["open_deviations"] == {
        "count": 1,
        "items": [{"deviation_number": 1, "status": "submitted"}],
    }

    r_sub = client.post(f"/executions/{ex_id}/complete", headers=decider)
    assert r_sub.status_code == 409
    assert "submitted" in r_sub.json()["detail"]


def test_complete_allowed_with_failed_latest_attempt_once_deviations_closed_and_without_witness(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
) -> None:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]

    # Record a failed attempt on R002 and passing attempts on all other test_step rows (no Witness)
    _record_pass_for_all_rows(client, decider, ex, skip={R002})
    failed = _record_fail_for_002(client, decider, ex_id)
    assert failed["deviations"][0]["status"] == "open"
    dev_id = failed["deviations"][0]["id"]

    # Close the Deviation
    closed = _close_deviation(client, decider, approver, ex_id, dev_id)
    assert closed["completion_blockers"]["blocked"] is False

    # Complete without any Witness confirmation, even though latest attempt failed
    comp = client.post(f"/executions/{ex_id}/complete", headers=decider)
    assert comp.status_code == 200, comp.text
    body = comp.json()
    assert body["status"] == "completed"
    assert body["frozen_copy"] is not None
    assert body["copy_hash"] is not None
    assert len(body["copy_hash"]) == 64


# --- Frozen Copy, Hash Stability, Audit & Immutability -------------------------------


def test_frozen_copy_hash_stable_across_reads_and_includes_witness_and_audit(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]
    after_attempt = _record_pass_for_all_rows(client, decider, ex)
    latest_v = after_attempt["rows"][0]["attempts"][0]["latest"]

    # Witness confirms
    w_res = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": latest_v["version"], "version_hash": latest_v["version_hash"]},
    )
    assert w_res.status_code == 201, w_res.text

    comp = client.post(f"/executions/{ex_id}/complete", headers=decider)
    assert comp.status_code == 200, comp.text
    completed = comp.json()
    copy_hash = completed["copy_hash"]
    frozen = completed["frozen_copy"]

    assert frozen["execution_id"] == ex_id
    assert frozen["protocol_id"] == ex["protocol_id"]
    assert frozen["submission_event_id"] == ex["submission_event_id"]
    assert frozen["submission_hash"] == ex["submission_hash"]
    assert frozen["completer"]["name"] == "Ayu Kartika Sari"
    assert len(frozen["rows"]) == len(ex["rows"])
    assert len(frozen["rows"][0]["attempts"][0]["versions"][0]["witness_confirmations"]) == 1

    # Hash matches canonical JSON recomputation and is stable across subsequent GETs
    assert hash_of(ExecutionCopy.model_validate(frozen)) == copy_hash

    r1 = client.get(f"/runs/{RUN_ID}/execution", headers=decider)
    r2 = client.get(f"/runs/{RUN_ID}/execution", headers=approver)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["copy_hash"] == copy_hash
    assert r2.json()["copy_hash"] == copy_hash
    assert r1.json()["frozen_copy"] == frozen

    # Audit Trail entry recorded in the same transaction
    with transaction(engine(fresh_database.app)) as s:
        actions = [
            e.action
            for e in entries(s)
            if e.record_type == "execution" and e.record_id == str(ex_id)
        ]
    assert "execution completed" in actions


def test_every_write_after_completion_is_refused_with_409(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
) -> None:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]
    _record_pass_for_all_rows(client, decider, ex, skip={R002})
    failed = _record_fail_for_002(client, decider, ex_id)
    dev_id = failed["deviations"][0]["id"]
    latest_v = failed["rows"][0]["attempts"][0]["latest"]
    _close_deviation(client, decider, approver, ex_id, dev_id)

    assert client.post(f"/executions/{ex_id}/complete", headers=decider).status_code == 200

    # Complete again -> 409
    assert client.post(f"/executions/{ex_id}/complete", headers=decider).status_code == 409

    # Record attempt -> 409
    assert (
        client.post(
            f"/executions/{ex_id}/rows/{R002}/attempts",
            headers=decider,
            json={"outcome_kind": "value", "value": {"type": "number", "value": 45}},
        ).status_code
        == 409
    )

    # Confirm witness -> 409
    assert (
        client.post(
            f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
            headers=witness,
            json={"version_number": latest_v["version"], "version_hash": latest_v["version_hash"]},
        ).status_code
        == 409
    )

    # Open manual deviation -> 409
    assert (
        client.post(
            f"/executions/{ex_id}/deviations",
            headers=decider,
            json={"requirement": None, "description": "Late deviation"},
        ).status_code
        == 409
    )

    # Add investigation -> 409
    assert (
        client.post(
            f"/executions/{ex_id}/deviations/{dev_id}/investigations",
            headers=decider,
            json={
                "investigation": "After completion",
                "deviation_class": "minor",
                "reason_for_change": "Late edit",
            },
        ).status_code
        == 409
    )

    # Submit / close / return deviation -> 409
    assert (
        client.post(f"/executions/{ex_id}/deviations/{dev_id}/submit", headers=decider).status_code
        == 409
    )
    assert (
        client.post(f"/executions/{ex_id}/deviations/{dev_id}/close", headers=approver).status_code
        == 409
    )
    assert (
        client.post(
            f"/executions/{ex_id}/deviations/{dev_id}/return",
            headers=approver,
            json={"reason": "Late return"},
        ).status_code
        == 409
    )


def test_execution_completions_table_is_append_only_for_every_role(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]
    _record_pass_for_all_rows(client, decider, ex)
    assert client.post(f"/executions/{ex_id}/complete", headers=decider).status_code == 200

    for url in (fresh_database.app, fresh_database.owner):
        eng = engine(url)
        with pytest.raises((DBAPIError, ProgrammingError)), transaction(eng) as s:
            s.execute(text("UPDATE execution_completions SET copy_hash = repeat('0', 64)"))
        with pytest.raises((DBAPIError, ProgrammingError)), transaction(eng) as s:
            s.execute(text("DELETE FROM execution_completions"))
        with pytest.raises((DBAPIError, ProgrammingError)), transaction(eng) as s:
            s.execute(text("TRUNCATE execution_completions"))
