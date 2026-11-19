"""Drafted Test Steps as Proposals (spec #247, "Drafted Test Steps become Proposals").

A drafted IQ/OQ Test Step of a run (``drafts.json``) is a Proposal of kind ``test_step``. An
``edited`` decision on it carries no Coverage class, so the decision table's rule "edited if
and only if a class" becomes "a class only on edited"; since the table has no kind column, the
code requires the class for a Coverage row and refuses it for a drafted Test Step. The
append-only triggers of ``0003`` stay.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute("""
        ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check
            CHECK (kind IN ('coverage', 'check', 'ai', 'draft', 'test_step'))
    """)
    # ``proposal_decisions_check`` is the name Postgres gave the unnamed
    # "(decision = 'edited') = (coverage IS NOT NULL)" of 0003.
    op.execute("ALTER TABLE proposal_decisions DROP CONSTRAINT proposal_decisions_check")
    op.execute("""
        ALTER TABLE proposal_decisions ADD CONSTRAINT proposal_decisions_class_only_on_edited
            CHECK (coverage IS NULL OR decision = 'edited')
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE proposal_decisions DROP CONSTRAINT proposal_decisions_class_only_on_edited"
    )
    op.execute("""
        ALTER TABLE proposal_decisions ADD CONSTRAINT proposal_decisions_check
            CHECK ((decision = 'edited') = (coverage IS NOT NULL))
    """)
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute("""
        ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check
            CHECK (kind IN ('coverage', 'check', 'ai', 'draft'))
    """)
