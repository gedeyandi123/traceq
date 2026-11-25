"""Review rounds, document versions, and pre-review report exports (Step 6, #319).

Append-only tables:
- ``document_versions``: distinct (equipment, doc_id, rev, sha256) seen across imported runs.
- ``review_rounds``: 1:1 with ``imported_runs``, numbered 1, 2, ... per Equipment.
- ``review_round_events``: ``opened``, ``returned_for_revision``, ``ready_for_protocol``.
- ``report_exports``: immutable snapshot + hashes of exported Typst PDF reports.

The application role may read and add, nothing else, and triggers refuse UPDATE, DELETE and
TRUNCATE to every role. ``stamp_database_clock()`` sets every row's ``at`` from the database.
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_TABLES = (
    "document_versions",
    "review_rounds",
    "review_round_events",
    "report_exports",
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_versions (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            equipment text NOT NULL,
            doc_id text NOT NULL,
            rev integer NOT NULL,
            doc_type text,
            source text NOT NULL CHECK (source IN ('corpus', 'review_package_draft')),
            sha256 text NOT NULL,
            first_seen_run_id text NOT NULL REFERENCES imported_runs (run_id),
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (equipment, doc_id, rev, sha256)
        )
    """)
    op.execute("CREATE INDEX document_versions_equipment ON document_versions (equipment)")

    op.execute("""
        CREATE TABLE review_rounds (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            equipment text NOT NULL,
            round_number integer NOT NULL CHECK (round_number >= 1),
            run_id text NOT NULL UNIQUE REFERENCES imported_runs (run_id),
            previous_round_id bigint REFERENCES review_rounds (id),
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (equipment, round_number)
        )
    """)
    op.execute("CREATE INDEX review_rounds_equipment ON review_rounds (equipment)")

    op.execute("""
        CREATE TABLE review_round_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            round_id bigint NOT NULL REFERENCES review_rounds (id),
            event text NOT NULL CHECK (
                event IN ('opened', 'returned_for_revision', 'ready_for_protocol')
            ),
            reason text,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            CHECK (
                event <> 'returned_for_revision'
                OR (reason IS NOT NULL AND btrim(reason) <> '')
            )
        )
    """)
    op.execute("CREATE INDEX review_round_events_round ON review_round_events (round_id)")

    op.execute("""
        CREATE TABLE report_exports (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            round_id bigint NOT NULL REFERENCES review_rounds (id),
            report_kind text NOT NULL CHECK (report_kind IN ('pre_review')),
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            snapshot_json jsonb NOT NULL,
            snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
            pdf_sha256 text NOT NULL CHECK (pdf_sha256 ~ '^[0-9a-f]{64}$'),
            template_version text NOT NULL,
            typst_version text NOT NULL
        )
    """)
    op.execute("CREATE INDEX report_exports_round ON report_exports (round_id)")

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
