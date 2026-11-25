"""Frozen copy and SHA-256 hash stored when an Execution is completed (ADR 0013, spec #270,
#275).

Append-only table ``execution_completions``: stores the canonical JSON frozen copy of the
completed Execution (every row, attempt, version, Witness confirmation, and Deviation) and its
SHA-256 ``copy_hash``, bound 1:1 to ``protocol_executions`` and the ``completed`` event in
``execution_events``.

The application role may read and add, nothing else, and triggers refuse UPDATE, DELETE and
TRUNCATE to every role. ``stamp_database_clock()`` sets every row's ``at`` from the database.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_TABLE = "execution_completions"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE {_TABLE} (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            execution_id bigint NOT NULL UNIQUE REFERENCES protocol_executions (id),
            event_id bigint NOT NULL UNIQUE REFERENCES execution_events (id),
            frozen_copy jsonb NOT NULL,
            copy_hash text NOT NULL CHECK (copy_hash ~ '^[0-9a-f]{{64}}$')
        )
    """)
    op.execute(f"""
        CREATE TRIGGER {_TABLE}_clock BEFORE INSERT ON {_TABLE}
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    op.execute(f"""
        CREATE TRIGGER {_TABLE}_append_only BEFORE UPDATE OR DELETE ON {_TABLE}
        FOR EACH ROW EXECUTE FUNCTION refuse_change()
    """)
    op.execute(f"""
        CREATE TRIGGER {_TABLE}_no_truncate BEFORE TRUNCATE ON {_TABLE}
        FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
    """)
    op.execute(f"REVOKE ALL ON {_TABLE} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO traceq_app")


def downgrade() -> None:
    op.execute(f"DROP TABLE {_TABLE}")
