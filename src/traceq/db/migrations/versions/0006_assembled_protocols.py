"""The Protocol assembled in TraceQ and its status events (spec #247, "The Protocol and its
rows", "Submission, freezing and approval"; ADR 0012).

``assembled_protocols``: one row per Protocol, for one Equipment, started from one imported
run. ``protocol_events``: its status changes, only added; the current status is the latest
event (``started`` and ``returned`` give Draft). Who acted is the token's subject and issuer
and the name shown at the time; when is the database clock. A return or a withdrawal needs its
reason.

The application role may read and add, nothing else, and the triggers of the Audit Trail
(``0001``) refuse UPDATE, DELETE and TRUNCATE to every role.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_TABLES = ("assembled_protocols", "protocol_events")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE assembled_protocols (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            equipment text NOT NULL,
            run_id text NOT NULL REFERENCES imported_runs (run_id)
        )
    """)
    op.execute("CREATE INDEX assembled_protocols_equipment ON assembled_protocols (equipment)")
    op.execute("CREATE INDEX assembled_protocols_run ON assembled_protocols (run_id)")
    op.execute("""
        CREATE TABLE protocol_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            protocol_id bigint NOT NULL REFERENCES assembled_protocols (id),
            event text NOT NULL CHECK (event IN
                ('started', 'submitted', 'approved', 'returned', 'withdrawn')),
            reason text CHECK (reason IS NULL OR btrim(reason) <> ''),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            CHECK (event NOT IN ('returned', 'withdrawn') OR reason IS NOT NULL)
        )
    """)
    op.execute("CREATE INDEX protocol_events_protocol ON protocol_events (protocol_id)")
    op.execute("""
        CREATE TRIGGER protocol_events_clock BEFORE INSERT ON protocol_events
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
    op.execute("DROP TABLE protocol_events")
    op.execute("DROP TABLE assembled_protocols")
