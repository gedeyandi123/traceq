"""Executions of Approved Protocols and their status events (ADR 0013, spec #270, #271).

``protocol_executions``: at most one Execution per Approved Protocol, bound to the Protocol's
``submitted`` event id and frozen-copy hash. ``execution_events``: its status changes, only
added; the current status is the latest event (``started`` gives ``in_progress``).

The application role may read and add, nothing else, and the triggers of the Audit Trail
(``0001``) refuse UPDATE, DELETE and TRUNCATE to every role.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_TABLES = ("protocol_executions", "execution_events")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE protocol_executions (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            protocol_id bigint NOT NULL UNIQUE REFERENCES assembled_protocols (id),
            submission_event_id bigint NOT NULL REFERENCES protocol_events (id),
            submission_hash text NOT NULL CHECK (submission_hash ~ '^[0-9a-f]{64}$')
        )
    """)
    op.execute("""
        CREATE TABLE execution_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            execution_id bigint NOT NULL REFERENCES protocol_executions (id),
            event text NOT NULL CHECK (event IN ('started', 'completed')),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL
        )
    """)
    op.execute("CREATE INDEX execution_events_execution ON execution_events (execution_id)")
    op.execute("""
        CREATE TRIGGER execution_events_clock BEFORE INSERT ON execution_events
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    for table in _TABLES:
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
    op.execute("DROP TABLE execution_events")
    op.execute("DROP TABLE protocol_executions")
