"""Deviation lifecycle: manual Deviations, Investigation versions, submit, close (4-way SoD),
and return to Open, over HTTP with a real Postgres and the demo issuer (ADR 0013, spec #270, #273).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, token
from test_protocol_approval_api import persona_token
from test_protocol_submission_api import R026
from test_test_step_proposals import add_drafted_run

from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.execution.deviations import CLOSURE_NOTE
from traceq.execution.results import database_utc_date
from traceq.identity import APPROVING_ROLE, EXECUTING_ROLE


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
def executor_b(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Second executor, distinct from Ayu."""
    return _mint_roles(demo_issuer, "exec-002", "Budi Santoso", [EXECUTING_ROLE])


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Citra: holds no roles."""
    return bearer(token(demo_issuer, decider=False))


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Dewi: holds only qualification-approver."""
    return persona_token(demo_issuer, "dewi")


def _mint_roles(issuer: DemoIssuer, subject: str, name: str, roles: list[str]) -> dict[str, str]:
    kid = httpx.get(f"{issuer.url}/jwks").json()["keys"][0]["kid"]
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": issuer.url,
        "sub": subject,
        "aud": issuer.audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "name": name,
        "roles": roles,
    }
    return bearer(jwt.encode(claims, issuer.key, algorithm="RS256", headers={"kid": kid}))


def _exec_and_approve(issuer: DemoIssuer, subject: str, name: str) -> dict[str, str]:
    return _mint_roles(issuer, subject, name, [EXECUTING_ROLE, APPROVING_ROLE])


def _start_execution(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    *,
    with_vendor_ref: bool = False,
) -> Any:
    from test_execution_results_api import _start_execution as start_exec

    return start_exec(client, decider, approver, with_vendor_ref=with_vendor_ref)


def _db_today(fresh_database: Databases) -> Any:
    with transaction(engine(fresh_database.app)) as s:
        return database_utc_date(s)


