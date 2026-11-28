"""A document version names who registered it (spec #375, ticket #393, audit C5/S1).

A Protocol Draft revision that reached TraceQ by an import (``POST /runs/{id}/import``) rather
than an upload named nobody, so its importer could approve the Protocol started
from it. ``document_versions`` now records the identity of the person whose import first
registered the version (``subject``, ``issuer``, ``name``): all three or none. Rows registered
before this migration keep none (NULL); they are never filled in, since the table is
append-only (the triggers of 0016 stay as they are, and adding a column fires none of them).

Going down drops the three columns, and the identities recorded since with them.
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE document_versions
            ADD COLUMN subject text,
            ADD COLUMN issuer text,
            ADD COLUMN name text,
            ADD CONSTRAINT document_versions_registrant_whole CHECK (
                (subject IS NULL AND issuer IS NULL AND name IS NULL)
                OR (
                    subject IS NOT NULL AND issuer IS NOT NULL AND name IS NOT NULL
                    AND btrim(subject) <> '' AND btrim(issuer) <> '' AND btrim(name) <> ''
                )
            )
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE document_versions
            DROP CONSTRAINT document_versions_registrant_whole,
            DROP COLUMN name,
            DROP COLUMN issuer,
            DROP COLUMN subject
    """)
