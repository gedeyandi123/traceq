"""Answers on the printed requirement numbers a run missed (spec #247, "Missed requirement
numbers"; ADR 0012 "Submission").

``missed_number_answers``: every version of the answer a human gave, in one Protocol, on one
printed number the run's URS completeness check missed, keyed by URS document, revision and
number and numbered 1, 2, ... per key; the latest counts. An answer is ``not_a_requirement``
or ``not_tested_here``, with a non-blank justification. Who answered is the token's subject
and issuer and the name shown at the time; when is the database clock.

The application role may read and add, nothing else, and the triggers of the Audit Trail
(``0001``) refuse UPDATE, DELETE and TRUNCATE to every role.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE missed_number_answers (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            protocol_id bigint NOT NULL REFERENCES assembled_protocols (id),
            doc text NOT NULL,
            rev integer NOT NULL,
            number text NOT NULL,
            version integer NOT NULL CHECK (version >= 1),
            kind text NOT NULL CHECK (kind IN ('not_a_requirement', 'not_tested_here')),
            justification text NOT NULL CHECK (btrim(justification) <> ''),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (protocol_id, doc, rev, number, version)
        )
    """)
    op.execute("""
        CREATE TRIGGER missed_number_answers_clock BEFORE INSERT ON missed_number_answers
        FOR EACH ROW EXECUTE FUNCTION stamp_database_clock()
    """)
    op.execute("""
        CREATE TRIGGER missed_number_answers_append_only
        BEFORE UPDATE OR DELETE ON missed_number_answers
        FOR EACH ROW EXECUTE FUNCTION refuse_change()
    """)
    op.execute("""
        CREATE TRIGGER missed_number_answers_no_truncate BEFORE TRUNCATE ON missed_number_answers
        FOR EACH STATEMENT EXECUTE FUNCTION refuse_change()
    """)
    op.execute("REVOKE ALL ON missed_number_answers FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON missed_number_answers TO traceq_app")


def downgrade() -> None:
    op.execute("DROP TABLE missed_number_answers")
