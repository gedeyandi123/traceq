"""A failed upload's revision number may be given again (spec #375, ticket #393, audit C1).

Migration 0021 made ``(equipment, rev)`` unique over every upload job. A failed job registered
no revision, yet it kept its number: in replay the retry got the next number, for which no
recording exists, and was refused. Uniqueness now holds over the jobs that did not fail
(``upload_jobs_live_rev``, a partial unique index); a failed job and its retry may share a
number. A job only moves forward (the trigger of 0021), so a failed job never comes back into
the index, and what a job holds (its ``rev`` among it) never changes.

Going down restores the unique constraint of 0021 and is refused, with nothing deleted, while
two jobs of an Equipment share a revision.
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE upload_jobs DROP CONSTRAINT upload_jobs_equipment_rev_key")
    op.execute(
        "CREATE UNIQUE INDEX upload_jobs_live_rev ON upload_jobs (equipment, rev)"
        " WHERE status <> 'failed'"
    )


def downgrade() -> None:
    op.execute("""
        DO $d$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM upload_jobs GROUP BY equipment, rev HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'upload jobs share a revision: migration 0023 does not go down'
                    ' while they do';
            END IF;
        END
        $d$
    """)
    op.execute("DROP INDEX upload_jobs_live_rev")
    op.execute(
        "ALTER TABLE upload_jobs ADD CONSTRAINT upload_jobs_equipment_rev_key"
        " UNIQUE (equipment, rev)"
    )
