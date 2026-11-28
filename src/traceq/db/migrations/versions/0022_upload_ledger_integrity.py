"""Tighten the upload queue and its ledger (spec #375, ticket #393, audit finding 6).

Migration 0021 is not edited; this one adds what the audit found missing:

- A finished job (``succeeded`` or ``failed``) is immutable: ``run_id``, ``cost_usd``,
  ``message`` and its times can no longer change (a trigger), and a finished job must have a
  cost and a finish time, and a ``succeeded`` one its run (a CHECK).
- ``upload_budget``: the application role may update only ``reserved_usd`` and ``spent_usd``
  (a column grant; the row's ``id`` is fixed), and ``spent_usd`` never goes down (a trigger):
  what was spent stays spent. Reserving and releasing still work as before.
- ``upload_jobs_dedupe`` serves the "already uploaded" lookup (Equipment, bytes, status).
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION upload_jobs_finished_immutable() RETURNS trigger LANGUAGE plpgsql AS $f$
        BEGIN
            IF OLD.status IN ('succeeded', 'failed') AND (
                NEW.run_id IS DISTINCT FROM OLD.run_id
                OR NEW.cost_usd IS DISTINCT FROM OLD.cost_usd
                OR NEW.message IS DISTINCT FROM OLD.message
                OR NEW.started_at IS DISTINCT FROM OLD.started_at
                OR NEW.finished_at IS DISTINCT FROM OLD.finished_at
                OR NEW.size_bytes <> OLD.size_bytes OR NEW.pages <> OLD.pages
                OR NEW.at <> OLD.at OR NEW.name <> OLD.name
            ) THEN
                RAISE EXCEPTION 'a finished upload job keeps its run, cost and message';
            END IF;
            RETURN NEW;
        END
        $f$
    """)
    op.execute("""
        CREATE TRIGGER upload_jobs_finished_immutable BEFORE UPDATE ON upload_jobs
        FOR EACH ROW EXECUTE FUNCTION upload_jobs_finished_immutable()
    """)
    op.execute("""
        ALTER TABLE upload_jobs ADD CONSTRAINT upload_jobs_finished_complete CHECK (
            (status NOT IN ('succeeded', 'failed')
                OR (cost_usd IS NOT NULL AND finished_at IS NOT NULL))
            AND (status <> 'succeeded' OR run_id IS NOT NULL)
        )
    """)
    op.execute("""
        CREATE FUNCTION upload_budget_spent_only_up() RETURNS trigger LANGUAGE plpgsql AS $f$
        BEGIN
            IF NEW.spent_usd < OLD.spent_usd THEN
                RAISE EXCEPTION 'the spent amount of the upload ledger never goes down';
            END IF;
            RETURN NEW;
        END
        $f$
    """)
    op.execute("""
        CREATE TRIGGER upload_budget_spent_only_up BEFORE UPDATE ON upload_budget
        FOR EACH ROW EXECUTE FUNCTION upload_budget_spent_only_up()
    """)
    op.execute("REVOKE UPDATE ON upload_budget FROM traceq_app")
    op.execute("GRANT UPDATE (reserved_usd, spent_usd) ON upload_budget TO traceq_app")
    op.execute("CREATE INDEX upload_jobs_dedupe ON upload_jobs (equipment, sha256, status)")


def downgrade() -> None:
    op.execute("DROP INDEX upload_jobs_dedupe")
    op.execute("REVOKE UPDATE ON upload_budget FROM traceq_app")
    op.execute("GRANT UPDATE ON upload_budget TO traceq_app")
    op.execute("DROP TRIGGER upload_budget_spent_only_up ON upload_budget")
    op.execute("DROP FUNCTION upload_budget_spent_only_up()")
    op.execute("ALTER TABLE upload_jobs DROP CONSTRAINT upload_jobs_finished_complete")
    op.execute("DROP TRIGGER upload_jobs_finished_immutable ON upload_jobs")
    op.execute("DROP FUNCTION upload_jobs_finished_immutable()")
