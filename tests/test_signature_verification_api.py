"""``verified`` on an Electronic Signature view is a real check (audit #341, H3): the signed
``content_hash`` is compared with a hash recomputed from the stored source data, so data altered
after signing reads ``verified: false`` and untouched data reads ``true``. Nothing compared
reads ``null`` ("not checked"), never ``true``.

Over HTTP with a real Postgres and the demo issuer. The alteration is done as the table owner
with the append-only triggers off: what the checks exist to catch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_assembled_protocol_api import read
from test_execution_completion_api import (
    _close_deviation,
    _record_fail_for_002,
    _record_pass_for_all_rows,
)
from test_execution_results_api import _start_execution
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, import_run, token
from test_protocol_approval_api import approve, persona_token, read_by
from test_protocol_submission_api import R002, make_ready, submit
from test_test_step_proposals import add_drafted_run

from traceq.audit import ElectronicSignature, signature_view, verified_against
from traceq.db import engine


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


def tamper(databases: Databases, table: str, statement: str) -> None:
    """Runs ``statement`` as the table owner with ``table``'s append-only triggers off."""
    with engine(databases.owner).begin() as c:
        c.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
        c.execute(text(statement))
        c.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))


def signatures_of_protocol(view: Any) -> dict[str, Any]:
    return {
        e["event"]: e["electronic_signature"]
        for e in view["events"]
        if e["electronic_signature"] is not None
    }


def test_a_signature_checked_against_nothing_is_not_checked_rather_than_verified() -> None:
    sig = ElectronicSignature(
        id=1,
        at=datetime.now(UTC),
        protocol_event_id=1,
        deviation_event_id=None,
        witness_confirmation_id=None,
        report_export_id=None,
        record_type="protocol_approval",
        signature_meaning="approved",
        content_hash="a" * 64,
        hash_scheme_version=1,
        content_payload=None,
        signer_subject="s",
        signer_issuer="i",
        signer_name="n",
        auth_time=datetime.now(UTC),
        jti="j",
        is_demo=True,
    )
    view = signature_view(sig, verified=None)
    assert view is not None
    assert view.verified is None
    assert verified_against(sig, None) is None
    assert verified_against(None, "a" * 64) is None
    assert verified_against(sig, "a" * 64) is True
    assert verified_against(sig, "b" * 64) is False


def test_a_protocol_signature_is_verified_until_its_frozen_copy_is_altered(
    client: TestClient,
    decider: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    import_run(client, decider)
    protocol = client.post(f"/runs/{RUN_ID}/protocol", headers=decider).json()
    make_ready(client, decider, protocol)
    view = submit(client, decider, protocol)
    approve(client, persona_token(demo_issuer, "dewi"), protocol, read_by(view))

    sigs = signatures_of_protocol(read(client, decider))
    assert set(sigs) == {"submitted", "approved"}
    assert [s["verified"] for s in sigs.values()] == [True, True]

    tamper(
        fresh_database,
        "protocol_events",
        "UPDATE protocol_events SET frozen_copy = "
        "jsonb_set(frozen_copy, '{preparer,name}', '\"Mallory\"') WHERE event = 'submitted'",
    )
    got = read(client, decider)
    assert [s["verified"] for s in signatures_of_protocol(got).values()] == [False, False]
    # The stored column still says what it said: only the recompute notices.
    assert got["submission"]["hash"] == view["submission"]["hash"]


def test_deviation_closure_and_witness_signatures_are_verified_until_their_data_is_altered(
    client: TestClient,
    decider: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, persona_token(demo_issuer, "dewi"))
    ex_id = ex["id"]
    _record_pass_for_all_rows(client, decider, ex, skip={R002})
    failed = _record_fail_for_002(client, decider, ex_id)
    dev_id = failed["deviations"][0]["id"]
    latest = next(r for r in failed["rows"] if r["requirement"] == R002)["attempts"][0]["latest"]
    _close_deviation(client, decider, persona_token(demo_issuer, "dewi"), ex_id, dev_id)
    w = client.post(
        f"/executions/{ex_id}/rows/{R002}/attempts/1/witness",
        headers=persona_token(demo_issuer, "eko"),
        json={"version_number": latest["version"], "version_hash": latest["version_hash"]},
    )
    assert w.status_code == 201, w.text

    def signatures() -> tuple[bool | None, bool | None]:
        got = client.get(f"/runs/{RUN_ID}/execution", headers=decider).json()
        dev = next(d for d in got["deviations"] if d["id"] == dev_id)
        closed = dev["events"][-1]["electronic_signature"]
        row = next(r for r in got["rows"] if r["requirement"] == R002)
        witnessed = row["attempts"][0]["latest"]["witness_confirmations"][0]["electronic_signature"]
        return closed["verified"], witnessed["verified"]

    assert signatures() == (True, True)

    tamper(
        fresh_database,
        "execution_deviations",
        "UPDATE execution_deviations SET description = 'altered later'",
    )
    assert signatures() == (False, True)

    tamper(
        fresh_database,
        "execution_attempt_versions",
        "UPDATE execution_attempt_versions SET observation = 'x'",
    )
    assert signatures() == (False, False)


def test_a_qualification_report_signature_is_verified_until_its_snapshot_is_altered(
    client: TestClient,
    decider: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    ex = _start_execution(client, decider, persona_token(demo_issuer, "dewi"))
    ex_id = ex["id"]
    _record_pass_for_all_rows(client, decider, ex)
    completed = client.post(f"/executions/{ex_id}/complete", headers=decider).json()
    assert completed["status"] == "completed"
    r = client.post(
        f"/executions/{ex_id}/qualification-reports",
        headers=persona_token(demo_issuer, "dewi"),
        json={
            "next_requalification_date": (datetime.now(UTC) + timedelta(days=30))
            .date()
            .isoformat(),
            "expected_revision_number": 1,
            "expected_execution_copy_hash": completed["copy_hash"],
        },
    )
    assert r.status_code == 201, r.text

    def verified() -> bool | None:
        got = client.get(f"/runs/{RUN_ID}/qualification-report", headers=decider).json()
        return got["latest_export"]["electronic_signature"]["verified"]

    assert verified() is True
    tamper(
        fresh_database,
        "report_exports",
        "UPDATE report_exports SET snapshot_json = "
        "jsonb_set(snapshot_json, '{conclusion_note}', '\"altered later\"')",
    )
    assert verified() is False
