"""Written Test Steps of a Protocol assembled in TraceQ (spec #247, "Written Test Steps").

``written_test_steps``: every version of the Test Step a human wrote for one requirement of
one Protocol, numbered 1, 2, ... per Protocol and requirement. A version holds the full
content (description, method, instrument, Acceptance Criterion) or is a removal, which takes
the written Test Step back; ``from_proposal_id`` names the drafted Test Step it was edited from
and ``decision_id`` the ``edited`` decision recorded with it, both only for a version made by
the edit route. Who wrote it is the token's subject and issuer and the name shown at the time;
when is the database clock.

The application role may read and add, nothing else, and the triggers of the Audit Trail
(``0001``) refuse UPDATE, DELETE and TRUNCATE to every role.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE written_test_steps (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            protocol_id bigint NOT NULL REFERENCES assembled_protocols (id),
            requirement text NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            removed boolean NOT NULL,
            description text,
            method text,
            instrument text,
            acceptance jsonb,
            from_proposal_id bigint REFERENCES proposals (id),
            decision_id bigint REFERENCES proposal_decisions (id),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (protocol_id, requirement, version),
            CHECK (removed = (description IS NULL)),
            CHECK (removed = (method IS NULL)),
            CHECK (removed = (acceptance IS NULL)),
            CHECK (NOT removed OR (instrument IS NULL AND from_proposal_id IS NULL)),
            CHECK ((from_proposal_id IS NULL) = (decision_id IS NULL))
        )
    """)
    op.execute("""
        CREATE TRIGGER written_test_steps_clock BEFORE INSERT ON written_test_steps
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    op.execute("""
        CREATE TRIGGER written_test_steps_append_only BEFORE UPDATE OR DELETE ON written_test_steps
        FOR EACH ROW EXECUTE FUNCTION refuse_change()
    """)
    op.execute("""
        CREATE TRIGGER written_test_steps_no_truncate BEFORE TRUNCATE ON written_test_steps
        FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
    """)
    op.execute("REVOKE ALL ON written_test_steps FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON written_test_steps TO traceq_app")


def downgrade() -> None:
    op.execute("DROP TABLE written_test_steps")
