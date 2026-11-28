"""Browser upload of a Protocol Draft with a background worker (spec #375, S5; spec #342).

- ``upload_jobs``: the database queue. One row per upload: the Equipment, the draft revision
  number (assigned under a lock per Equipment, unique per Equipment), the SHA-256 of the bytes
  (the file is stored under it, never under its name), size and page count, the budget
  reserved for it, its status (``queued``, ``running``, ``succeeded``, ``failed``), the run
  it produced and who uploaded it. The status moves forward only.
- ``upload_budget``: one row, the live-spend ledger of uploads. ``reserved_usd`` is what
  queued and running jobs may still spend; ``spent_usd`` what finished jobs did spend. A
  reservation is one conditional UPDATE, so concurrent uploads never reserve past the ceiling.

The application role reads, adds and updates these two tables (a queue and a counter are
state, not records); the history of what was uploaded is the Audit Trail, written in the same
transaction.
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE upload_budget (
            id smallint PRIMARY KEY CHECK (id = 1),
            reserved_usd numeric(12, 6) NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
            spent_usd numeric(12, 6) NOT NULL DEFAULT 0 CHECK (spent_usd >= 0)
        )
    """)
    op.execute("INSERT INTO upload_budget (id) VALUES (1)")
    op.execute("""
        CREATE TABLE upload_jobs (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            equipment text NOT NULL CHECK (btrim(equipment) <> ''),
            rev integer NOT NULL CHECK (rev >= 0),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            size_bytes integer NOT NULL CHECK (size_bytes > 0),
            pages integer NOT NULL CHECK (pages > 0),
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
            reserved_usd numeric(12, 6) NOT NULL CHECK (reserved_usd >= 0),
            cost_usd numeric(12, 6) CHECK (cost_usd >= 0),
            run_id text,
            message text,
            started_at timestamptz,
            finished_at timestamptz,
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (equipment, rev)
        )
    """)
    op.execute("CREATE INDEX upload_jobs_queue ON upload_jobs (id) WHERE status = 'queued'")
    op.execute("""
        CREATE FUNCTION upload_jobs_forward_only() RETURNS trigger LANGUAGE plpgsql AS $f$
        BEGIN
            IF (OLD.status, NEW.status) NOT IN (
                ('queued', 'queued'), ('queued', 'running'), ('running', 'running'),
                ('running', 'succeeded'), ('running', 'failed'),
                ('succeeded', 'succeeded'), ('failed', 'failed')
            ) THEN
                RAISE EXCEPTION 'an upload job does not move from % to %', OLD.status, NEW.status;
            END IF;
            IF NEW.id <> OLD.id OR NEW.equipment <> OLD.equipment OR NEW.rev <> OLD.rev
               OR NEW.sha256 <> OLD.sha256 OR NEW.subject <> OLD.subject
               OR NEW.issuer <> OLD.issuer OR NEW.reserved_usd <> OLD.reserved_usd THEN
                RAISE EXCEPTION 'what an upload job holds does not change';
            END IF;
            RETURN NEW;
        END
        $f$
    """)
    op.execute("""
        CREATE TRIGGER upload_jobs_forward_only BEFORE UPDATE ON upload_jobs
        FOR EACH ROW EXECUTE FUNCTION upload_jobs_forward_only()
    """)
    op.execute("""
        CREATE TRIGGER upload_jobs_clock BEFORE INSERT ON upload_jobs
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    for table in ("upload_jobs", "upload_budget"):
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON upload_jobs TO traceq_app")
    op.execute("GRANT SELECT, UPDATE ON upload_budget TO traceq_app")


def downgrade() -> None:
    op.execute("DROP TABLE upload_jobs")
    op.execute("DROP FUNCTION upload_jobs_forward_only()")
    op.execute("DROP TABLE upload_budget")
