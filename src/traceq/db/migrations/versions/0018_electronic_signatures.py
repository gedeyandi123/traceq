"""Electronic Signatures table and append-only triggers (Step 8, spec #333, #334).

Append-only table ``electronic_signatures`` using an Exclusive Arc of four nullable UNIQUE FKs:
- ``protocol_event_id`` -> ``protocol_events (id)`` (``protocol_submission``, ``protocol_approval``)
- ``deviation_event_id`` -> ``execution_deviation_events (id)`` (``deviation_closure``)
- ``witness_confirmation_id`` -> ``execution_witness_confirmations (id)`` (``witness_confirmation``)
- ``report_export_id`` -> ``report_exports (id)`` (``qualification_report``)

Enforces ``UNIQUE (signer_issuer, jti)`` for anti-replay, ``BEFORE INSERT`` target verification
(matching ``event``/``report_kind`` and ``(signer_subject, signer_issuer)``), database clock
stamping, and ``refuse_change()`` on UPDATE/DELETE/TRUNCATE.
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_TABLE = "electronic_signatures"
_VERIFY_FN = "verify_electronic_signature_target"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE {_TABLE} (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            protocol_event_id bigint UNIQUE REFERENCES protocol_events (id),
            deviation_event_id bigint UNIQUE REFERENCES execution_deviation_events (id),
            witness_confirmation_id bigint UNIQUE
                REFERENCES execution_witness_confirmations (id),
            report_export_id bigint UNIQUE REFERENCES report_exports (id),
            record_type text NOT NULL CHECK (
                record_type IN (
                    'protocol_submission',
                    'protocol_approval',
                    'deviation_closure',
                    'witness_confirmation',
                    'qualification_report'
                )
            ),
            signature_meaning text NOT NULL CHECK (
                signature_meaning IN ('prepared', 'approved', 'witnessed')
            ),
            content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{{64}}$'),
            hash_scheme_version integer NOT NULL DEFAULT 1 CHECK (hash_scheme_version >= 1),
            content_payload jsonb,
            signer_subject text NOT NULL CHECK (btrim(signer_subject) <> ''),
            signer_issuer text NOT NULL CHECK (btrim(signer_issuer) <> ''),
            signer_name text NOT NULL CHECK (btrim(signer_name) <> ''),
            auth_time timestamptz NOT NULL,
            jti text NOT NULL CHECK (btrim(jti) <> ''),
            is_demo boolean NOT NULL DEFAULT false,
            CONSTRAINT electronic_signatures_signer_issuer_jti_key UNIQUE (signer_issuer, jti),
            CONSTRAINT electronic_signatures_exclusive_arc_check CHECK (
                num_nonnulls(
                    protocol_event_id,
                    deviation_event_id,
                    witness_confirmation_id,
                    report_export_id
                ) = 1
            ),
            CONSTRAINT electronic_signatures_record_type_target_check CHECK (
                (
                    record_type IN ('protocol_submission', 'protocol_approval')
                    AND protocol_event_id IS NOT NULL
                )
                OR (record_type = 'deviation_closure' AND deviation_event_id IS NOT NULL)
                OR (record_type = 'witness_confirmation' AND witness_confirmation_id IS NOT NULL)
                OR (record_type = 'qualification_report' AND report_export_id IS NOT NULL)
            ),
            CONSTRAINT electronic_signatures_record_type_meaning_check CHECK (
                (record_type = 'protocol_submission' AND signature_meaning = 'prepared')
                OR (
                    record_type IN (
                        'protocol_approval',
                        'deviation_closure',
                        'qualification_report'
                    )
                    AND signature_meaning = 'approved'
                )
                OR (record_type = 'witness_confirmation' AND signature_meaning = 'witnessed')
            )
        )
    """)

    op.execute(f"""
        CREATE FUNCTION {_VERIFY_FN}() RETURNS trigger LANGUAGE plpgsql AS $f$
        DECLARE
            v_match boolean := false;
        BEGIN
            IF NEW.record_type = 'protocol_submission' THEN
                SELECT EXISTS (
                    SELECT 1 FROM protocol_events
                    WHERE id = NEW.protocol_event_id
                      AND event = 'submitted'
                      AND subject = NEW.signer_subject
                      AND issuer = NEW.signer_issuer
                ) INTO v_match;
            ELSIF NEW.record_type = 'protocol_approval' THEN
                SELECT EXISTS (
                    SELECT 1 FROM protocol_events
                    WHERE id = NEW.protocol_event_id
                      AND event = 'approved'
                      AND subject = NEW.signer_subject
                      AND issuer = NEW.signer_issuer
                ) INTO v_match;
            ELSIF NEW.record_type = 'deviation_closure' THEN
                SELECT EXISTS (
                    SELECT 1 FROM execution_deviation_events
                    WHERE id = NEW.deviation_event_id
                      AND event = 'closed'
                      AND subject = NEW.signer_subject
                      AND issuer = NEW.signer_issuer
                ) INTO v_match;
            ELSIF NEW.record_type = 'witness_confirmation' THEN
                SELECT EXISTS (
                    SELECT 1 FROM execution_witness_confirmations
                    WHERE id = NEW.witness_confirmation_id
                      AND witness_subject = NEW.signer_subject
                      AND witness_issuer = NEW.signer_issuer
                ) INTO v_match;
            ELSIF NEW.record_type = 'qualification_report' THEN
                SELECT EXISTS (
                    SELECT 1 FROM report_exports
                    WHERE id = NEW.report_export_id
                      AND report_kind = 'qualification'
                      AND subject = NEW.signer_subject
                      AND issuer = NEW.signer_issuer
                ) INTO v_match;
            END IF;

            IF NOT v_match THEN
                RAISE EXCEPTION
                    'electronic_signature target mismatch for record_type %',
                    NEW.record_type
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END
        $f$
    """)

    op.execute(f"""
        CREATE TRIGGER {_TABLE}_clock
        BEFORE INSERT ON {_TABLE}
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    op.execute(f"""
        CREATE TRIGGER {_TABLE}_verify_target
        BEFORE INSERT ON {_TABLE}
        FOR EACH ROW EXECUTE FUNCTION {_VERIFY_FN}()
    """)
    op.execute(f"""
        CREATE TRIGGER {_TABLE}_append_only
        BEFORE UPDATE OR DELETE ON {_TABLE}
        FOR EACH ROW EXECUTE FUNCTION refuse_change()
    """)
    op.execute(f"""
        CREATE TRIGGER {_TABLE}_no_truncate
        BEFORE TRUNCATE ON {_TABLE}
        FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
    """)
    op.execute(f"REVOKE ALL ON {_TABLE} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO traceq_app")


def downgrade() -> None:
    op.execute(f"DROP TABLE {_TABLE}")
    op.execute(f"DROP FUNCTION {_VERIFY_FN}()")