def _record_failed_attempt(
    client: TestClient,
    executor: dict[str, str],
    eid: int,
    fresh_database: Databases,
    requirement: str = R026,
) -> Any:
    today = _db_today(fresh_database)
    r = client.post(
        f"/executions/{eid}/rows/{requirement}/attempts",
        headers=executor,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 999},
            "instruments": [{"identifier": "TACH-07", "calibration_due_date": today.isoformat()}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- Manual Deviations ----------------------------------------------------------------


def test_open_manual_deviation_auth_validation_and_sequence(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, approver, with_vendor_ref=True)
    eid = ex["id"]
    url = f"/executions/{eid}/deviations"

    # 401 without token; 403 for reader & approver
    assert client.post(url, json={"description": "Sensor drifted"}).status_code == 401
    assert (
        client.post(url, headers=reader, json={"description": "Sensor drifted"}).status_code == 403
    )
    assert (
        client.post(url, headers=approver, json={"description": "Sensor drifted"}).status_code
        == 403
    )

    # 422 blank description
    assert client.post(url, headers=decider, json={"description": "   "}).status_code == 422

    # 404 unknown execution or unknown requirement
    assert (
        client.post(
            "/executions/999999/deviations", headers=decider, json={"description": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            url, headers=decider, json={"requirement": "URS-TP201-999", "description": "x"}
        ).status_code
        == 404
    )

    # 409 on Vendor Reference row
    vendor_row = next(r for r in ex["rows"] if r["kind"] == "vendor_reference")
    assert (
        client.post(
            url,
            headers=decider,
            json={"requirement": vendor_row["requirement"], "description": "Cannot link vendor"},
        ).status_code
        == 409
    )

    # Automatic deviation #1 from a failed attempt
    _record_failed_attempt(client, decider, eid, fresh_database, R026)

    # Manual deviation #2 linked to a Test Step row
    r2 = client.post(
        url,
        headers=decider,
        json={"requirement": R026, "description": "Power flicker mid-step"},
    )
    assert r2.status_code == 201, r2.text

    # Manual deviation #3 linked to Execution only (requirement=None)
    r3 = client.post(
        url,
        headers=decider,
        json={"description": "Room HVAC alarm during execution"},
    )
    assert r3.status_code == 201, r3.text
    devs = r3.json()["deviations"]
    assert [d["deviation_number"] for d in devs] == [1, 2, 3]
    assert [d["cause"] for d in devs] == ["failed", "manual", "manual"]
    assert devs[1]["requirement"] == R026
    assert devs[1]["status"] == "open"
    assert devs[1]["subject"] == "demo-0001"
    assert devs[1]["name"] == "Ayu Kartika Sari"
    assert devs[2]["requirement"] is None
    assert devs[2]["events"][0]["event"] == "opened"

    with transaction(engine(fresh_database.app)) as s:
        opened_audit = [e for e in entries(s) if e.action == "deviation opened"]
        assert len(opened_audit) == 3


# --- Investigation Versions & Submit --------------------------------------------------


def test_investigation_versions_and_submit_guards(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, approver)
    eid = ex["id"]
    opened = client.post(
        f"/executions/{eid}/deviations",
        headers=decider,
        json={"description": "Door interlock delayed"},
    ).json()
    dev_id = opened["deviations"][0]["id"]
    inv_url = f"/executions/{eid}/deviations/{dev_id}/investigations"
    sub_url = f"/executions/{eid}/deviations/{dev_id}/submit"

    # Submit without Investigation -> 409
    assert client.post(sub_url, headers=decider).status_code == 409

    # Auth guards
    inv1 = {
        "investigation": "Loose limit switch bracket; no product impact.",
        "deviation_class": "minor",
        "capa": "Tighten bracket and re-verify.",
    }
    assert client.post(inv_url, json=inv1).status_code == 401
    assert client.post(inv_url, headers=reader, json=inv1).status_code == 403
    assert client.post(inv_url, headers=approver, json=inv1).status_code == 403
    assert client.post(sub_url, headers=reader).status_code == 403
    assert client.post(sub_url, headers=approver).status_code == 403

    # v1 succeeds without reason_for_change
    r1 = client.post(inv_url, headers=decider, json=inv1)
    assert r1.status_code == 201, r1.text
    d1 = r1.json()["deviations"][0]
    assert d1["deviation_class"] == "minor"
    assert len(d1["investigations"]) == 1
    assert d1["investigations"][0]["version"] == 1
    assert d1["investigations"][0]["capa"] == "Tighten bracket and re-verify."

    # v2 without reason_for_change -> 422
    inv2_no_reason = {
        "investigation": "Root cause updated after inspection.",
        "deviation_class": "major",
    }
    assert client.post(inv_url, headers=decider, json=inv2_no_reason).status_code == 422
    assert (
        client.post(
            inv_url, headers=decider, json={**inv2_no_reason, "reason_for_change": "   "}
        ).status_code
        == 422
    )

    # v2 with reason_for_change succeeds
    r2 = client.post(
        inv_url,
        headers=decider,
        json={**inv2_no_reason, "reason_for_change": "Expanded impact assessment"},
    )
    assert r2.status_code == 201, r2.text
    d2 = r2.json()["deviations"][0]
    assert d2["deviation_class"] == "major"
    assert [v["version"] for v in d2["investigations"]] == [1, 2]
    assert d2["investigations"][1]["reason_for_change"] == "Expanded impact assessment"

    # Submit succeeds
    sub = client.post(sub_url, headers=decider)
    assert sub.status_code == 200, sub.text
    assert sub.json()["deviations"][0]["status"] == "submitted"

    # Writes on Submitted Deviation are refused (409)
    assert (
        client.post(
            inv_url,
            headers=decider,
            json={**inv2_no_reason, "reason_for_change": "Late edit"},
        ).status_code
        == 409
    )
    assert client.post(sub_url, headers=decider).status_code == 409

    with transaction(engine(fresh_database.app)) as s:
        actions = [e.action for e in entries(s)]
        assert actions.count("deviation investigation recorded") == 2
        assert actions.count("deviation submitted") == 1


# --- Return to Open & Close -----------------------------------------------------------


def test_return_to_open_and_close_lifecycle(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, approver)
    eid = ex["id"]
    dev_id = client.post(
        f"/executions/{eid}/deviations",
        headers=decider,
        json={"description": "Label printer jam"},
    ).json()["deviations"][0]["id"]

    inv_url = f"/executions/{eid}/deviations/{dev_id}/investigations"
    sub_url = f"/executions/{eid}/deviations/{dev_id}/submit"
    ret_url = f"/executions/{eid}/deviations/{dev_id}/return"
    close_url = f"/executions/{eid}/deviations/{dev_id}/close"

    # Close / Return when Open -> 409 (and 403 for non-approver)
    assert client.post(close_url, headers=decider).status_code == 403
    assert client.post(close_url, headers=reader).status_code == 403
    assert client.post(ret_url, headers=decider, json={"reason": "x"}).status_code == 403
    assert client.post(ret_url, headers=reader, json={"reason": "x"}).status_code == 403
    assert client.post(close_url, headers=approver).status_code == 409
    assert client.post(ret_url, headers=approver, json={"reason": "x"}).status_code == 409

    # Write v1 & submit
    client.post(
        inv_url,
        headers=decider,
        json={"investigation": "Paper roll misaligned", "deviation_class": "minor"},
    )
    client.post(sub_url, headers=decider)

    # Return without reason -> 422
    assert client.post(ret_url, headers=approver, json={"reason": "  "}).status_code == 422

    # Return with reason -> Open
    ret = client.post(
        ret_url, headers=approver, json={"reason": "Please state batch impact explicitly"}
    )
    assert ret.status_code == 200, ret.text
    d_ret = ret.json()["deviations"][0]
    assert d_ret["status"] == "open"
    assert d_ret["events"][-1]["event"] == "returned"
    assert d_ret["events"][-1]["reason"] == "Please state batch impact explicitly"

    # Executor revises (v2) and re-submits
    client.post(
        inv_url,
        headers=decider,
        json={
            "investigation": "Paper roll misaligned; zero product/batch impact.",
            "deviation_class": "minor",
            "reason_for_change": "Clarified batch impact per QA",
        },
    )
    client.post(sub_url, headers=decider)

    # Approver closes
    closed = client.post(close_url, headers=approver)
    assert closed.status_code == 200, closed.text
    d_closed = closed.json()["deviations"][0]
    assert d_closed["status"] == "closed"
    assert d_closed["closure_note"] == CLOSURE_NOTE

    # Writes on Closed Deviation refused (409)
    assert (
        client.post(
            inv_url,
            headers=decider,
            json={
                "investigation": "x",
                "deviation_class": "minor",
                "reason_for_change": "y",
            },
        ).status_code
        == 409
    )
    assert client.post(sub_url, headers=decider).status_code == 409
    assert client.post(close_url, headers=approver).status_code == 409
    assert client.post(ret_url, headers=approver, json={"reason": "late"}).status_code == 409

    with transaction(engine(fresh_database.app)) as s:
        actions = [e.action for e in entries(s)]
        assert "deviation returned" in actions
        closed_entries = [e for e in entries(s) if e.action == "deviation closed"]
        assert len(closed_entries) == 1
        assert isinstance(closed_entries[0].new_value, dict)
        assert closed_entries[0].new_value["note"] == CLOSURE_NOTE


# --- 4-Way Separation of Duties -------------------------------------------------------


def test_close_four_way_separation_of_duties(
    client: TestClient,
    decider: dict[str, str],
    executor_b: dict[str, str],
    approver: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    dual = _exec_and_approve(demo_issuer, "dual-001", "Eka Dual")
    ex = _start_execution(client, decider, approver)
    eid = ex["id"]

    # Case 1: Dual user is Performer of an attempt on R026 -> automatic Deviation #1
    _record_failed_attempt(client, dual, eid, fresh_database, R026)
    dev_step_auto = client.get(f"/runs/{RUN_ID}/execution", headers=decider).json()["deviations"][
        0
    ]["id"]
    # Another executor (decider) writes Investigation & submits
    client.post(
        f"/executions/{eid}/deviations/{dev_step_auto}/investigations",
        headers=decider,
        json={"investigation": "Speed sensor fault", "deviation_class": "major"},
    )
    client.post(f"/executions/{eid}/deviations/{dev_step_auto}/submit", headers=decider)
    # Dual user cannot close because they performed an attempt on R026
    r_sod_performer = client.post(
        f"/executions/{eid}/deviations/{dev_step_auto}/close", headers=dual
    )
    assert r_sod_performer.status_code == 409

    # Case 2: Dual user opens a manual Deviation (Execution-only) -> #2
    dev_manual_opener = client.post(
        f"/executions/{eid}/deviations",
        headers=dual,
        json={"description": "Utility air pressure dip"},
    ).json()["deviations"][1]["id"]
    client.post(
        f"/executions/{eid}/deviations/{dev_manual_opener}/investigations",
        headers=decider,
        json={"investigation": "Compressor cycled", "deviation_class": "minor"},
    )
    client.post(f"/executions/{eid}/deviations/{dev_manual_opener}/submit", headers=decider)
    # Dual user cannot close because they opened this manual Deviation
    r_sod_opener = client.post(
        f"/executions/{eid}/deviations/{dev_manual_opener}/close", headers=dual
    )
    assert r_sod_opener.status_code == 409

    # Case 3: Dual user authors an Investigation version on an Execution-only manual Deviation -> #3
    dev_inv_author = client.post(
        f"/executions/{eid}/deviations",
        headers=decider,
        json={"description": "Printer ribbon low"},
    ).json()["deviations"][2]["id"]
    client.post(
        f"/executions/{eid}/deviations/{dev_inv_author}/investigations",
        headers=dual,
        json={"investigation": "Replaced ribbon", "deviation_class": "minor"},
    )
    client.post(
        f"/executions/{eid}/deviations/{dev_inv_author}/investigations",
        headers=executor_b,
        json={
            "investigation": "Confirmed print quality",
            "deviation_class": "minor",
            "reason_for_change": "Second check",
        },
    )
    client.post(f"/executions/{eid}/deviations/{dev_inv_author}/submit", headers=executor_b)
    # Dual user cannot close because they authored v1 of the Investigation
    r_sod_author = client.post(f"/executions/{eid}/deviations/{dev_inv_author}/close", headers=dual)
    assert r_sod_author.status_code == 409

    # Case 4: Execution-only Deviation opened & investigated by others CAN be closed by Dual user
    # even though Dual user performed an attempt on R026!
    dev_exec_only = client.post(
        f"/executions/{eid}/deviations",
        headers=decider,
        json={"description": "Ambient humidity spike"},
    ).json()["deviations"][3]["id"]
    client.post(
        f"/executions/{eid}/deviations/{dev_exec_only}/investigations",
        headers=executor_b,
        json={"investigation": "Dehumidifier restored", "deviation_class": "minor"},
    )
    client.post(f"/executions/{eid}/deviations/{dev_exec_only}/submit", headers=executor_b)
    r_allowed = client.post(f"/executions/{eid}/deviations/{dev_exec_only}/close", headers=dual)
    assert r_allowed.status_code == 200, r_allowed.text


# --- Append-only DB Triggers ----------------------------------------------------------


def test_investigation_table_is_append_only(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    ex = _start_execution(client, decider, approver)
    eid = ex["id"]
    dev_id = client.post(
        f"/executions/{eid}/deviations",
        headers=decider,
        json={"description": "Trigger test"},
    ).json()["deviations"][0]["id"]
    client.post(
        f"/executions/{eid}/deviations/{dev_id}/investigations",
        headers=decider,
        json={"investigation": "Initial root cause", "deviation_class": "minor"},
    )

    with transaction(engine(fresh_database.owner)) as s, pytest.raises(DBAPIError):
        s.execute(
            text("UPDATE execution_deviation_investigations SET deviation_class = 'critical'")
        )
    with transaction(engine(fresh_database.owner)) as s, pytest.raises(DBAPIError):
        s.execute(text("DELETE FROM execution_deviation_investigations"))
    with transaction(engine(fresh_database.owner)) as s, pytest.raises(DBAPIError):
        s.execute(text("TRUNCATE execution_deviation_investigations"))
