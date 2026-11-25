"""Witness confirmations bound to attempt version hashes (ADR 0013, spec #270, #274).

Append-only table ``execution_witness_confirmations``: records a Witness's confirmation of a
specific ``execution_attempt_versions`` row and its ``version_hash``. A Witness cannot confirm
the same version twice, while another witnessing person may confirm it too.

The application role may read and add, nothing else, and triggers refuse UPDATE, DELETE and
TRUNCATE to every role. ``stamp_database_clock()`` sets every row's ``at`` from the database.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_TABLE = "execution_witness_confirmations"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE {_TABLE} (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            version_id bigint NOT NULL REFERENCES execution_attempt_versions (id),
            version_hash text NOT NULL CHECK (version_hash ~ '^[0-9a-f]{{64}}$'),
            witness_subject text NOT NULL,
            witness_issuer text NOT NULL,
            witness_name text NOT NULL,
            UNIQUE (version_id, witness_subject, witness_issuer)
        )
    """)
    op.execute(f"CREATE INDEX {_TABLE}_version ON {_TABLE} (version_id)")
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
