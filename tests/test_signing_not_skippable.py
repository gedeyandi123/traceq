"""A signing action cannot skip its Electronic Signature (audit #341, A2-4, ticket #361).

Every signing route (submit, approve, close a Deviation, confirm as Witness, approve a
Qualification Report) once signed only when its token carried ``auth_time`` and ``jti`` and
silently wrote the record unsigned otherwise; the routers also took ``fresh_auth`` as optional.
Now ``fresh_auth`` is required and each domain function refuses a token without either claim.

Over HTTP with a real Postgres and the demo issuer. ``lenient_client`` wires the real routers
with a ``fresh_auth`` that checks nothing, as a careless future wiring would: the domain layer
alone must then refuse (401, as ``require_fresh_auth`` does), write no event, no signature and
no Audit Trail entry, and the same request with a fully fresh token must still succeed with a
verified signature.
"""

from __future__ import annotations

import inspect
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from conftest import Databases, DemoIssuer
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_assembled_protocol_api import read
from test_execution_completion_api import (
    _record_fail_for_002,
    _record_pass_for_all_rows,
)
from test_execution_results_api import _start_execution
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, import_run, token
from test_protocol_approval_api import persona_token, read_by
from test_protocol_submission_api import R002, make_ready, submit_url
from test_test_step_proposals import add_drafted_run

from traceq.assembly.api import create_router as assembly_router
from traceq.db import engine
from traceq.execution.api import create_router as execution_router
from traceq.identity import IdentitySettings, Principal, Verifier, authenticate
from traceq.identity.issuer import PERSONAS

CLAIMS = ("auth_time", "jti")
WRITTEN = (
    "protocol_events",
    "execution_deviation_events",
    "execution_witness_confirmations",
    "report_exports",
    "electronic_signatures",
    "audit_trail",
)


def forged(issuer: DemoIssuer, username: str, *, without: str | None = None) -> dict[str, str]:
    """The demo persona's token, signed as the demo issuer signs its own, minus one claim."""
    persona = next(p for p in PERSONAS if p.username == username)
    kid = httpx.get(f"{issuer.url}/jwks").json()["keys"][0]["kid"]
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": issuer.url,
        "sub": persona.subject,
        "aud": issuer.audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "auth_time": int(now.timestamp()),
        "jti": uuid.uuid4().hex,
        "name": persona.name,
        "roles": persona.roles,
    }
    if without is not None:
        del claims[without]
    return bearer(jwt.encode(claims, issuer.key, algorithm="RS256", headers={"kid": kid}))


def counts(databases: Databases) -> dict[str, int]:
    with engine(databases.owner).connect() as c:
        return {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in WRITTEN}


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
def lenient_client(runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases) -> TestClient:
    """The real routers over the same database, but whose ``fresh_auth`` lets anyone through."""
    principal = authenticate(
        Verifier(IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience))
    )

    def anyone(who: Principal) -> Principal:
        return who

    app = FastAPI()
    db = engine(fresh_database.app)
    app.include_router(assembly_router(runs, db, principal, fresh_auth=anyone))
    app.include_router(execution_router(db, principal, fresh_auth=anyone))
    return TestClient(app)


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=True))


def refused(
    lenient: TestClient,
    databases: Databases,
    issuer: DemoIssuer,
    username: str,
    method: str,
    url: str,
    body: Any,
) -> None:
    """The request with a token lacking ``auth_time``, then ``jti``: 401 and nothing written."""
    before = counts(databases)
    for claim in CLAIMS:
        r = lenient.request(method, url, headers=forged(issuer, username, without=claim), json=body)
        assert r.status_code == 401, (claim, r.status_code, r.text)
        assert r.headers["www-authenticate"].startswith(
            'Bearer error="insufficient_user_authentication"'
        )
        assert counts(databases) == before, claim


