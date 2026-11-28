"""A Protocol started from the reviewed Protocol Draft (spec #375, S4a1; ADR 0012, amended 26
November 2026).

- ``proposals.kind`` accepts ``draft_step`` and ``draft_criterion``: a Test Step the site's
  draft prints, and its Acceptance Criterion, each decided by a human.
- ``assembled_protocols`` gains the pin of its source: the draft document, revision and hash
  (null for a Protocol assembled from TraceQ's own drafted Test Steps only). The run it was
  started from is its ``run_id``. A Protocol is pinned at creation and never re-synced.
- ``protocol_draft_mappings``: every version of the requirement a human mapped one draft Test
  Step to, in one Protocol, for a step the traceability table maps to none or to several, or
  that the citation check dropped. The latest counts; who mapped it is the token's subject and
  issuer and the name shown at the time.
- ``protocol_finding_reasons``: every version of the written reason a Preparer gives, in one
  Protocol, for submitting a row on which a finding was accepted and the row is unchanged.

The application role may read and add, nothing else, and the triggers of the Audit Trail
(``0001``) refuse UPDATE, DELETE and TRUNCATE to every role.
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_TABLES = ("protocol_draft_mappings", "protocol_finding_reasons")


def upgrade() -> None:
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute("""
        ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check
            CHECK (kind IN ('coverage', 'check', 'ai', 'draft', 'test_step',
                            'draft_step', 'draft_criterion'))
    """)
    op.execute("""
        ALTER TABLE assembled_protocols
            ADD COLUMN draft_doc text,
            ADD COLUMN draft_rev integer,
            ADD COLUMN draft_sha256 text,
            ADD CONSTRAINT assembled_protocols_draft_pin_check CHECK (
                (draft_doc IS NULL) = (draft_rev IS NULL)
                AND (draft_doc IS NULL) = (draft_sha256 IS NULL)
            )
    """)
    op.execute("""
        CREATE TABLE protocol_draft_mappings (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            protocol_id bigint NOT NULL REFERENCES assembled_protocols (id),
            step text NOT NULL CHECK (btrim(step) <> ''),
            version integer NOT NULL CHECK (version >= 1),
            requirement text NOT NULL CHECK (btrim(requirement) <> ''),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (protocol_id, step, version)
        )
    """)
    op.execute("""
        CREATE TABLE protocol_finding_reasons (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at timestamptz NOT NULL DEFAULT clock_timestamp(),
            protocol_id bigint NOT NULL REFERENCES assembled_protocols (id),
            proposal_id bigint NOT NULL REFERENCES proposals (id),
            version integer NOT NULL CHECK (version >= 1),
            reason text NOT NULL CHECK (btrim(reason) <> ''),
            subject text NOT NULL,
            issuer text NOT NULL,
            name text NOT NULL,
            UNIQUE (protocol_id, proposal_id, version)
        )
    """)
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
    op.execute("DROP TABLE protocol_finding_reasons")
    op.execute("DROP TABLE protocol_draft_mappings")
    op.execute("""
        ALTER TABLE assembled_protocols
            DROP CONSTRAINT assembled_protocols_draft_pin_check,
            DROP COLUMN draft_sha256,
            DROP COLUMN draft_rev,
            DROP COLUMN draft_doc
    """)
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute("""
        ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check
            CHECK (kind IN ('coverage', 'check', 'ai', 'draft', 'test_step'))
    """)
