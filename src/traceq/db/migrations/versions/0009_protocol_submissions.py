"""The frozen copy a submission stores, and its hash (spec #247, "Submission, freezing and
approval"; ADR 0012 "Freezing and approval").

A ``submitted`` event of ``protocol_events`` holds the frozen copy of the Protocol
(``frozen_copy``, one JSON document) and the SHA-256 of its canonical JSON (``copy_hash``);
no other event holds either. Adding the columns changes no row, so the append-only triggers
of ``0006`` stay as they are.
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE protocol_events
            ADD COLUMN frozen_copy jsonb,
            ADD COLUMN copy_hash text CHECK (copy_hash ~ '^[0-9a-f]{64}$'),
            ADD CONSTRAINT protocol_events_submission_copy
                CHECK ((event = 'submitted') = (frozen_copy IS NOT NULL AND copy_hash IS NOT NULL)
                    AND (frozen_copy IS NULL) = (copy_hash IS NULL))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE protocol_events
            DROP CONSTRAINT protocol_events_submission_copy,
            DROP COLUMN copy_hash,
            DROP COLUMN frozen_copy
    """)
