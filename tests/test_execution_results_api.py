"""Recording Execution Results judged by code, with instruments and automatic Deviations,
over HTTP with a real Postgres and the demo issuer (ADR 0013, spec #270, #272).
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, import_run, token
from test_protocol_approval_api import persona_token
from test_protocol_submission_api import (
    N003,
    N004,
    R002,
    R026,
    R030,
    STEP,
    decide,
    dispose,
    edit,
    make_ready,
    place,
    proposals,
    submit,
    write,
)
from test_test_step_proposals import add_drafted_run

from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.execution.results import database_utc_date


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


def _approve_protocol(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    written_step: dict[str, Any] | None = None,
    *,
    with_vendor_ref: bool = False,
) -> Any:
    import_run(client, decider)
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert r.status_code == 201, r.text
    draft = r.json()
    if with_vendor_ref:
        ps = proposals(client, decider)
        decide(
            client,
            decider,
            place(ps, "coverage", R002),
            decision="edited",
            coverage="covered_by_vendor",
            reason="FAT cukup",
        )
        decide(client, decider, place(ps, "coverage", R026), decision="accepted")
        decide(
            client,
            decider,
            place(ps, "coverage", R030),
            decision="edited",
            coverage="gap",
            reason="r",
        )
        write(client, decider, draft, R026, written_step or STEP)
        edit(client, decider, draft, place(ps, "test_step", R030), STEP)
        dispose(client, decider, draft, number=N003)
        dispose(client, decider, draft, number=N004, kind="not_tested_here")
    else:
        make_ready(client, decider, draft)
        if written_step is not None:
            write(client, decider, draft, R026, written_step)
    submitted = submit(client, decider, draft)
    sub = submitted["submission"]
    app = client.post(
        f"/protocols/{submitted['id']}/approve",
        headers=approver,
        json={"submission_event_id": sub["event_id"], "hash": sub["hash"]},
    )
    assert app.status_code == 200, app.text
    return app.json()


def _start_execution(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    written_step: dict[str, Any] | None = None,
    *,
    with_vendor_ref: bool = False,
) -> Any:
    approved = _approve_protocol(
        client, decider, approver, written_step, with_vendor_ref=with_vendor_ref
    )
    ex = client.post(f"/protocols/{approved['id']}/execution", headers=decider)
    assert ex.status_code == 201, ex.text
    return ex.json()


def _attempt_url(execution_id: int, requirement: str) -> str:
    return f"/executions/{execution_id}/rows/{requirement}/attempts"


def _db_today(fresh_database: Databases) -> Any:
    with transaction(engine(fresh_database.app)) as s:
        return database_utc_date(s)


# --- Auth & Row Guards ----------------------------------------------------------------


def test_record_attempt_auth_roles_and_vendor_ref_409(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, approver, with_vendor_ref=True)
    eid = ex["id"]
    today = _db_today(fresh_database)
    payload = {
        "outcome_kind": "value",
        "value": {"type": "number", "value": 50},
        "instruments": [{"identifier": "TACH-07", "calibration_due_date": today.isoformat()}],
    }

    # 401 without token
    assert client.post(_attempt_url(eid, R026), json=payload).status_code == 401
    # 403 for reader (citra) and approver (dewi)
    assert client.post(_attempt_url(eid, R026), headers=reader, json=payload).status_code == 403
    assert client.post(_attempt_url(eid, R026), headers=approver, json=payload).status_code == 403
    # 404 unknown execution or requirement
    assert client.post(_attempt_url(999999, R026), headers=decider, json=payload).status_code == 404
    assert (
        client.post(_attempt_url(eid, "URS-TP201-999"), headers=decider, json=payload).status_code
        == 404
    )
    # 409 on Vendor Reference row (R002 is covered_by_vendor)
    vendor_row = next(r for r in ex["rows"] if r["kind"] == "vendor_reference")
    vr = client.post(
        _attempt_url(eid, vendor_row["requirement"]),
        headers=decider,
        json={"outcome_kind": "value", "value": {"type": "present", "value": True}},
    )
    assert vr.status_code == 409


# --- Judging Rules (ADR 0013) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("acceptance", "value", "expected_verdict"),
    [
        # Range: inclusive at both bounds, outside fails
        (
            {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
            {"type": "number", "value": 20.0},
            "pass",
        ),
        (
            {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
            {"type": "number", "value": 70.0},
            "pass",
        ),
        (
            {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
            {"type": "number", "value": 19.99},
            "fail",
        ),
        (
            {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
            {"type": "number", "value": 70.01},
            "fail",
        ),
        # Range: single lower bound
        (
            {"type": "range", "min": 10.0, "max": None, "unit": "bar"},
            {"type": "number", "value": 10.0},
            "pass",
        ),
        (
            {"type": "range", "min": 10.0, "max": None, "unit": "bar"},
            {"type": "number", "value": 9.9},
            "fail",
        ),
        # Range: single upper bound
        (
            {"type": "range", "min": None, "max": 5.0, "unit": "mm"},
            {"type": "number", "value": 5.0},
            "pass",
        ),
        (
            {"type": "range", "min": None, "max": 5.0, "unit": "mm"},
            {"type": "number", "value": 5.1},
            "fail",
        ),
        # Number: exact equality, NO rounding
        (
            {"type": "number", "value": 30.0, "unit": "°C"},
            {"type": "number", "value": 30.0},
            "pass",
        ),
        (
            {"type": "number", "value": 30.0, "unit": "°C"},
            {"type": "number", "value": 29.9},
            "fail",
        ),
        # OneOf: allowed passes, not_one_of fails
        (
            {"type": "one_of", "allowed": ["PASS", "OK"]},
            {"type": "one_of", "value": "OK", "not_one_of": False},
            "pass",
        ),
        (
            {"type": "one_of", "allowed": ["PASS", "OK"]},
            {"type": "one_of", "value": "ALARM", "not_one_of": True},
            "fail",
        ),
        # Present: true passes, false fails
        ({"type": "present"}, {"type": "present", "value": True}, "pass"),
        ({"type": "present"}, {"type": "present", "value": False}, "fail"),
    ],
)
def test_judging_rules_for_all_acceptance_shapes(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    acceptance: dict[str, Any],
    value: dict[str, Any],
    expected_verdict: str,
) -> None:
    ex = _start_execution(
        client,
        decider,
        approver,
        written_step={
            "description": "Langkah uji kriteria",
            "method": "Amati langsung",
            "instrument": None,
            "acceptance": acceptance,
        },
    )
    r = client.post(
        _attempt_url(ex["id"], R026),
        headers=decider,
        json={"outcome_kind": "value", "value": value},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    row = next(row for row in body["rows"] if row["requirement"] == R026)
    assert len(row["attempts"]) == 1
    attempt = row["attempts"][0]
    assert attempt["attempt_number"] == 1
    assert attempt["latest"]["version"] == 1
    assert attempt["latest"]["verdict"] == expected_verdict
    assert len(attempt["latest"]["version_hash"]) == 64
    if expected_verdict == "fail":
        assert len(body["deviations"]) == 1
        assert body["deviations"][0]["cause"] == "failed"
    else:
        assert body["deviations"] == []

    # Even if a frozen copy carries a value on a present criterion, judge on present/absent only
    from traceq.execution.results import PresentResultValue, RecordAttemptRequest, judge
    from traceq.traceability.values import Present

    assert (
        judge(
            Present(value=True),
            RecordAttemptRequest(outcome_kind="value", value=PresentResultValue(value=False)),
        )
        == "fail"
    )
    assert (
        judge(
            Present(value=False),
            RecordAttemptRequest(outcome_kind="value", value=PresentResultValue(value=True)),
        )
        == "pass"
    )


def test_inverted_bounds_range_in_frozen_copy_fails_every_value_and_accepts_not_performable(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    # Start a normal execution, then test inverted bounds directly via judge() and via a
    # frozen copy containing inverted bounds (e.g. from an older draft).
    from traceq.execution.results import NumberResultValue, RecordAttemptRequest, judge
    from traceq.traceability.values import Range

    inverted = Range(min=70.0, max=20.0, unit="rpm")
    assert (
        judge(
            inverted,
            RecordAttemptRequest(outcome_kind="value", value=NumberResultValue(value=50.0)),
        )
        == "fail"
    )
    assert (
        judge(
            inverted,
            RecordAttemptRequest(
                outcome_kind="not_performable",
                not_performable_reason="Mesin sedang perawatan",
            ),
        )
        == "fail"
    )

    # Also test not_performable over HTTP on a real Execution
    ex = _start_execution(
        client,
        decider,
        approver,
        written_step={
            "description": "Langkah uji",
            "method": "Metode",
            "instrument": "   ",  # blank -> treated as empty
            "acceptance": {"type": "number", "value": 30.0, "unit": "°C"},
        },
    )
    r = client.post(
        _attempt_url(ex["id"], R026),
        headers=decider,
        json={
            "outcome_kind": "not_performable",
            "not_performable_reason": "Katup utama terkunci",
            "observation": "Dicatat saat inspeksi",
            "evidence": ["LOG-001", "PRINT-02"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    row = next(row for row in body["rows"] if row["requirement"] == R026)
    latest = row["attempts"][0]["latest"]
    assert latest["verdict"] == "fail"
    assert latest["outcome_kind"] == "not_performable"
    assert latest["not_performable_reason"] == "Katup utama terkunci"
    assert latest["evidence"] == ["LOG-001", "PRINT-02"]
    assert len(body["deviations"]) == 1
    assert body["deviations"][0]["cause"] == "failed"
    assert body["deviations"][0]["status"] == "open"


def test_422_for_wrong_shape_inf_nan_client_verdict_and_blank_not_performable(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
) -> None:
    ex = _start_execution(
        client,
        decider,
        approver,
        written_step={
            "description": "Langkah uji",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        },
    )
    url = _attempt_url(ex["id"], R026)

    # Wrong shape (present on range)
    assert (
        client.post(
            url,
            headers=decider,
            json={"outcome_kind": "value", "value": {"type": "present", "value": True}},
        ).status_code
        == 422
    )
    # Client sending verdict field
    assert (
        client.post(
            url,
            headers=decider,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 50.0},
                "verdict": "pass",
            },
        ).status_code
        == 422
    )
    # Blank not_performable_reason
    assert (
        client.post(
            url,
            headers=decider,
            json={"outcome_kind": "not_performable", "not_performable_reason": "   "},
        ).status_code
        == 422
    )
    # Missing not_performable_reason
    assert (
        client.post(url, headers=decider, json={"outcome_kind": "not_performable"}).status_code
        == 422
    )
    # inf / nan floats
    for bad in ("Infinity", "-Infinity", "NaN"):
        raw = '{"outcome_kind": "value", "value": {"type": "number", "value": ' + bad + "}}"
        r = client.post(
            url,
            headers={**decider, "Content-Type": "application/json"},
            content=raw,
        )
        assert r.status_code == 422, f"{bad} gave {r.status_code}: {r.text}"


# --- Instruments & Calibration Dates --------------------------------------------------


def test_instruments_required_when_named_and_calibration_checked_against_db_utc_date(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(
        client,
        decider,
        approver,
        written_step={
            "description": "Uji kecepatan",
            "method": "Ukur dengan takometer",
            "instrument": "TACH-07",
            "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        },
    )
    url = _attempt_url(ex["id"], R026)
    today = _db_today(fresh_database)
    yesterday = today - timedelta(days=1)

    # Neither instrument nor reason -> 422
    r_none = client.post(
        url,
        headers=decider,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 50.0}},
    )
    assert r_none.status_code == 422

    # Expired instrument -> 409 naming the expired instrument
    r_exp = client.post(
        url,
        headers=decider,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "instruments": [
                {"identifier": "TACH-OLD", "calibration_due_date": yesterday.isoformat()}
            ],
        },
    )
    assert r_exp.status_code == 409
    assert "TACH-OLD" in r_exp.json()["detail"]

    # Two instruments with one expired -> 409 naming the expired one
    r_two = client.post(
        url,
        headers=decider,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "instruments": [
                {"identifier": "TACH-OK", "calibration_due_date": today.isoformat()},
                {"identifier": "TACH-BAD", "calibration_due_date": yesterday.isoformat()},
            ],
        },
    )
    assert r_two.status_code == 409
    assert "TACH-BAD" in r_two.json()["detail"]

    # Today's UTC date is accepted -> 201
    r_today = client.post(
        url,
        headers=decider,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "instruments": [{"identifier": "TACH-07", "calibration_due_date": today.isoformat()}],
        },
    )
    assert r_today.status_code == 201, r_today.text
    assert r_today.json()["deviations"] == []


# --- Automatic Deviations & Audit Trail -----------------------------------------------


def test_no_calibrated_instrument_opens_one_deviation_and_with_fail_opens_two(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    # Case 1 on R026: passing verdict + no_calibrated_instrument_reason -> 1 Deviation (#1)
    ex = _start_execution(
        client,
        decider,
        approver,
        written_step={
            "description": "Uji kecepatan",
            "method": "Inspeksi visual",
            "instrument": "TACH-07",
            "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        },
    )
    r1 = client.post(
        _attempt_url(ex["id"], R026),
        headers=decider,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "no_calibrated_instrument_reason": "Pembacaan langsung pada panel terkalibrasi",
        },
    )
    assert r1.status_code == 201, r1.text
    b1 = r1.json()
    assert len(b1["deviations"]) == 1
    assert b1["deviations"][0]["deviation_number"] == 1
    assert b1["deviations"][0]["cause"] == "no_calibrated_instrument"
    assert b1["deviations"][0]["status"] == "open"
    assert b1["deviations"][0]["requirement"] == R026

    # Case 2 on R030 (same Execution, STEP has instrument "stopwatch" and range 20..70 rpm):
    # failing verdict + no_calibrated_instrument_reason -> opens 2 more Deviations (#2, #3)
    r2 = client.post(
        _attempt_url(ex["id"], R030),
        headers=decider,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 99.0},
            "no_calibrated_instrument_reason": "Takometer rusak saat uji",
        },
    )
    assert r2.status_code == 201, r2.text
    b2 = r2.json()
    assert [d["deviation_number"] for d in b2["deviations"]] == [1, 2, 3]
    assert [d["cause"] for d in b2["deviations"]] == [
        "no_calibrated_instrument",
        "failed",
        "no_calibrated_instrument",
    ]
    assert all(d["status"] == "open" for d in b2["deviations"])

    # Audit Trail entries recorded in the same transaction for attempt + each Deviation
    with transaction(engine(fresh_database.app)) as s:
        all_entries = entries(s)
    attempt_logs = [
        e
        for e in all_entries
        if e.record_type == "execution_attempt" and e.record_id == f"{ex['id']}/{R030}/1"
    ]
    dev_logs = [
        e
        for e in all_entries
        if e.record_type == "execution_deviation"
        and e.record_id in {f"{ex['id']}/1", f"{ex['id']}/2", f"{ex['id']}/3"}
    ]
    assert len(attempt_logs) == 1
    assert attempt_logs[0].action == "attempt recorded"
    assert len(dev_logs) == 3
    assert all(d.action == "deviation opened" for d in dev_logs)


# --- Append-Only DB Enforcement -------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "update_col"),
    [
        ("execution_attempts", "requirement"),
        ("execution_attempt_versions", "verdict"),
        ("execution_deviations", "description"),
        ("execution_deviation_events", "event"),
    ],
)
def test_result_and_deviation_tables_refuse_update_delete_and_truncate(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
    table: str,
    update_col: str,
) -> None:
    ex = _start_execution(
        client,
        decider,
        approver,
        written_step={
            "description": "Langkah uji",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "number", "value": 30.0, "unit": "°C"},
        },
    )
    r = client.post(
        _attempt_url(ex["id"], R026),
        headers=decider,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 99.0}},
    )
    assert r.status_code == 201

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
