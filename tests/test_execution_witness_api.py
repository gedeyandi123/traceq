"""Witness confirmation bound to attempt version hashes (ADR 0013, spec #270, #274),
over HTTP with a real Postgres and the demo issuer.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_execution_results_api import _start_execution
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, token
from test_protocol_approval_api import persona_token
from test_protocol_submission_api import R002
from test_test_step_proposals import add_drafted_run

from traceq.audit import DEMO_SIGNATURE_LABEL, entries
from traceq.db import engine, transaction
from traceq.execution.results import ATTEMPT_VERSIONS, database_utc_date
from traceq.identity import EXECUTING_ROLE, WITNESSING_ROLE


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
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=False))


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    return persona_token(demo_issuer, "dewi")


@pytest.fixture
def witness(demo_issuer: DemoIssuer) -> dict[str, str]:
    return persona_token(demo_issuer, "eko")


def _custom_token(
    demo_issuer: DemoIssuer,
    *,
    subject: str,
    name: str,
    roles: list[str],
) -> dict[str, str]:
    kid = httpx.get(f"{demo_issuer.url}/jwks").json()["keys"][0]["kid"]
    now = datetime.now(UTC)
    signed = jwt.encode(
        {
            "iss": demo_issuer.url,
            "sub": subject,
            "aud": demo_issuer.audience,
            "iat": now,
            "auth_time": int(now.timestamp()),
            "jti": uuid.uuid4().hex,
            "exp": now + timedelta(minutes=5),
            "name": name,
            "roles": roles,
        },
        demo_issuer.key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    return bearer(signed)


def _setup_attempt(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> tuple[int, dict[str, Any]]:
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]
    with transaction(engine(fresh_database.app)) as s:
        today = database_utc_date(s)
    r = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts",
        headers=decider,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 40},
            "instruments": [
                {
                    "identifier": "TACH-07",
                    "calibration_due_date": (today + timedelta(days=30)).isoformat(),
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    row = next(row for row in r.json()["rows"] if row["requirement"] == R002)
    return ex_id, row["attempts"][0]["latest"]


@pytest.mark.db
def test_eko_confirms_latest_version_and_records_audit_trail(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex_id, latest = _setup_attempt(client, decider, approver, fresh_database)

    r = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert r.status_code == 201, r.text
    row = next(row for row in r.json()["rows"] if row["requirement"] == R002)
    confirmations = row["attempts"][0]["latest"]["witness_confirmations"]
    assert len(confirmations) == 1
    conf = confirmations[0]
    assert conf["subject"] == "demo-0005"
    assert conf["name"] == "Eko Prasetyo Wijaya"
    assert conf["version_hash"] == latest["version_hash"]
    assert conf["voided"] is False
    assert conf["note"] == DEMO_SIGNATURE_LABEL
    assert conf["electronic_signature"]["verified"] is True

    got = client.get(f"/runs/{RUN_ID}/execution", headers=witness)
    assert got.status_code == 200
    got_row = next(row for row in got.json()["rows"] if row["requirement"] == R002)
    assert len(got_row["attempts"][0]["latest"]["witness_confirmations"]) == 1

    with transaction(engine(fresh_database.app)) as s:
        audit_rows = [e for e in entries(s) if e.action == "witness confirmed"]
    assert len(audit_rows) == 1
    assert audit_rows[0].record_id == f"{ex_id}/{R002}/1/v1"
    assert audit_rows[0].actor.subject == "demo-0005"


@pytest.mark.db
def test_non_witness_roles_receive_403(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    reader: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex_id, latest = _setup_attempt(client, decider, approver, fresh_database)
    payload = {"version_number": latest["version"], "version_hash": latest["version_hash"]}

    for actor_headers in (decider, approver, reader):
        r = client.post(
            f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
            headers=actor_headers,
            json=payload,
        )
        assert r.status_code == 403


@pytest.mark.db
def test_performer_holding_both_executor_and_witness_roles_is_refused(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    dual = _custom_token(
        demo_issuer,
        subject="dual-0001",
        name="Dual Role Person",
        roles=[EXECUTING_ROLE, WITNESSING_ROLE],
    )
    ex = _start_execution(client, decider, approver)
    ex_id = ex["id"]
    with transaction(engine(fresh_database.app)) as s:
        today = database_utc_date(s)
    r = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts",
        headers=dual,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 40},
            "instruments": [
                {
                    "identifier": "TACH-07",
                    "calibration_due_date": (today + timedelta(days=30)).isoformat(),
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    latest = next(row for row in r.json()["rows"] if row["requirement"] == R002)["attempts"][0][
        "latest"
    ]

    refused = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=dual,
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert refused.status_code == 409
    assert "Performer" in refused.json()["detail"]


@pytest.mark.db
def test_stale_version_wrong_hash_duplicate_and_second_witness(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex_id, latest = _setup_attempt(client, decider, approver, fresh_database)

    stale = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": 99, "version_hash": latest["version_hash"]},
    )
    assert stale.status_code == 409

    wrong_hash = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": latest["version"], "version_hash": "0" * 64},
    )
    assert wrong_hash.status_code == 409

    ok1 = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert ok1.status_code == 201

    dup = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert dup.status_code == 409

    second_witness = _custom_token(
        demo_issuer,
        subject="demo-9999",
        name="Saksi Kedua",
        roles=[WITNESSING_ROLE],
    )
    ok2 = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=second_witness,
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert ok2.status_code == 201
    row = next(row for row in ok2.json()["rows"] if row["requirement"] == R002)
    assert len(row["attempts"][0]["latest"]["witness_confirmations"]) == 2


@pytest.mark.db
def test_confirmation_is_marked_voided_when_later_version_exists(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex_id, latest = _setup_attempt(client, decider, approver, fresh_database)
    ok = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert ok.status_code == 201
    attempt_id = next(row for row in ok.json()["rows"] if row["requirement"] == R002)["attempts"][
        0
    ]["id"]

    # Insert a later version (v2) directly to verify voided computation before #277 lands.
    with transaction(engine(fresh_database.app)) as s:
        s.execute(
            insert(ATTEMPT_VERSIONS).values(
                attempt_id=attempt_id,
                version=2,
                outcome_kind="value",
                not_performable_reason=None,
                value={"type": "number", "value": 42},
                observation=None,
                instruments=[],
                no_calibrated_instrument_reason=None,
                evidence=[],
                verdict="pass",
                version_hash="b" * 64,
                reason_for_change="koreksi",
                subject="demo-0001",
                issuer="http://127.0.0.1:9000",
                name="Ayu Kartika Sari",
            )
        )

    got = client.get(f"/runs/{RUN_ID}/execution", headers=witness)
    assert got.status_code == 200
    versions = next(row for row in got.json()["rows"] if row["requirement"] == R002)["attempts"][0][
        "versions"
    ]
    assert len(versions) == 2
    assert versions[0]["witness_confirmations"][0]["voided"] is True
    assert versions[1]["witness_confirmations"] == []


@pytest.mark.db
def test_witness_table_is_append_only(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex_id, latest = _setup_attempt(client, decider, approver, fresh_database)
    r = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=witness,
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert r.status_code == 201

    for stmt in (
        "UPDATE execution_witness_confirmations SET witness_name = 'x'",
        "DELETE FROM execution_witness_confirmations",
        "TRUNCATE execution_witness_confirmations",
    ):
        with (
            pytest.raises((DBAPIError, ProgrammingError)),
            transaction(engine(fresh_database.app)) as s,
        ):
            s.execute(text(stmt))
