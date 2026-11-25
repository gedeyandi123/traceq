"""Qualification reports, protocol step attributes, and execution retest links (Step 7, #326).

Extends the schema for Step 7:
- ``execution_attempts``: nullable ``retest_deviation_id`` and ``retest_reason`` on retests
  (``attempt_number > 1``), with non-blank and pair-nullability checks.
- ``protocol_step_attributes``: append-only table recording ``stage`` (``IQ``/``OQ``/null) and
  ``witness_required`` per protocol and requirement.
- ``report_exports``: allows ``report_kind = 'qualification'`` targeting ``execution_id`` with
  nullable ``round_id``.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE execution_attempts
            ADD COLUMN retest_deviation_id bigint REFERENCES execution_deviations (id),
            ADD COLUMN retest_reason text,
            ADD CONSTRAINT execution_attempts_retest_pair_check
                CHECK ((retest_deviation_id IS NULL) = (retest_reason IS NULL)),
            ADD CONSTRAINT execution_attempts_retest_reason_non_blank_check
                CHECK (retest_reason IS NULL OR btrim(retest_reason) <> ''),
            ADD CONSTRAINT execution_attempts_retest_attempt_number_check
                CHECK (attempt_number > 1 OR retest_deviation_id IS NULL)
    """)

    op.execute("""
        CREATE TABLE protocol_step_attributes (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            protocol_id bigint NOT NULL REFERENCES assembled_protocols (id),
            requirement text NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            stage text CHECK (stage IS NULL OR stage IN ('IQ', 'OQ')),
            witness_required boolean NOT NULL DEFAULT false,
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (protocol_id, requirement, version)
        )
    """)
    op.execute(
        "CREATE INDEX protocol_step_attributes_protocol_req "
        "ON protocol_step_attributes (protocol_id, requirement)"
    )
    op.execute("""
        CREATE TRIGGER protocol_step_attributes_clock
        BEFORE INSERT ON protocol_step_attributes
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    op.execute("""
        CREATE TRIGGER protocol_step_attributes_append_only
        BEFORE UPDATE OR DELETE ON protocol_step_attributes
        FOR EACH ROW EXECUTE FUNCTION refuse_change()
    """)
    op.execute("""
        CREATE TRIGGER protocol_step_attributes_no_truncate
        BEFORE TRUNCATE ON protocol_step_attributes
        FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
    """)
    op.execute("REVOKE ALL ON protocol_step_attributes FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON protocol_step_attributes TO traceq_app")

    op.execute("""
        ALTER TABLE report_exports
            ALTER COLUMN round_id DROP NOT NULL,
            ADD COLUMN execution_id bigint REFERENCES protocol_executions (id),
            DROP CONSTRAINT report_exports_report_kind_check,
            ADD CONSTRAINT report_exports_report_kind_check
                CHECK (report_kind IN ('pre_review', 'qualification')),
            ADD CONSTRAINT report_exports_kind_target_check
                CHECK (
                    (report_kind = 'pre_review' AND round_id IS NOT NULL AND execution_id IS NULL)
                    OR (report_kind = 'qualification' AND execution_id IS NOT NULL)
                )
    """)
    op.execute(
        "CREATE INDEX report_exports_execution "
        "ON report_exports (execution_id) WHERE execution_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX report_exports_execution")
    op.execute("""
        ALTER TABLE report_exports
            DROP CONSTRAINT report_exports_kind_target_check,
            DROP CONSTRAINT report_exports_report_kind_check,
            ADD CONSTRAINT report_exports_report_kind_check
                CHECK (report_kind IN ('pre_review')),
            DROP COLUMN execution_id,
            ALTER COLUMN round_id SET NOT NULL
    """)

    op.execute("DROP TABLE protocol_step_attributes")

    op.execute("""
        ALTER TABLE execution_attempts
            DROP CONSTRAINT execution_attempts_retest_attempt_number_check,
            DROP CONSTRAINT execution_attempts_retest_reason_non_blank_check,
            DROP CONSTRAINT execution_attempts_retest_pair_check,
            DROP COLUMN retest_reason,
            DROP COLUMN retest_deviation_id
    """)
