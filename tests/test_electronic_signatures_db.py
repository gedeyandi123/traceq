"""Database & API tests for Electronic Signatures, auth_time/replay, Anti-TOCTOU, and Typst v2."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from traceq import audit
from traceq.app.api import create_app
from traceq.db import engine, transaction
from traceq.identity import (
    APPROVING_ROLE,
    DECIDING_ROLE,
    EXECUTING_ROLE,
    WITNESSING_ROLE,
    IdentitySettings,
)
from traceq.reports import (
    QUALIFICATION_TEMPLATE_VERSION,
    QUALIFICATION_TEMPLATE_VERSION_V1,
    QualificationCounts,
    QualificationReportSnapshot,
    QualificationReportSnapshotV1,
    SignatureSnapshotClaim,
    parse_qualification_snapshot,
    qualification_snapshot_hash,
    render_qualification_pdf,
)


def _fresh_token(
    issuer: DemoIssuer,
    *,
    sub: str,
    name: str,
    roles: list[str],
    jti: str,
    auth_time: datetime | None = None,
    amr: list[str] | None = None,
) -> dict[str, str]:
    now = datetime.now(UTC)
    kid = httpx.get(f"{issuer.url}/jwks").json()["keys"][0]["kid"]
    payload: dict[str, object] = {
        "iss": issuer.url,
        "sub": sub,
        "aud": issuer.audience,
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "auth_time": int((auth_time or now).timestamp()),
        "jti": jti,
        "amr": [] if amr is None else amr,
        "name": name,
        "roles": roles,
    }
    tok = jwt.encode(payload, issuer.key, algorithm="RS256", headers={"kid": kid})
    return {"authorization": f"Bearer {tok}"}


def test_0018_triggers_grants_exclusive_arc_and_replay(fresh_database: Databases) -> None:
    owner_db = engine(fresh_database.owner)
    app_db = engine(fresh_database.app)

    with transaction(owner_db) as session:
        session.execute(
            text(
                """
                INSERT INTO imported_runs (
                    run_id, equipment, created, model, mode, pipeline_version,
                    prompts, documents
                ) VALUES (
                    'run-0018', 'TP-201', now(), 'm', 'replay', '0.2.0',
                    '{}'::jsonb, '[]'::jsonb
                )
                """
            )
        )
        proto_id = session.execute(
            text(
                "INSERT INTO assembled_protocols (equipment, run_id) "
                "VALUES ('TP-201', 'run-0018') RETURNING id"
            )
        ).scalar_one()
        started_id = session.execute(
            text(
                """
                INSERT INTO protocol_events (protocol_id, event, subject, issuer, name)
                VALUES (:pid, 'started', 'u1', 'iss', 'User 1') RETURNING id
                """
            ),
            {"pid": proto_id},
        ).scalar_one()
        submitted_id = session.execute(
            text(
                """
                INSERT INTO protocol_events (
                    protocol_id, event, frozen_copy, copy_hash, subject, issuer, name
                ) VALUES (
                    :pid, 'submitted', '{}'::jsonb, :h, 'u1', 'iss', 'User 1'
                ) RETURNING id
                """
            ),
            {"pid": proto_id, "h": "a" * 64},
        ).scalar_one()

        submitted_id_2 = session.execute(
            text(
                """
                INSERT INTO protocol_events (
                    protocol_id, event, frozen_copy, copy_hash, subject, issuer, name
                ) VALUES (
                    :pid, 'submitted', '{}'::jsonb, :h, 'u1', 'iss', 'User 1'
                ) RETURNING id
                """
            ),
            {"pid": proto_id, "h": "b" * 64},
        ).scalar_one()

        # 1. Wrong target event ('started' for protocol_submission) -> rejected by trigger
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(
                    """
                        INSERT INTO electronic_signatures (
                            protocol_event_id, record_type, signature_meaning, content_hash,
                            signer_subject, signer_issuer, signer_name, auth_time, jti
                        ) VALUES (
                            :eid, 'protocol_submission', 'prepared', :h,
                            'u1', 'iss', 'User 1', now(), 'jti-bad-ev'
                        )
                        """
                ),
                {"eid": started_id, "h": "a" * 64},
            )

        # 2. Mismatched signer_subject -> rejected by trigger
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(
                    """
                        INSERT INTO electronic_signatures (
                            protocol_event_id, record_type, signature_meaning, content_hash,
                            signer_subject, signer_issuer, signer_name, auth_time, jti
                        ) VALUES (
                            :eid, 'protocol_submission', 'prepared', :h,
                            'other', 'iss', 'Other', now(), 'jti-bad-sub'
                        )
                        """
                ),
                {"eid": submitted_id, "h": "a" * 64},
            )

        # 3. Wrong signature_meaning for record_type -> rejected by CHECK
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(
                    """
                        INSERT INTO electronic_signatures (
                            protocol_event_id, record_type, signature_meaning, content_hash,
                            signer_subject, signer_issuer, signer_name, auth_time, jti
                        ) VALUES (
                            :eid, 'protocol_submission', 'approved', :h,
                            'u1', 'iss', 'User 1', now(), 'jti-bad-meaning'
                        )
                        """
                ),
                {"eid": submitted_id, "h": "a" * 64},
            )

    # 4. Valid insert via app role + stamp_database_clock + replay conflict
    with transaction(app_db) as session:
        sig = audit.record_signature(
            session,
            audit.Actor(subject="u1", issuer="iss", name="User 1"),
            record_type="protocol_submission",
            signature_meaning="prepared",
            content_hash="a" * 64,
            auth_time=datetime.now(UTC),
            jti="jti-valid-1",
            is_demo=False,
            protocol_event_id=submitted_id,
        )
        assert sig.at.year >= 2020
        assert audit.signature_label(sig) == audit.ELECTRONIC_SIGNATURE_LABEL
        assert audit.verify_signature(sig, "a" * 64) is True
        assert audit.verify_signature(sig, "b" * 64) is False

        # Replay of (signer_issuer, jti) on a different event -> SignatureReplayConflict
        with pytest.raises(audit.SignatureReplayConflict), session.begin_nested():
            audit.record_signature(
                session,
                audit.Actor(subject="u1", issuer="iss", name="User 1"),
                record_type="protocol_submission",
                signature_meaning="prepared",
                content_hash="b" * 64,
                auth_time=datetime.now(UTC),
                jti="jti-valid-1",
                is_demo=False,
                protocol_event_id=submitted_id_2,
            )

    # 5. Append-only triggers + traceq_app grants
    with transaction(app_db) as session:
        with pytest.raises(DBAPIError), session.begin_nested():
            session.execute(text("UPDATE electronic_signatures SET signer_name = 'x'"))
        with pytest.raises(DBAPIError), session.begin_nested():
            session.execute(text("DELETE FROM electronic_signatures"))

    with transaction(owner_db) as session, pytest.raises(DBAPIError), session.begin_nested():
        session.execute(text("TRUNCATE electronic_signatures"))


def test_signing_endpoints_fresh_auth_replay_and_antitoctou(
    fresh_database: Databases, demo_issuer: DemoIssuer, tmp_path: Path
) -> None:
    app = create_app(
        tmp_path,
        identity=IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience),
        database=fresh_database.app,
    )
    client = TestClient(app)

    # Seed minimal run + protocol + execution? Easier: test 403 before 401 on signing endpoints
    stale_time = datetime.now(UTC) - timedelta(minutes=5)
    wrong_role_stale = _fresh_token(
        demo_issuer,
        sub="u-reader",
        name="Reader",
        roles=[],
        jti="jti-reader-stale",
        auth_time=stale_time,
    )
    # 403 must fire BEFORE 401 stale auth_time
    r403 = client.post(
        "/protocols/1/submit", headers=wrong_role_stale, json={"expected_draft_hash": "a" * 64}
    )
    assert r403.status_code == 403

    r403_app = client.post(
        "/protocols/1/approve",
        headers=wrong_role_stale,
        json={"submission_event_id": 1, "hash": "a" * 64},
    )
    assert r403_app.status_code == 403

    # With right role + stale auth_time -> 401 + RFC 9470 header
    decider_stale = _fresh_token(
        demo_issuer,
        sub="u-dec",
        name="Decider",
        roles=[DECIDING_ROLE],
        jti="jti-dec-stale",
        auth_time=stale_time,
    )
    r401 = client.post(
        "/protocols/1/submit", headers=decider_stale, json={"expected_draft_hash": "a" * 64}
    )
    assert r401.status_code == 401
    assert r401.headers.get("www-authenticate") == (
        'Bearer error="insufficient_user_authentication", max_age=60'
    )

    approver_stale = _fresh_token(
        demo_issuer,
        sub="u-app",
        name="Approver",
        roles=[APPROVING_ROLE],
        jti="jti-app-stale",
        auth_time=stale_time,
    )
    r401_close = client.post(
        "/executions/1/deviations/1/close",
        headers=approver_stale,
        json={
            "expected_event_id": 1,
            "expected_investigation_version": 1,
            "expected_content_hash": "a" * 64,
        },
    )
    assert r401_close.status_code == 401
    assert r401_close.headers.get("www-authenticate") == (
        'Bearer error="insufficient_user_authentication", max_age=60'
    )

    witness_stale = _fresh_token(
        demo_issuer,
        sub="u-wit",
        name="Witness",
        roles=[WITNESSING_ROLE],
        jti="jti-wit-stale",
        auth_time=stale_time,
    )
    r401_wit = client.post(
        "/executions/1/rows/R-1/attempts/1/witness",
        headers=witness_stale,
        json={"version_number": 1, "version_hash": "a" * 64},
    )
    assert r401_wit.status_code == 401
    assert r401_wit.headers.get("www-authenticate") == (
        'Bearer error="insufficient_user_authentication", max_age=60'
    )

    r401_rep = client.post(
        "/executions/1/qualification-reports",
        headers=approver_stale,
        json={
            "expected_revision_number": 1,
            "expected_execution_copy_hash": "a" * 64,
        },
    )
    assert r401_rep.status_code == 401
    assert r401_rep.headers.get("www-authenticate") == (
        'Bearer error="insufficient_user_authentication", max_age=60'
    )

    # Suppress unused import lint on EXECUTING_ROLE
    assert EXECUTING_ROLE


def test_typst_v1_and_v2_snapshot_and_rerender_without_jti() -> None:
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    counts = QualificationCounts(
        iq_total=1,
        iq_passed=1,
        iq_failed=0,
        oq_total=0,
        oq_passed=0,
        oq_failed=0,
        unsplit_total=0,
        unsplit_passed=0,
        unsplit_failed=0,
        vendor_reference_count=0,
        total_rows=1,
        total_deviations=0,
    )
    v1_dict = {
        "generated_at": now.isoformat(),
        "equipment": "TP-201",
        "run_id": "run-1",
        "protocol_id": 1,
        "execution_id": 1,
        "revision_number": 1,
        "protocol_submission_hash": "a" * 64,
        "execution_copy_hash": "b" * 64,
        "completed_at": now.isoformat(),
        "completer_name": "Ayu",
        "approver_name": "Dewi",
        "approver_subject": "demo-0004",
        "approver_issuer": "http://127.0.0.1:9000",
        "approval_note": "a recorded status, not an Electronic Signature (ADR 0007 phase 2)",
        "technical_conclusion": "qualified",
        "conclusion_note": None,
        "next_requalification_date": None,
        "counts": counts.model_dump(mode="json"),
        "rows": [],
        "deviations": [],
    }
    v1_snap = parse_qualification_snapshot(v1_dict, QUALIFICATION_TEMPLATE_VERSION_V1)
    assert isinstance(v1_snap, QualificationReportSnapshotV1)
    v1_pdf = render_qualification_pdf(v1_snap, template_version=QUALIFICATION_TEMPLATE_VERSION_V1)
    assert v1_pdf.startswith(b"%PDF")
    assert (
        hashlib.sha256(v1_pdf).hexdigest()
        == hashlib.sha256(
            render_qualification_pdf(v1_snap, template_version=QUALIFICATION_TEMPLATE_VERSION_V1)
        ).hexdigest()
    )
    # V1 hash does not include electronic_signature
    assert "electronic_signature" not in v1_snap.model_dump(mode="json")
    assert len(qualification_snapshot_hash(v1_snap)) == 64

    v2_snap = QualificationReportSnapshot(
        generated_at=now,
        equipment="TP-201",
        run_id="run-1",
        protocol_id=1,
        execution_id=1,
        revision_number=2,
        protocol_submission_hash="a" * 64,
        execution_copy_hash="b" * 64,
        completed_at=now,
        completer_name="Ayu",
        approver_name="Dewi",
        approver_subject="kc-dewi",
        approver_issuer="http://127.0.0.1:8180/realms/traceq",
        approval_note=audit.ELECTRONIC_SIGNATURE_LABEL,
        technical_conclusion="qualified",
        counts=counts,
        electronic_signature=SignatureSnapshotClaim(
            record_type="qualification_report",
            signature_meaning="approved",
            content_hash="c" * 64,
            hash_scheme_version=1,
            signer_subject="kc-dewi",
            signer_issuer="http://127.0.0.1:8180/realms/traceq",
            signer_name="Dewi",
            auth_time=now,
            signed_at=now,
            is_demo=False,
            label=audit.ELECTRONIC_SIGNATURE_LABEL,
        ),
    )
    assert "jti" not in v2_snap.model_dump(mode="json")["electronic_signature"]
    v2_pdf = render_qualification_pdf(v2_snap, template_version=QUALIFICATION_TEMPLATE_VERSION)
    assert v2_pdf.startswith(b"%PDF")
    assert v2_pdf == render_qualification_pdf(
        v2_snap, template_version=QUALIFICATION_TEMPLATE_VERSION
    )
