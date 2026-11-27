"""Database hardening (0015), review rounds schema (0016), and pure diff unit tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import Databases
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from traceq.db import engine, transaction
from traceq.rounds.diff import PreviousFinding, RoundDoc, RoundFindingItem, compute_round_diff


def test_compute_round_diff_tracks_docs_findings_and_decisions() -> None:
    diff = compute_round_diff(
        previous_round_number=1,
        previous_run_id="run-1",
        current_run_id="run-2",
        previous_docs=[
            RoundDoc("URS-1", 0, "a" * 64),
            RoundDoc("FAT-1", 0, "b" * 64),
            RoundDoc("OLD-1", 0, "c" * 64),
        ],
        current_docs=[
            RoundDoc("URS-1", 1, "d" * 64),  # revised
            RoundDoc("FAT-1", 0, "b" * 64),  # unchanged
            RoundDoc("DRAFT-1", 0, "e" * 64),  # added
        ],
        previous_findings=[PreviousFinding(1, "c1"), PreviousFinding(2, "c2")],
        current_findings=[
            RoundFindingItem(2, "c2", state="decided", decided_run_id="run-1"),
            RoundFindingItem(3, "c3", state="undecided", decided_run_id=None),
            RoundFindingItem(4, "c4", state="changed", decided_run_id="run-1"),
        ],
    )
    assert diff.previous_round_number == 1
    assert diff.documents_added == ("DRAFT-1",)
    assert diff.documents_revised == ("URS-1",)
    assert diff.documents_unchanged == ("FAT-1",)
    assert diff.documents_removed == ("OLD-1",)
    assert diff.findings_resolved == 1  # 1
    assert diff.findings_persisted == 1  # 2
    assert diff.findings_new == 2  # 3, 4
    assert diff.decisions_carried_forward == 1  # 2 decided on run-1
    assert diff.decisions_changed == 1  # 4
    assert diff.decisions_undecided == 1  # 3


def test_0015_hardening_triggers_and_checks(fresh_database: Databases) -> None:
    owner_db = engine(fresh_database.owner)
    with transaction(owner_db) as session:
        # 1. imported_runs.imported_at is stamped by DB clock even if caller supplies another time.
        stale = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)
        inserted_at = session.execute(
            text(
                """
                INSERT INTO imported_runs (
                    run_id, equipment, created, model, mode, pipeline_version,
                    prompts, documents, imported_at, completeness
                ) VALUES (
                    'run-0015', 'TP-201', :created, 'm', 'replay', '0.2.0',
                    '{}'::jsonb, '[]'::jsonb, :stale, '{"urs": []}'::jsonb
                ) RETURNING imported_at
                """
            ),
            {"created": stale, "stale": stale},
        ).scalar_one()
        assert inserted_at.year >= 2020

        prop_id = session.execute(
            text(
                """
                INSERT INTO proposals (kind, equipment, subject, subject_hash, ordinal)
                VALUES ('coverage', 'TP-201', '{}'::jsonb, 'h0', 0) RETURNING id
                """
            )
        ).scalar_one()
        session.execute(
            text(
                """
                INSERT INTO run_proposals (
                    run_id, proposal_id, seq, requirement, content_hash, proposed
                ) VALUES ('run-0015', :pid, 0, 'REQ-1', 'c0', '{}'::jsonb)
                """
            ),
            {"pid": prop_id},
        )

        # 2. refuse_change() and no_truncate on imported_runs, proposals, run_proposals.
        for table in ("imported_runs", "proposals", "run_proposals"):
            with pytest.raises(DBAPIError, match="append-only"), session.begin_nested():
                session.execute(text(f"DELETE FROM {table}"))
            with pytest.raises(DBAPIError, match="append-only"), session.begin_nested():
                session.execute(text(f"TRUNCATE {table} CASCADE"))

        # 3. CHECK constraints on execution_attempt_versions and execution_deviation_events.
        session.execute(
            text(
                """
                INSERT INTO assembled_protocols (equipment, run_id)
                VALUES ('TP-201', 'run-0015')
                """
            )
        )
        proto_id = session.execute(
            text("SELECT id FROM assembled_protocols WHERE run_id = 'run-0015'")
        ).scalar_one()
        ev_id = session.execute(
            text(
                """
                INSERT INTO protocol_events (protocol_id, event, subject, issuer, name)
                VALUES (:pid, 'approved', 's', 'i', 'n') RETURNING id
                """
            ),
            {"pid": proto_id},
        ).scalar_one()
        exec_id = session.execute(
            text(
                """
                INSERT INTO protocol_executions (
                    protocol_id, submission_event_id, submission_hash
                ) VALUES (
                    :pid, :eid, :h
                ) RETURNING id
                """
            ),
            {"pid": proto_id, "eid": ev_id, "h": "0" * 64},
        ).scalar_one()
        att_id = session.execute(
            text(
                """
                INSERT INTO execution_attempts (
                    execution_id, requirement, attempt_number, subject, issuer, name
                ) VALUES (:exid, 'REQ-1', 1, 's', 'i', 'n') RETURNING id
                """
            ),
            {"exid": exec_id},
        ).scalar_one()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(
                    """
                    INSERT INTO execution_attempt_versions (
                        attempt_id, version, outcome_kind, value, verdict,
                        version_hash, reason_for_change, subject, issuer, name
                    ) VALUES (
                        :aid, 2, 'value', CAST(:val AS jsonb),
                        'pass', :h, '   ', 's', 'i', 'n'
                    )
                    """
                ),
                {"aid": att_id, "val": '{"type":"present","value":true}', "h": "a" * 64},
            )

        dev_id = session.execute(
            text(
                """
                INSERT INTO execution_deviations (
                    execution_id, deviation_number, cause, description, subject, issuer, name
                ) VALUES (:exid, 1, 'manual', 'desc', 's', 'i', 'n') RETURNING id
                """
            ),
            {"exid": exec_id},
        ).scalar_one()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(
                    """
                    INSERT INTO execution_deviation_events (
                        deviation_id, event, reason, subject, issuer, name
                    ) VALUES (:did, 'returned', '   ', 's', 'i', 'n')
                    """
                ),
                {"did": dev_id},
            )


def test_0016_append_only_and_check_constraints(fresh_database: Databases) -> None:
    owner_db = engine(fresh_database.owner)
    with transaction(owner_db) as session:
        session.execute(
            text(
                """
                INSERT INTO imported_runs (
                    run_id, equipment, created, model, mode, pipeline_version, prompts, documents
                ) VALUES (
                    'run-0016', 'TP-201', now(), 'm', 'replay', '0.2.0', '{}'::jsonb, '[]'::jsonb
                )
                """
            )
        )
        round_id = session.execute(
            text(
                """
                INSERT INTO review_rounds (equipment, round_number, run_id)
                VALUES ('TP-201', 1, 'run-0016') RETURNING id
                """
            )
        ).scalar_one()

        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(
                    """
                    INSERT INTO review_round_events (
                        round_id, event, reason, subject, issuer, name
                    ) VALUES (:rid, 'returned_for_revision', '  ', 's', 'i', 'n')
                    """
                ),
                {"rid": round_id},
            )

        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                text(
                    """
                    INSERT INTO report_exports (
                        round_id, report_kind, subject, issuer, name,
                        snapshot_json, snapshot_hash, pdf_sha256,
                        template_version, typst_version
                    ) VALUES (
                        :rid, 'invalid_kind', 's', 'i', 'n',
                        '{}'::jsonb, :h, :h, '1.0.0', '0.15.2'
                    )
                    """
                ),
                {"rid": round_id, "h": "a" * 64},
            )

        session.execute(
            text(
                """
                INSERT INTO document_versions (
                    equipment, doc_id, rev, source, sha256, first_seen_run_id
                ) VALUES ('TP-201', 'URS-1', 0, 'corpus', :h, 'run-0016')
                """
            ),
            {"h": "a" * 64},
        )
        session.execute(
            text(
                """
                INSERT INTO review_round_events (
                    round_id, event, subject, issuer, name
                ) VALUES (:rid, 'opened', 's', 'i', 'n')
                """
            ),
            {"rid": round_id},
        )
        session.execute(
            text(
                """
                INSERT INTO report_exports (
                    round_id, report_kind, subject, issuer, name,
                    snapshot_json, snapshot_hash, pdf_sha256,
                    template_version, typst_version
                ) VALUES (
                    :rid, 'pre_review', 's', 'i', 'n',
                    '{}'::jsonb, :h, :h, '1.0.0', '0.15.2'
                )
                """
            ),
            {"rid": round_id, "h": "a" * 64},
        )

        for table in (
            "document_versions",
            "review_rounds",
            "review_round_events",
            "report_exports",
        ):
            with pytest.raises(DBAPIError, match="append-only"), session.begin_nested():
                session.execute(text(f"DELETE FROM {table}"))
            with pytest.raises(DBAPIError, match="append-only"), session.begin_nested():
                session.execute(text(f"TRUNCATE {table} CASCADE"))
