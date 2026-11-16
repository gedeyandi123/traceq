"""The Audit Trail, append-only, enforced in Postgres (ADR 0007 phase 1).

The application role may read and append, nothing else, and triggers refuse UPDATE, DELETE and
TRUNCATE to every role. The time of an entry is the database clock: a trigger overwrites any
value the application sends. No hash chain yet: this resists the application, not a database
administrator.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE audit_trail (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            action text NOT NULL,
            record_type text NOT NULL,
            record_id text NOT NULL,
            old_value jsonb,
            new_value jsonb,
            reason text
        )
    """)
    op.execute("""
        CREATE FUNCTION stamp_database_clock() RETURNS trigger LANGUAGE plpgsql AS $f$
        BEGIN
            NEW.at := clock_timestamp();
            RETURN NEW;
        END
        $f$
    """)
    # Shared by every append-only table (the decisions table gets the same triggers).
    op.execute("""
        CREATE FUNCTION refuse_change() RETURNS trigger LANGUAGE plpgsql AS $f$
        BEGIN
            RAISE EXCEPTION 'TraceQ: % on % is refused, the table is append-only',
                TG_OP, TG_TABLE_NAME;
        END
        $f$
    """)
    op.execute("""
        CREATE TRIGGER audit_trail_clock BEFORE INSERT ON audit_trail
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    op.execute("""
        CREATE TRIGGER audit_trail_append_only BEFORE UPDATE OR DELETE ON audit_trail
        FOR EACH ROW EXECUTE FUNCTION refuse_change()
    """)
    op.execute("""
        CREATE TRIGGER audit_trail_no_truncate BEFORE TRUNCATE ON audit_trail
        FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
    """)
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO traceq_app")
    op.execute("REVOKE ALL ON audit_trail FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON audit_trail TO traceq_app")


def downgrade() -> None:
    op.execute("DROP TABLE audit_trail")
    op.execute("DROP FUNCTION refuse_change()")
    op.execute("DROP FUNCTION stamp_database_clock()")
