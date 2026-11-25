"""Execution attempts, versioned Results, and automatic Deviations (ADR 0013, spec #270, #272).

Append-only tables:
- ``execution_attempts``: ordered attempts (1, 2, ...) on a Test Step row of an Execution.
- ``execution_attempt_versions``: immutable versions (1, 2, ...) of an attempt's Result,
  judged by code, with instruments, evidence references, and SHA-256 canonical JSON hash.
- ``execution_deviations``: numbered (1, 2, ...) per Execution, opened automatically by code
  for ``failed`` or ``no_calibrated_instrument`` (or manually later).
- ``execution_deviation_events``: status events (``opened``, ``submitted``, ``returned``,
  ``closed``); current status is the latest event.

The application role may read and add, nothing else, and triggers refuse UPDATE, DELETE and
TRUNCATE to every role. ``stamp_database_clock()`` sets every row's ``at`` from the database.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_TABLES = (
    "execution_attempts",
    "execution_attempt_versions",
    "execution_deviations",
    "execution_deviation_events",
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE execution_attempts (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            execution_id bigint NOT NULL REFERENCES protocol_executions (id),
            requirement text NOT NULL,
            attempt_number integer NOT NULL CHECK (attempt_number >= 1),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (execution_id, requirement, attempt_number)
        )
    """)
    op.execute(
        "CREATE INDEX execution_attempts_exec_req ON execution_attempts (execution_id, requirement)"
    )

    op.execute("""
        CREATE TABLE execution_attempt_versions (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            attempt_id bigint NOT NULL REFERENCES execution_attempts (id),
            version integer NOT NULL CHECK (version >= 1),
            outcome_kind text NOT NULL CHECK (outcome_kind IN ('value', 'not_performable')),
            not_performable_reason text,
            value jsonb,
            observation text,
            instruments jsonb NOT NULL DEFAULT '[]'::jsonb,
            no_calibrated_instrument_reason text,
            evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
            verdict text NOT NULL CHECK (verdict IN ('pass', 'fail')),
            version_hash text NOT NULL CHECK (version_hash ~ '^[0-9a-f]{64}$'),
            reason_for_change text,
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (attempt_id, version),
            CHECK (
                (
                    outcome_kind = 'not_performable'
                    AND not_performable_reason IS NOT NULL
                    AND value IS NULL
                )
                OR (outcome_kind = 'value' AND not_performable_reason IS NULL AND value IS NOT NULL)
            )
        )
    """)
    op.execute(
        "CREATE INDEX execution_attempt_versions_attempt ON execution_attempt_versions (attempt_id)"
    )

    op.execute("""
        CREATE TABLE execution_deviations (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            execution_id bigint NOT NULL REFERENCES protocol_executions (id),
            deviation_number integer NOT NULL CHECK (deviation_number >= 1),
            requirement text,
            attempt_id bigint REFERENCES execution_attempts (id),
            cause text NOT NULL CHECK (cause IN ('failed', 'no_calibrated_instrument', 'manual')),
            description text NOT NULL,
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (execution_id, deviation_number)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX execution_deviations_attempt_cause "
        "ON execution_deviations (attempt_id, cause) WHERE attempt_id IS NOT NULL"
    )
    op.execute("CREATE INDEX execution_deviations_execution ON execution_deviations (execution_id)")

    op.execute("""
        CREATE TABLE execution_deviation_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            deviation_id bigint NOT NULL REFERENCES execution_deviations (id),
            event text NOT NULL CHECK (event IN ('opened', 'submitted', 'returned', 'closed')),
            reason text,
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX execution_deviation_events_deviation "
        "ON execution_deviation_events (deviation_id)"
    )

    for table in _TABLES:
        op.execute(f"""
            CREATE TRIGGER {table}_clock BEFORE INSERT ON {table}
            FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
        """)
        op.execute(f"""
            CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION refuse_change()
        """)
        op.execute(f"""
            CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
        """)
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO traceq_app")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE {table}")
