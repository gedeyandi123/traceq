"""The rows of a Protocol in Draft status, computed live, not stored (spec #247, "The Protocol
and its rows"; ADR 0012 "Rows").

One row per requirement of the run, in requirement order, from the run's Coverage Proposals
and its drafted Test Steps (``test_step`` Proposals) and where each stands. A row's kind:

- Coverage not decided on the run's content (``undecided``, or ``changed`` since it was
  decided: a decision on other content is not a human decision on this one): the kind is
  unknown and the row blocks.
- Decided ``covered_by_vendor`` (accepted as proposed or edited to it) with no accepted draft
  and no written Test Step: a **Vendor Reference**, naming the row's Evidence steps.
- Otherwise a **Test Step** row: its Test Step is the written one if any, else the accepted
  draft; without one it blocks.

Each row also says what its write form starts from (``prefill``): the written Test Step in
force, else the latest version of it in the most recent withdrawn Protocol of the Equipment,
else the first drafted Test Step (its Acceptance Criterion only when in one of the four shapes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from traceq.assembly import written
from traceq.assembly.lifecycle import AssembledProtocol
from traceq.assembly.written import Acceptance, WrittenContent, WrittenVersion
from traceq.proposals.decisions import Standing, standings
from traceq.proposals.store import RUN_PROPOSALS
from traceq.runs.schemas import DraftedTestStep, MatrixRow
from traceq.traceability.coverage import CoverageClass
from traceq.traceability.values import Text

type PrefillOrigin = Literal["written", "withdrawn", "draft"]

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
class Prefill:
    """What the row's write form starts from, and where it came from."""

    origin: PrefillOrigin
    description: str
    method: str
    instrument: str | None
    acceptance: Acceptance | None
    """``None`` when the source has none in one of the four shapes: the human sets it."""


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
    """For a Test Step row without a written Test Step: the accepted draft, if any."""
    written: tuple[WrittenVersion, ...]
    """Every version of the row's written Test Step in this Protocol, oldest first."""
    written_step: WrittenVersion | None
    """For a Test Step row: the written Test Step in force, if any."""
    prefill: Prefill | None
    blockers: tuple[Blocker, ...]


def _decided_class(s: Standing, proposed: dict[str, Any]) -> CoverageClass | None:
    if s.state != "decided":
        return None
    current = s.decisions[0]
    return current.coverage if current.decision == "edited" else proposed.get("coverage")


def _from_content(origin: PrefillOrigin, c: WrittenContent) -> Prefill:
    return Prefill(origin, c.description, c.method, c.instrument, c.acceptance)


def _from_draft(d: DraftedTestStep) -> Prefill:
    a = d.acceptance
    return Prefill(
        "draft", d.description, d.method, d.instrument, None if isinstance(a, Text) else a
    )


def _prefill(
    in_force: WrittenVersion | None,
    carried: WrittenContent | None,
    drafts: tuple[DraftOfRow, ...],
) -> Prefill | None:
    if in_force is not None and in_force.content is not None:
        return _from_content("written", in_force.content)
    if carried is not None:
        return _from_content("withdrawn", carried)
    return _from_draft(drafts[0].draft) if drafts else None


def rows_of(session: Session, protocol: AssembledProtocol) -> list[ProtocolRow]:
    """The rows of a Protocol in Draft status, from its run, in requirement order."""
    run_id = protocol.run_id
    versions = written.versions_of(session, protocol.id)
    carried = written.carried_over(session, protocol)
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
        history = versions.get(s.requirement, ())
        in_force = written.current(history)
        if in_force is not None:
            accepted = None
        kind: RowKind
        blockers: tuple[Blocker, ...]
        if decided is None:
            kind, accepted, step = "undecided", None, None
            blockers = ("coverage_undecided",)
        elif decided == "covered_by_vendor" and accepted is None and in_force is None:
            kind, blockers, step = "vendor_reference", (), None
        else:
            kind, step = "test_step", in_force
            blockers = () if accepted is not None or step is not None else ("no_test_step",)
        out.append(
            ProtocolRow(
                requirement=row,
                coverage=s,
                decided_class=decided,
                kind=kind,
                drafts=mine,
                test_step=accepted,
                written=history,
                written_step=step,
                prefill=_prefill(in_force, carried.get(s.requirement), mine),
                blockers=blockers,
            )
        )
    return out
