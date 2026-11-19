"""The rows of a Protocol in Draft status, computed live, not stored (spec #247, "The Protocol
and its rows"; ADR 0012 "Rows").

One row per requirement of the run, in requirement order, from the run's Coverage Proposals
and its drafted Test Steps (``test_step`` Proposals) and where each stands. A row's kind:

- Coverage not decided on the run's content (``undecided``, or ``changed`` since it was
  decided: a decision on other content is not a human decision on this one): the kind is
  unknown and the row blocks.
- Decided ``covered_by_vendor`` (accepted as proposed or edited to it) with no accepted draft:
  a **Vendor Reference**, naming the row's Evidence steps.
- Otherwise a **Test Step** row: its Test Step is the accepted draft; without one it blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from traceq.proposals.decisions import Standing, standings
from traceq.proposals.store import RUN_PROPOSALS
from traceq.runs.schemas import DraftedTestStep, MatrixRow
from traceq.traceability.coverage import CoverageClass

type RowKind = Literal["undecided", "vendor_reference", "test_step"]
type Blocker = Literal["coverage_undecided", "no_test_step"]
"""``coverage_undecided``: Coverage not decided by a human on the run's content.
``no_test_step``: a Test Step row with no Test Step."""


@dataclass(frozen=True)
class DraftOfRow:
    """A drafted Test Step of the row's requirement and where its Proposal stands."""

    draft: DraftedTestStep
    standing: Standing

    @property
    def accepted(self) -> bool:
        s = self.standing
        return s.state == "decided" and s.decisions[0].decision == "accepted"


@dataclass(frozen=True)
class ProtocolRow:
    requirement: MatrixRow
    """The requirement as the run proposed it: text, URS citation, Evidence."""
    coverage: Standing
    decided_class: CoverageClass | None
    """The class a human decided on the run's content; ``None`` while undecided or changed."""
    kind: RowKind
    drafts: tuple[DraftOfRow, ...]
    test_step: DraftOfRow | None
    """For a Test Step row: the accepted draft, if any."""
    blockers: tuple[Blocker, ...]


def _decided_class(s: Standing, proposed: dict[str, Any]) -> CoverageClass | None:
    if s.state != "decided":
        return None
    current = s.decisions[0]
    return current.coverage if current.decision == "edited" else proposed.get("coverage")


def rows_of(session: Session, run_id: str) -> list[ProtocolRow]:
    """The rows of a Protocol started from an imported run, in requirement order."""
    stood = standings(session, run_id) or []
    proposed: dict[int, dict[str, Any]] = {
        r.proposal_id: r.proposed
        for r in session.execute(
            select(RUN_PROPOSALS.c.proposal_id, RUN_PROPOSALS.c.proposed).where(
                RUN_PROPOSALS.c.run_id == run_id
            )
        )
    }
    drafts: dict[str, list[DraftOfRow]] = {}
    for s in stood:
        if s.kind == "test_step" and s.requirement is not None:
            draft = DraftedTestStep.model_validate(proposed[s.proposal_id])
            drafts.setdefault(s.requirement, []).append(DraftOfRow(draft, s))
    out: list[ProtocolRow] = []
    for s in stood:
        if s.kind != "coverage" or s.requirement is None:
            continue
        row = MatrixRow.model_validate(proposed[s.proposal_id])
        decided = _decided_class(s, proposed[s.proposal_id])
        mine = tuple(drafts.get(s.requirement, ()))
        accepted = next((d for d in mine if d.accepted), None)
        kind: RowKind
        blockers: tuple[Blocker, ...]
        if decided is None:
            kind, accepted = "undecided", None
            blockers = ("coverage_undecided",)
        elif decided == "covered_by_vendor" and accepted is None:
            kind, blockers = "vendor_reference", ()
        else:
            kind = "test_step"
            blockers = () if accepted is not None else ("no_test_step",)
        out.append(
            ProtocolRow(
                requirement=row,
                coverage=s,
                decided_class=decided,
                kind=kind,
                drafts=mine,
                test_step=accepted,
                blockers=blockers,
            )
        )
    return out
