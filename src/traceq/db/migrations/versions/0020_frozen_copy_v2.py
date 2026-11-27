"""The latest Protocol Draft revision an event of a Protocol started from the draft saw (spec
#375, S4a2; ADR 0012, amended 26 November 2026).

``protocol_events.latest_draft_rev`` is set on the ``submitted`` and ``approved`` events of a
Protocol started from the Protocol Draft: the latest revision of that draft the Equipment had
when the event was recorded, so an Approver's decision shows whether a newer revision existed.
Null for every other event. The frozen copy of such a Protocol is a version 2 copy, stored in
the same ``frozen_copy`` column (``schema_version`` 2); version 1 copies are untouched.
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE protocol_events
            ADD COLUMN latest_draft_rev integer CHECK (latest_draft_rev >= 0)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE protocol_events DROP COLUMN latest_draft_rev")
