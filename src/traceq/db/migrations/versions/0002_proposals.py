"""Imported runs and their Proposals, with an identity that holds across runs (spec #105).

``imported_runs``: the provenance of each imported run. ``proposals``: one row per subject
key (what a Proposal is about) and its order among Proposals of one run with that key.
``run_proposals``: what each run proposed about it, as proposed, with the hash of the content
a decision rests on, where it stands in the run's files, and its order in them (``seq``).

The application role may read and add, nothing else: an import is never undone or rewritten.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE imported_runs (
            run_id text PRIMARY KEY,
            equipment text NOT NULL,
            created timestamptz NOT NULL,
            model text NOT NULL,
            mode text NOT NULL,
            pipeline_version text NOT NULL,
            prompts jsonb NOT NULL,
            documents jsonb NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE proposals (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            kind text NOT NULL CHECK (kind IN ('coverage', 'check', 'ai')),
            equipment text NOT NULL,
            subject jsonb NOT NULL,
            subject_hash text NOT NULL,
            ordinal integer NOT NULL CHECK (ordinal >= 0),
            UNIQUE (subject_hash, ordinal)
        )
    """)
    op.execute("""
        CREATE TABLE run_proposals (
            run_id text NOT NULL REFERENCES imported_runs (run_id),
            proposal_id bigint NOT NULL REFERENCES proposals (id),
            seq integer NOT NULL,
            requirement text,
            position integer,
            content_hash text NOT NULL,
            proposed jsonb NOT NULL,
            PRIMARY KEY (run_id, proposal_id),
            CHECK ((requirement IS NULL) <> (position IS NULL))
        )
    """)
    for table in ("imported_runs", "proposals", "run_proposals"):
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO traceq_app")


def downgrade() -> None:
    op.execute("DROP TABLE run_proposals")
    op.execute("DROP TABLE proposals")
    op.execute("DROP TABLE imported_runs")
