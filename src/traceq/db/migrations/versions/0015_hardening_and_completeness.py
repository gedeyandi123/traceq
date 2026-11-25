"""Hardening append-only triggers/checks and adding imported_runs.completeness (Step 6, #319).

- Adds ``stamp_imported_at()`` trigger on ``imported_runs`` so ``imported_at`` is always
  stamped by the database clock.
- Adds ``refuse_change()`` (UPDATE/DELETE) and ``no_truncate`` (TRUNCATE) triggers on
  ``imported_runs``, ``proposals``, and ``run_proposals``.
- Adds explicit ``IS NOT NULL`` CHECK constraints on ``execution_attempt_versions`` and
  ``execution_deviation_events``.
- Adds nullable ``completeness jsonb`` column to ``imported_runs``.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_HARDENED_TABLES = ("imported_runs", "proposals", "run_proposals")


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION stamp_imported_at() RETURNS trigger LANGUAGE plpgsql AS $f$
        BEGIN
            NEW.imported_at := clock_timestamp();
            RETURN NEW;
        END
        $f$
    """)
    op.execute("""
        CREATE TRIGGER imported_runs_clock BEFORE INSERT ON imported_runs
        FOR EACH ROW EXECUTE FUNCTION stamp_imported_at()
    """)
    for table in _HARDENED_TABLES:
        op.execute(f"""
            CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION refuse_change()
        """)
        op.execute(f"""
            CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
        """)
    op.execute("""
        ALTER TABLE execution_attempt_versions
        ADD CONSTRAINT execution_attempt_versions_rfc_check
        CHECK (version = 1 OR (reason_for_change IS NOT NULL AND btrim(reason_for_change) <> ''))
    """)
    op.execute("""
        ALTER TABLE execution_deviation_events
        ADD CONSTRAINT execution_deviation_events_returned_reason_check
        CHECK (event <> 'returned' OR (reason IS NOT NULL AND btrim(reason) <> ''))
    """)
    op.execute("ALTER TABLE imported_runs ADD COLUMN completeness jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE imported_runs DROP COLUMN completeness")
    op.execute(
        "ALTER TABLE execution_deviation_events "
        "DROP CONSTRAINT execution_deviation_events_returned_reason_check"
    )
    op.execute(
        "ALTER TABLE execution_attempt_versions "
        "DROP CONSTRAINT execution_attempt_versions_rfc_check"
    )
    for table in reversed(_HARDENED_TABLES):
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP TRIGGER imported_runs_clock ON imported_runs")
    op.execute("DROP FUNCTION stamp_imported_at()")
