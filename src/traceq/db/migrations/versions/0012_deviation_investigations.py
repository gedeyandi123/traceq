"""Deviation Investigation versions (ADR 0013, spec #270, #273).

Append-only table ``execution_deviation_investigations``: immutable versions (1, 2, ...) of a
Deviation's Investigation (root cause & impact), class (``minor``/``major``/``critical``),
optional CAPA text, and Reason for Change (required from version 2 onwards).

The application role may read and add, nothing else, and triggers refuse UPDATE, DELETE and
TRUNCATE to every role. ``stamp_database_clock()`` sets every row's ``at`` from the database.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_TABLE = "execution_deviation_investigations"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE {_TABLE} (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            deviation_id bigint NOT NULL REFERENCES execution_deviations (id),
            version integer NOT NULL CHECK (version >= 1),
            investigation text NOT NULL CHECK (btrim(investigation) <> ''),
            deviation_class text NOT NULL CHECK (deviation_class IN ('minor', 'major', 'critical')),
            capa text,
            reason_for_change text,
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (deviation_id, version),
            CHECK (
                version = 1
                OR (reason_for_change IS NOT NULL AND btrim(reason_for_change) <> '')
            )
        )
    """)
    op.execute(f"CREATE INDEX {_TABLE}_deviation ON {_TABLE} (deviation_id)")
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
