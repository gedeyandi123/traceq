"""Proposal Decisions, append-only like the Audit Trail (spec #105, "Proposal Decisions").

A decision belongs to a Proposal and to the content hash it was made on, and names the run on
whose screen it was made. Decisions are only added: the current one is the latest for that
Proposal and content. Who decided is stored as the token's subject and issuer and the name
shown at the time; when is the database clock.

The application role may read and add, nothing else, and the triggers of the Audit Trail
(``0001``) refuse UPDATE, DELETE and TRUNCATE to every role.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE proposal_decisions (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            proposal_id bigint NOT NULL,
            run_id text NOT NULL,
            content_hash text NOT NULL,
            decision text NOT NULL CHECK (decision IN ('accepted', 'rejected', 'edited')),
            coverage text CHECK (coverage IN
                ('covered_by_vendor', 'partial', 'site_only', 'gap', 'conflict')),
            reason text CHECK (reason IS NULL OR btrim(reason) <> ''),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            FOREIGN KEY (run_id, proposal_id) REFERENCES run_proposals (run_id, proposal_id),
            CHECK ((decision = 'edited') = (coverage IS NOT NULL)),
            CHECK (decision = 'accepted' OR reason IS NOT NULL)
        )
    """)
    op.execute("CREATE INDEX proposal_decisions_proposal ON proposal_decisions (proposal_id)")
    op.execute("""
        CREATE TRIGGER proposal_decisions_clock BEFORE INSERT ON proposal_decisions
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    op.execute("""
        CREATE TRIGGER proposal_decisions_append_only BEFORE UPDATE OR DELETE
        ON proposal_decisions FOR EACH ROW EXECUTE FUNCTION refuse_change()
    """)
    op.execute("""
        CREATE TRIGGER proposal_decisions_no_truncate BEFORE TRUNCATE ON proposal_decisions
        FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
    """)
    op.execute("REVOKE ALL ON proposal_decisions FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON proposal_decisions TO traceq_app")


def downgrade() -> None:
    op.execute("DROP TABLE proposal_decisions")