def test_both_routers_require_fresh_auth() -> None:
    for make in (assembly_router, execution_router):
        param = inspect.signature(make).parameters["fresh_auth"]
        assert param.default is inspect.Parameter.empty, make.__module__
        assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_submit_and_approve_refuse_a_token_without_fresh_auth_claims(
    client: TestClient,
    lenient_client: TestClient,
    decider: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    import_run(client, decider)
    protocol = client.post(f"/runs/{RUN_ID}/protocol", headers=decider).json()
    make_ready(client, decider, protocol)
    draft_hash = read(client, decider)["draft_hash"]
    body = {"expected_draft_hash": draft_hash}

    refused(lenient_client, fresh_database, demo_issuer, "ayu", "POST", submit_url(protocol), body)
    assert read(client, decider)["status"] == "draft"

    r = client.post(submit_url(protocol), headers=decider, json=body)
    assert r.status_code == 200, r.text
    submitted = r.json()

    refused(
        lenient_client,
        fresh_database,
        demo_issuer,
        "dewi",
        "POST",
        f"/protocols/{protocol['id']}/approve",
        read_by(submitted),
    )
    assert read(client, decider)["status"] == "submitted"

    r = client.post(
        f"/protocols/{protocol['id']}/approve",
        headers=persona_token(demo_issuer, "dewi"),
        json=read_by(submitted),
    )
    assert r.status_code == 200, r.text
    signed = {
        e["event"]: e["electronic_signature"]
        for e in read(client, decider)["events"]
        if e["electronic_signature"] is not None
    }
    assert set(signed) == {"submitted", "approved"}
    assert [s["verified"] for s in signed.values()] == [True, True]


def test_close_witness_and_report_refuse_a_token_without_fresh_auth_claims(
    client: TestClient,
    lenient_client: TestClient,
    decider: dict[str, str],
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    # A token signs once (replay guard): every signing request gets a fresh one.
    ex = _start_execution(client, decider, persona_token(demo_issuer, "dewi"))
    ex_id = ex["id"]
    _record_pass_for_all_rows(client, decider, ex, skip={R002})
    failed = _record_fail_for_002(client, decider, ex_id)
    dev_id = failed["deviations"][0]["id"]
    latest = next(r for r in failed["rows"] if r["requirement"] == R002)["attempts"][0]["latest"]
    dev_url = f"/executions/{ex_id}/deviations/{dev_id}"
    r = client.post(
        f"{dev_url}/investigations",
        headers=decider,
        json={
            "investigation": "Turret speed out of range during initial run.",
            "deviation_class": "minor",
            "capa": "Recalibrate drive.",
        },
    )
    assert r.status_code == 201, r.text
    r = client.post(f"{dev_url}/submit", headers=decider)
    assert r.status_code == 200, r.text
    d = next(item for item in r.json()["deviations"] if item["id"] == dev_id)
    close_body = {
        "expected_event_id": d["events"][-1]["id"],
        "expected_investigation_version": d["investigations"][-1]["version"],
        "expected_content_hash": d["closure_content_hash"],
    }

    refused(
        lenient_client, fresh_database, demo_issuer, "dewi", "POST", f"{dev_url}/close", close_body
    )
    r = client.post(f"{dev_url}/close", headers=persona_token(demo_issuer, "dewi"), json=close_body)
    assert r.status_code == 200, r.text

    witness_url = f"/executions/{ex_id}/rows/{R002}/attempts/1/witness"
    witness_body = {"version_number": latest["version"], "version_hash": latest["version_hash"]}
    refused(
        lenient_client,
        fresh_database,
        demo_issuer,
        "eko",
        "POST",
        witness_url,
        witness_body,
    )
    r = client.post(witness_url, headers=persona_token(demo_issuer, "eko"), json=witness_body)
    assert r.status_code == 201, r.text

    completed = client.post(f"/executions/{ex_id}/complete", headers=decider).json()
    assert completed["status"] == "completed", completed
    report_body = {
        "expected_revision_number": 1,
        "expected_execution_copy_hash": completed["copy_hash"],
    }
    report_url = f"/executions/{ex_id}/qualification-reports"
    refused(lenient_client, fresh_database, demo_issuer, "dewi", "POST", report_url, report_body)
    r = client.post(report_url, headers=persona_token(demo_issuer, "dewi"), json=report_body)
    assert r.status_code == 201, r.text

    got = client.get(f"/runs/{RUN_ID}/execution", headers=decider).json()
    dev = next(d for d in got["deviations"] if d["id"] == dev_id)
    row = next(r for r in got["rows"] if r["requirement"] == R002)
    witnessed = row["attempts"][0]["latest"]["witness_confirmations"][0]["electronic_signature"]
    assert dev["events"][-1]["electronic_signature"]["verified"] is True
    assert witnessed["verified"] is True
    report = client.get(f"/runs/{RUN_ID}/qualification-report", headers=decider).json()
    assert report["latest_export"]["electronic_signature"]["verified"] is True


def test_the_demo_issuer_token_carries_what_signing_needs(demo_issuer: DemoIssuer) -> None:
    """Demo (non-Keycloak) signing keeps working: its token has ``auth_time`` and a fresh ``jti``
    per request, so ``require_fresh_auth`` and the signature replay guard both pass."""
    verifier = Verifier(IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience))
    first, second = (
        verifier.verify(token_of(persona_token(demo_issuer, "dewi"))) for _ in range(2)
    )
    for who in (first, second):
        assert who.auth_time is not None
        assert who.jti is not None
    assert first.jti != second.jti


def token_of(headers: dict[str, str]) -> str:
    return headers["Authorization"].removeprefix("Bearer ")
