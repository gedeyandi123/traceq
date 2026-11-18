"""Draft findings as Proposals (spec #196, "Proposals and decisions").

A Check Finding on the Protocol Draft of a Review Package run is a Proposal of kind ``draft``,
kept apart from the Equipment's Check Findings (kind ``check``), whose keys do not change.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute("""
        ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check
            CHECK (kind IN ('coverage', 'check', 'ai', 'draft'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute("""
        ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check
            CHECK (kind IN ('coverage', 'check', 'ai'))
    """)
