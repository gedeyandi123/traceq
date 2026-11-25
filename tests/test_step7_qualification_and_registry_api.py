"""Integration tests (real Postgres + FastAPI TestClient) for Step 7 Slice 1:
- Migration 0017 upgrade/downgrade/upgrade & DB constraints
- Protocol v2: PUT /protocols/{id}/rows/{req}/attributes, freeze, approval SoD
- Execution v2: retest_deviation_id/retest_reason persistence, unconfirmed_witness_rows blocker
- Qualification Report: GET, POST (SoD, 422, revisions, audit), PDF download (zero writes)
- Rounds isolation from qualification exports
- Equipment Registry: GET /equipment merging disk runs + DB-only equipment
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_execution_completion_api import _record_pass_for_all_rows
from test_execution_results_api import _start_execution
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, token
from test_protocol_approval_api import persona_token
from test_protocol_submission_api import make_ready
from test_test_step_proposals import add_drafted_run

from traceq.audit import DEMO_SIGNATURE_LABEL, UNSIGNED_STATUS_LABEL, entries
from traceq.db import engine, transaction
from traceq.db.database import HERE as DB_HERE


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
    """Ayu: qualification-decider + qualification-executor."""
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Citra: no write roles."""
    return bearer(token(demo_issuer, decider=False))


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Dewi: qualification-approver."""
    return persona_token(demo_issuer, "dewi")


@pytest.fixture
def witness(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Eko: qualification-witness."""
    return persona_token(demo_issuer, "eko")


def _prepare_draft_protocol(
    client: TestClient, decider: dict[str, str], run_id: str = RUN_ID
) -> dict[str, Any]:
    assert client.post(f"/runs/{run_id}/import", headers=decider).status_code == 200
    proto = client.post(f"/runs/{run_id}/protocol", headers=decider)
    assert proto.status_code == 201
    make_ready(client, decider, proto.json())
    refreshed = client.get(f"/runs/{run_id}/protocol", headers=decider)
    assert refreshed.status_code == 200
    return refreshed.json()


@pytest.mark.db
def test_0017_migration_reversible_and_constraints(fresh_database: Databases) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(DB_HERE / "migrations"))
    cfg.attributes["url"] = fresh_database.owner

    # Downgrade to 0016 and re-upgrade to head (0017) cleanly.
    command.downgrade(cfg, "0016")
    command.upgrade(cfg, "head")

    owner_db = engine(fresh_database.owner)
    with transaction(owner_db) as session:
        # protocol_step_attributes has append-only triggers & traceq_app only gets SELECT, INSERT.
        privs = set(
            session.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'traceq_app' AND table_name = 'protocol_step_attributes'"
                )
            ).scalars()
        )
        assert privs == {"SELECT", "INSERT"}

    # Check report_exports target constraint: qualification needs execution_id.
    with pytest.raises(IntegrityError), transaction(owner_db) as session:
        session.execute(
            text(
                """
                INSERT INTO report_exports (
                    round_id, execution_id, report_kind, subject, issuer, name,
                    snapshot_json, snapshot_hash, pdf_sha256, template_version, typst_version
                ) VALUES (
                    NULL, NULL, 'qualification', 'u', 'i', 'U',
                    '{}'::jsonb, repeat('a', 64), repeat('b', 64), '1.0.0', '0.15.2'
                )
                """
            )
        )


@pytest.mark.db
def test_protocol_v2_step_attributes_and_approval_sod(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    assert client.post(f"/runs/{RUN_ID}/import", headers=decider).status_code == 200
    proto_raw = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert proto_raw.status_code == 201
    proto = proto_raw.json()
    pid = proto["id"]

    # Auth & role checks
    assert (
        client.put(
            f"/protocols/{pid}/rows/R001/attributes",
            json={"stage": "IQ", "witness_required": True},
        ).status_code
        == 401
    )
    assert (
        client.put(
            f"/protocols/{pid}/rows/R001/attributes",
            headers=reader,
            json={"stage": "IQ", "witness_required": True},
        ).status_code
        == 403
    )
    # 404 unknown protocol or requirement
    assert (
        client.put(
            "/protocols/99999/rows/R001/attributes",
            headers=decider,
            json={"stage": "IQ", "witness_required": False},
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/protocols/{pid}/rows/NO-SUCH-REQ/attributes",
            headers=decider,
            json={"stage": "IQ", "witness_required": False},
        ).status_code
        == 404
    )

    # 409 on non-test_step row (undecided before make_ready)
    undecided_row = next(r for r in proto["rows"] if r["kind"] != "test_step")
    assert (
        client.put(
            f"/protocols/{pid}/rows/{undecided_row['requirement']}/attributes",
            headers=decider,
            json={"stage": "IQ", "witness_required": True},
        ).status_code
        == 409
    )

    make_ready(client, decider, proto)
    proto = client.get(f"/runs/{RUN_ID}/protocol", headers=decider).json()
    ts_row = next(r for r in proto["rows"] if r["kind"] == "test_step")
    assert ts_row["stage"] is None
    assert ts_row["witness_required"] is False

    # Set attributes on test_step row
    upd = client.put(
        f"/protocols/{pid}/rows/{ts_row['requirement']}/attributes",
        headers=decider,
        json={"stage": "OQ", "witness_required": True},
    )
    assert upd.status_code == 200
    updated_ts = next(r for r in upd.json()["rows"] if r["requirement"] == ts_row["requirement"])
    assert updated_ts["stage"] == "OQ"
    assert updated_ts["witness_required"] is True
    assert updated_ts["test_step"]["stage"] == "OQ"
    assert updated_ts["test_step"]["witness_required"] is True

    # Submit & verify frozen copy
    sub = client.post(f"/protocols/{pid}/submit", headers=decider)
    assert sub.status_code == 200
    frozen_rows = sub.json()["submission"]["frozen_copy"]["rows"]
    frozen_ts = next(r for r in frozen_rows if r["requirement"] == ts_row["requirement"])
    assert len(frozen_ts["step_attributes"]) == 1
    assert frozen_ts["test_step"]["stage"] == "OQ"
    assert frozen_ts["test_step"]["witness_required"] is True

    # 409 on non-draft protocol
    assert (
        client.put(
            f"/protocols/{pid}/rows/{ts_row['requirement']}/attributes",
            headers=decider,
            json={"stage": "IQ", "witness_required": False},
        ).status_code
        == 409
    )

    # Approval succeeds for Dewi
    app = client.post(
        f"/protocols/{pid}/approve",
        headers=approver,
        json={
            "submission_event_id": sub.json()["submission"]["event_id"],
            "hash": sub.json()["submission"]["hash"],
        },
    )
    assert app.status_code == 200


@pytest.mark.db
def test_execution_v2_witness_blocker_retest_and_qualification_report(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    # Start execution on a fresh run with witness_required=True on R-01
    ex_init = _start_execution(client, decider, approver)
    eid = ex_init["id"]
    pid = ex_init["protocol_id"]

    # 404 on qualification-report before completion
    assert client.get(f"/runs/{RUN_ID}/qualification-report", headers=reader).status_code == 404
    assert (
        client.post(
            f"/executions/{eid}/qualification-reports",
            headers=approver,
            json={"expected_revision_number": 1, "expected_execution_copy_hash": "a" * 64},
        ).status_code
        == 409
    )

    # Complete all rows cleanly
    _record_pass_for_all_rows(client, decider, ex_init)
    comp_resp = client.post(f"/executions/{eid}/complete", headers=decider)
    assert comp_resp.status_code == 200
    completed = comp_resp.json()
    assert completed["status"] == "completed"

    # GET qualification-report succeeds for any signed-in user
    q_resp = client.get(f"/runs/{RUN_ID}/qualification-report", headers=reader)
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["execution_id"] == eid
    assert q_data["protocol_id"] == pid
    assert q_data["execution_copy_hash"] == completed["copy_hash"]
    assert q_data["approval_note"] == UNSIGNED_STATUS_LABEL
    assert q_data["technical_conclusion"] == "qualified"
    assert q_data["latest_export"] is None

    # SoD: performer/completer (decider) cannot approve even if they had approve role;
    # non-approver gets 403
    assert (
        client.post(
            f"/executions/{eid}/qualification-reports",
            headers=decider,
            json={
                "expected_revision_number": 1,
                "expected_execution_copy_hash": completed["copy_hash"],
            },
        ).status_code
        == 403
    )

    # 422 if next_requalification_date is in the past
    past_date = (datetime.now(UTC) - timedelta(days=2)).date().isoformat()
    assert (
        client.post(
            f"/executions/{eid}/qualification-reports",
            headers=approver,
            json={
                "next_requalification_date": past_date,
                "expected_revision_number": 1,
                "expected_execution_copy_hash": completed["copy_hash"],
            },
        ).status_code
        == 422
    )

    # Approve revision 1 with blank conclusion_note -> normalized to None (fresh token)
    future_date = (datetime.now(UTC) + timedelta(days=365)).date().isoformat()
    rev1 = client.post(
        f"/executions/{eid}/qualification-reports",
        headers=persona_token(demo_issuer, "dewi"),
        json={
            "conclusion_note": "   ",
            "next_requalification_date": future_date,
            "expected_revision_number": 1,
            "expected_execution_copy_hash": completed["copy_hash"],
        },
    )
    assert rev1.status_code == 201
    r1 = rev1.json()
    exp1 = r1["latest_export"]
    assert exp1["revision_number"] == 1
    assert exp1["conclusion_note"] is None
    assert exp1["next_requalification_date"] == future_date
    assert exp1["approval_note"] == DEMO_SIGNATURE_LABEL
    assert exp1["electronic_signature"]["verified"] is True

    # Download PDF (zero DB writes, byte-identical on second download)
    pdf1 = client.get(
        f"/executions/{eid}/qualification-reports/{exp1['id']}/pdf",
        headers=reader,
    )
    assert pdf1.status_code == 200
    assert pdf1.headers["content-type"] == "application/pdf"
    assert hashlib.sha256(pdf1.content).hexdigest() == exp1["pdf_sha256"]

    pdf1_again = client.get(
        f"/executions/{eid}/qualification-reports/{exp1['id']}/pdf",
        headers=reader,
    )
    assert pdf1_again.content == pdf1.content

    # Wrong execution_id -> 404
    assert (
        client.get(
            f"/executions/{eid + 999}/qualification-reports/{exp1['id']}/pdf",
            headers=reader,
        ).status_code
        == 404
    )

    # Rounds isolation: qualification export does NOT appear in rounds
    rounds_resp = client.get(f"/runs/{RUN_ID}/rounds", headers=reader)
    assert rounds_resp.status_code == 200
    for rnd in rounds_resp.json()["rounds"]:
        assert all(e["id"] != exp1["id"] for e in rnd["exports"])

    # Append-only revision 2 allowed (fresh token per signature)
    rev2 = client.post(
        f"/executions/{eid}/qualification-reports",
        headers=persona_token(demo_issuer, "dewi"),
        json={
            "conclusion_note": "Updated note",
            "expected_revision_number": 2,
            "expected_execution_copy_hash": completed["copy_hash"],
        },
    )
    assert rev2.status_code == 201
    assert len(rev2.json()["exports"]) == 2
    assert rev2.json()["latest_export"]["revision_number"] == 2
    assert rev2.json()["latest_export"]["conclusion_note"] == "Updated note"

    # Audit trail recorded qualification report approval
    with transaction(engine(fresh_database.app)) as session:
        audit_rows = [
            e
            for e in entries(session)
            if e.record_type == "report_export" and e.record_id == str(exp1["id"])
        ]
        assert len(audit_rows) == 1
        assert audit_rows[0].action == "qualification report approved"
        assert isinstance(audit_rows[0].new_value, dict)
        assert audit_rows[0].new_value["approval_note"] == DEMO_SIGNATURE_LABEL

    # Equipment Registry: GET /equipment merges disk run + DB state + DB-only equipment
    with transaction(engine(fresh_database.owner)) as session:
        session.execute(
            text(
                """
                INSERT INTO imported_runs (
                    run_id, equipment, created, model, mode, pipeline_version,
                    prompts, documents, completeness
                ) VALUES (
                    'db-only-run-1', 'EQ-DB-ONLY', now(), 'm', 'replay', '0.2.0',
                    '{}'::jsonb, '[]'::jsonb, '{"urs": []}'::jsonb
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO review_rounds (equipment, round_number, run_id)
                VALUES ('EQ-DB-ONLY', 1, 'db-only-run-1')
                """
            )
        )

    eq_resp = client.get("/equipment", headers=reader)
    assert eq_resp.status_code == 200
    items = {item["equipment"]: item for item in eq_resp.json()}
    assert "TP-201" in items
    tp = items["TP-201"]
    assert tp["run_count"] == 1
    assert tp["latest_run"]["run_id"] == RUN_ID
    assert tp["latest_round"]["run_id"] == RUN_ID
    assert tp["latest_protocol"]["run_id"] == RUN_ID
    assert tp["latest_execution"]["run_id"] == RUN_ID
    assert tp["latest_execution"]["open_deviations"] == 0
    assert tp["latest_qualification_report"]["run_id"] == RUN_ID
    assert tp["latest_qualification_report"]["revision_number"] == 2

    assert "EQ-DB-ONLY" in items
    db_only = items["EQ-DB-ONLY"]
    assert db_only["run_count"] == 0
    assert db_only["latest_run"] is None
    assert db_only["latest_round"]["run_id"] == "db-only-run-1"


@pytest.mark.db
def test_witness_blocker_and_retest_persistence_on_execution(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
) -> None:
    proto = _prepare_draft_protocol(client, decider)
    pid = proto["id"]
    ts_row = next(r for r in proto["rows"] if r["kind"] == "test_step")
    req_id = ts_row["requirement"]

    # Mark witness_required=True and stage="IQ" on ts_row
    assert (
        client.put(
            f"/protocols/{pid}/rows/{req_id}/attributes",
            headers=decider,
            json={"stage": "IQ", "witness_required": True},
        ).status_code
        == 200
    )
    # Submit & approve
    sub = client.post(f"/protocols/{pid}/submit", headers=decider).json()
    client.post(
        f"/protocols/{pid}/approve",
        headers=approver,
        json={
            "submission_event_id": sub["submission"]["event_id"],
            "hash": sub["submission"]["hash"],
        },
    )

    ex = client.post(f"/protocols/{pid}/execution", headers=decider).json()
    eid = ex["id"]
    # Record failing attempt on req_id so we can test retest persistence too
    target_row = next(r for r in ex["rows"] if r["requirement"] == req_id)
    step = target_row["test_step"]
    assert step["stage"] == "IQ"
    assert step["witness_required"] is True

    acc = step["acceptance"]
    fail_val: dict[str, Any] = (
        {"type": "number", "value": float(acc["max"]) + 100.0}
        if acc["type"] == "range"
        else {"type": "number", "value": float(acc["value"]) + 100.0}
        if acc["type"] == "number"
        else {"type": "one_of", "value": "OUT-OF-SPEC", "not_one_of": True}
        if acc["type"] == "one_of"
        else {"type": "present", "value": False}
    )
    fail_payload: dict[str, Any] = {
        "outcome_kind": "value",
        "value": fail_val,
        "evidence": ["LOG-1"],
    }
    if step["instrument"]:
        fail_payload["instruments"] = [
            {"identifier": step["instrument"], "calibration_due_date": "2099-12-31"}
        ]
    att1 = client.post(
        f"/executions/{eid}/rows/{req_id}/attempts",
        headers=decider,
        json=fail_payload,
    )
    assert att1.status_code == 201
    dev = att1.json()["deviations"][0]

    # Retest with retest_reason
    pass_val: dict[str, Any] = (
        {"type": "number", "value": (float(acc["min"]) + float(acc["max"])) / 2.0}
        if acc["type"] == "range"
        else {"type": "number", "value": float(acc["value"])}
        if acc["type"] == "number"
        else {"type": "one_of", "value": acc["options"][0], "not_one_of": False}
        if acc["type"] == "one_of"
        else {"type": "present", "value": True}
    )
    retest_payload: dict[str, Any] = {
        "outcome_kind": "value",
        "value": pass_val,
        "evidence": ["LOG-2"],
        "deviation_id": dev["id"],
        "retest_reason": "Sensor replaced",
    }
    if step["instrument"]:
        retest_payload["instruments"] = [
            {"identifier": step["instrument"], "calibration_due_date": "2099-12-31"}
        ]
    att2 = client.post(
        f"/executions/{eid}/rows/{req_id}/retests",
        headers=decider,
        json=retest_payload,
    )
    assert att2.status_code == 201
    retest_row_view = next(r for r in att2.json()["rows"] if r["requirement"] == req_id)
    latest_att = retest_row_view["attempts"][-1]
    assert latest_att["retest_deviation_id"] == dev["id"]
    assert latest_att["retest_reason"] == "Sensor replaced"

    # Complete other rows & close deviation, but leave witness unconfirmed -> blocked!
    ex_cur = att2.json()
    for r in ex_cur["rows"]:
        if r["kind"] == "test_step" and not r["attempts"]:
            s = r["test_step"]
            val = (
                {"type": "number", "value": (s["acceptance"]["min"] + s["acceptance"]["max"]) / 2}
                if s["acceptance"]["type"] == "range"
                else {"type": "number", "value": s["acceptance"]["value"]}
                if s["acceptance"]["type"] == "number"
                else {"type": "one_of", "value": s["acceptance"]["options"][0], "not_one_of": False}
                if s["acceptance"]["type"] == "one_of"
                else {"type": "present", "value": True}
            )
            p: dict[str, Any] = {"outcome_kind": "value", "value": val, "evidence": ["LOG-1"]}
            if s["instrument"]:
                p["instruments"] = [
                    {"identifier": s["instrument"], "calibration_due_date": "2099-12-31"}
                ]
            ex_cur = client.post(
                f"/executions/{eid}/rows/{r['requirement']}/attempts", headers=decider, json=p
            ).json()

    # Close deviation
    client.post(
        f"/executions/{eid}/deviations/{dev['id']}/investigations",
        headers=decider,
        json={"investigation": "Replaced sensor", "deviation_class": "minor"},
    )
    sub_dev = client.post(f"/executions/{eid}/deviations/{dev['id']}/submit", headers=decider)
    d_sub = next(item for item in sub_dev.json()["deviations"] if item["id"] == dev["id"])
    close_dev = client.post(
        f"/executions/{eid}/deviations/{dev['id']}/close",
        headers=persona_token(demo_issuer, "dewi"),
        json={
            "expected_event_id": d_sub["events"][-1]["id"],
            "expected_investigation_version": d_sub["investigations"][-1]["version"],
            "expected_content_hash": d_sub["closure_content_hash"],
        },
    )
    assert close_dev.status_code == 200

    # Still blocked by unconfirmed_witness_rows!
    comp_blocked = client.post(f"/executions/{eid}/complete", headers=decider)
    assert comp_blocked.status_code == 409
    assert "unconfirmed_witness_rows" in comp_blocked.json()["detail"]

    # Confirm witness -> completion succeeds
    client.post(
        f"/executions/{eid}/rows/{req_id}/attempts/{latest_att['attempt_number']}/witness",
        headers=witness,
        json={
            "version_number": latest_att["latest"]["version"],
            "version_hash": latest_att["latest"]["version_hash"],
        },
    )
    comp_ok = client.post(f"/executions/{eid}/complete", headers=decider)
    assert comp_ok.status_code == 200
    frozen_att = next(
        r for r in comp_ok.json()["frozen_copy"]["rows"] if r["requirement"] == req_id
    )["attempts"][-1]
    assert frozen_att["retest_deviation_id"] == dev["id"]
    assert frozen_att["retest_reason"] == "Sensor replaced"
