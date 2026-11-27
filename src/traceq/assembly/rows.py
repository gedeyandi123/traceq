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
  draft; without one it blocks. It also blocks while one of its drafted Test Steps is not
  decided on the run's content, and while its Test Step is an accepted draft whose Acceptance
  Criterion is missing or free text (spec #247, "Submission checks").

Each row also says what its write form starts from (``prefill``): the written Test Step in
force, else the latest version of it in the most recent withdrawn Protocol of the Equipment,
else the first drafted Test Step (its Acceptance Criterion only when in an Acceptance shape).

A Protocol started from the site's Protocol Draft (spec #375, S4a1; ADR 0012, amended 26
November 2026) adds, per row:

- **Source.** A requirement the draft covers, that is, one a draft Test Step is mapped to (by
  the traceability table when to exactly one, else by a human), takes its Test Step from the
  draft: TraceQ's own drafted Test Steps are not offered for it. Any other requirement takes
  TraceQ's own drafted or written one. ``ProtocolRow.source`` says which.
- **Draft rows.** The draft Test Step and its Acceptance Criterion are two Proposals a human
  decides; an edit types both. An ``edited`` decision made in another Protocol never decides
  the step here: only a written Test Step of this Protocol does.
- **Findings.** A finding of the draft about the row that is not decided blocks; an accepted
  one on a row whose Test Step is not written in this Protocol needs a written reason.
- **Stage.** A Test Step row needs its Stage (IQ or OQ).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeGuard

from sqlalchemy import select
from sqlalchemy.orm import Session

from traceq.assembly import attributes, draft_source, written
from traceq.assembly.attributes import Stage, StepAttribute
from traceq.assembly.draft_source import Mapping, Reason
from traceq.assembly.lifecycle import AssembledProtocol
from traceq.assembly.written import Acceptance, WrittenContent, WrittenVersion
from traceq.proposals.decisions import Decision, Standing, standings
from traceq.proposals.store import RUN_PROPOSALS
from traceq.review.printed import Limit
from traceq.review.printed import Tolerance as PrintedTolerance
from traceq.runs.schemas import (
    DraftCheckFinding,
    DraftCriterionProposal,
    DraftedTestStep,
    DraftStepProposal,
    MatrixRow,
    PrintedRead,
)
from traceq.traceability.coverage import CoverageClass
from traceq.traceability.values import (
    ExclusiveRange,
    Number,
    Range,
    Text,
    ToleranceBand,
    Value,
    tolerance_judgeable,
)

type PrefillOrigin = Literal["written", "withdrawn", "draft"]

type RowKind = Literal["undecided", "vendor_reference", "test_step"]
type RowSource = Literal["draft", "traceq_drafted", "traceq_written"]
"""Where a row's Test Step comes from: the site's Protocol Draft, a Test Step TraceQ drafted
(accepted or edited), or one a human wrote."""
type Blocker = Literal[
    "coverage_undecided",
    "draft_undecided",
    "no_test_step",
    "acceptance_not_shaped",
    "finding_undecided",
    "finding_reason_missing",
    "stage_missing",
]
"""``coverage_undecided``: Coverage not decided by a human on the run's content.
``draft_undecided``: a drafted Test Step of a Test Step row not decided on the run's content
(for a draft Test Step: the step, or its Acceptance Criterion once the step is accepted).
``no_test_step``: a Test Step row with no Test Step. ``acceptance_not_shaped``: its Test Step
is an accepted draft whose Acceptance Criterion is missing, free text or not exactly one of the
four shapes, so Execution could not judge it by code (ADR 0002). The last three apply to a
Protocol started from the Protocol Draft: ``finding_undecided``: a finding about the row is not
decided; ``finding_reason_missing``: a finding about the row is accepted and the row is
unchanged, without a written reason; ``stage_missing``: a Test Step row without its Stage."""


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
    """``None`` when the source has none in an Acceptance shape: the human sets it."""


@dataclass(frozen=True)
class DraftCandidate:
    """A Test Step of the site's Protocol Draft that stands for the row's requirement, with its
    Acceptance Criterion and where each stands (Protocol started from the draft)."""

    step: DraftStepProposal
    standing: Standing
    criterion: DraftCriterionProposal | None
    """``None`` when the draft's reading of the step holds no Acceptance Criterion."""
    criterion_standing: Standing | None
    mapping: Mapping | None
    """The human mapping in force, for a step the traceability table maps to none or several
    requirements; ``None`` when the table maps it to exactly one."""
    edited_here: bool
    """An ``edited`` decision on the step was made with a written Test Step of this
    Protocol."""

    def _current(self, d: Decision) -> Decision | None:
        """A decision binds to the requirement mapping too (ADR 0012, "Binding to content"):
        one made before the human mapping in force (a remap, or the mapping of another
        Protocol) decides nothing here."""
        return d if self.mapping is None or d.at > self.mapping.at else None

    @property
    def step_decision(self) -> Decision | None:
        s = self.standing
        return self._current(s.decisions[0]) if s.state == "decided" else None

    @property
    def criterion_decision(self) -> Decision | None:
        s = self.criterion_standing
        if s is None or s.state != "decided":
            return None
        return self._current(s.decisions[0])

    @property
    def decided_here(self) -> bool:
        """The step is decided in this Protocol: accepted or rejected on its content, or edited
        with a written Test Step here. An edit made in another Protocol does not count."""
        d = self.step_decision
        return d is not None and (d.decision != "edited" or self.edited_here)

    @property
    def ready(self) -> bool:
        """Nothing is left to decide: the step, and its criterion once the step is accepted."""
        d = self.step_decision
        if not self.decided_here or d is None:
            return False
        return d.decision != "accepted" or self.criterion_decision is not None

    @property
    def accepted(self) -> bool:
        """Accepted as read, with its criterion accepted, and holding a description and a
        method: usable as the row's Test Step."""
        d, c = self.step_decision, self.criterion_decision
        return (
            d is not None
            and d.decision == "accepted"
            and c is not None
            and c.decision == "accepted"
            and bool((self.step.description or "").strip())
            and bool((self.step.method or "").strip())
        )


@dataclass(frozen=True)
class DraftStepListing:
    """A Test Step of the pinned Protocol Draft, whether or not it became a row's candidate."""

    step: DraftStepProposal
    standing: Standing
    mappings: tuple[Mapping, ...]
    """Every human mapping of it in this Protocol, oldest first."""
    requirement: str | None
    """The requirement it stands for here; ``None``: listed and unusable until a human maps it
    to exactly one (or rejects it)."""

    @property
    def resolved(self) -> bool:
        """It stands for a requirement, or a human rejected it."""
        s = self.standing
        return self.requirement is not None or (
            s.state == "decided" and s.decisions[0].decision == "rejected"
        )


@dataclass(frozen=True)
class RowFinding:
    """A finding of the Protocol Draft about the row's requirement and where it stands."""

    standing: Standing
    finding: DraftCheckFinding
    reasons: tuple[Reason, ...]
    """Every written reason for it in this Protocol, oldest first; the latest counts."""

    @property
    def accepted(self) -> bool:
        s = self.standing
        return s.state == "decided" and s.decisions[0].decision == "accepted"

    @property
    def reason_current(self) -> bool:
        """A reason was written after the decision in force: one written for an earlier
        acceptance (since rejected, or on content that changed) does not count."""
        s = self.standing
        return (
            s.state == "decided" and bool(self.reasons) and self.reasons[-1].at > s.decisions[0].at
        )


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
    step_attributes: tuple[StepAttribute, ...] = ()
    candidates: tuple[DraftCandidate, ...] = ()
    """The draft Test Steps that stand for the requirement: for a row the draft covers, its Test
    Step comes from these and ``drafts`` is empty."""
    accepted_candidate: DraftCandidate | None = None
    """For a Test Step row without a written Test Step: the accepted draft Test Step, if any."""
    findings: tuple[RowFinding, ...] = ()
    """Findings of the Protocol Draft about the requirement (a Protocol started from it)."""

    @property
    def source(self) -> RowSource | None:
        """Where the row's Test Step comes from; ``None`` while it has none."""
        step = step_of(self)
        return None if step is None else step.source

    @property
    def changed(self) -> bool:
        """The row's Test Step is one a human wrote or edited in this Protocol."""
        return self.written_step is not None


@dataclass(frozen=True)
class RowStep:
    """The one Test Step of a Test Step row, wherever it came from: what the page shows and
    what the frozen copy holds."""

    origin: Literal["accepted_draft", "written"]
    proposal_id: int | None
    """For an accepted draft: its Proposal. For a written one: the draft it was edited from,
    ``None`` when written without one."""
    version: int | None
    """For a written Test Step: the version in force."""
    decision: Decision | None
    """For an accepted draft: the ``accepted`` decision in force. For a written one edited from
    a draft: the ``edited`` decision recorded with it; ``None`` when written without one."""
    description: str
    method: str
    instrument: str | None
    acceptance: Value | Acceptance | None
    acceptance_flag: str | None
    stage: Stage | None = None
    witness_required: bool = False
    source: RowSource = "traceq_drafted"


def _edited(r: ProtocolRow, v: WrittenVersion) -> Decision | None:
    """The ``edited`` decision recorded with the version, among the row's drafts' decisions."""
    if v.decision_id is None:
        return None
    standings_ = [d.standing for d in r.drafts] + [c.standing for c in r.candidates]
    for s in standings_:
        for x in s.decisions:
            if x.id == v.decision_id:
                return x
    raise LookupError(
        f"the edited decision {v.decision_id} of {r.requirement.id} version {v.version} is not"
        " among its drafts' decisions"
    )


def exact_acceptance(value: PrintedRead | None) -> Acceptance | None:
    """The Acceptance Criterion a draft prints, as a shape Execution judges exactly, or
    ``None``: a limit or range (a strict bound is an exclusive range, never an inclusive one),
    a tolerance in percent or in the nominal's unit, or a number. A tolerance in another unit,
    text or a form code did not read is not shaped (spec #375, S4a3)."""
    if isinstance(value, Limit):
        if value.min_exclusive or value.max_exclusive:
            return ExclusiveRange(
                min=value.min,
                max=value.max,
                min_exclusive=value.min_exclusive,
                max_exclusive=value.max_exclusive,
                unit=value.unit,
            )
        return Range(min=value.min, max=value.max, unit=value.unit)
    if isinstance(value, PrintedTolerance):
        if not tolerance_judgeable(value.tolerance_unit, value.unit):
            return None
        return ToleranceBand(
            nominal=value.nominal,
            tolerance=value.tolerance,
            tolerance_unit=value.tolerance_unit.strip(),
            unit=value.unit,
        )
    if isinstance(value, Range | Number):
        return value
    return None


def _candidate_source(r: ProtocolRow, v: WrittenVersion) -> RowSource:
    """Where a written Test Step comes from: the draft step it was edited from, a Test Step
    TraceQ drafted, or nothing but a person."""
    if v.from_proposal_id is None:
        return "traceq_written"
    if any(c.standing.proposal_id == v.from_proposal_id for c in r.candidates):
        return "draft"
    return "traceq_drafted"


def step_of(r: ProtocolRow) -> RowStep | None:
    """The row's one Test Step: the written one in force, else the accepted draft."""
    stage, witness_required = attributes.current(r.step_attributes)
    v = r.written_step
    if v is not None:
        c = v.content
        if c is None:
            raise ValueError(f"the written Test Step in force of {r.requirement.id} is a removal")
        return RowStep(
            origin="written",
            proposal_id=v.from_proposal_id,
            version=v.version,
            decision=_edited(r, v),
            description=c.description,
            method=c.method,
            instrument=c.instrument,
            acceptance=c.acceptance,
            acceptance_flag=None,
            stage=stage,
            witness_required=witness_required,
            source=_candidate_source(r, v),
        )
    if r.accepted_candidate is not None:
        a = r.accepted_candidate
        exact = exact_acceptance(None if a.criterion is None else a.criterion.value)
        return RowStep(
            origin="accepted_draft",
            proposal_id=a.standing.proposal_id,
            version=None,
            decision=a.step_decision,
            description=a.step.description or "",
            method=a.step.method or "",
            instrument=a.step.instrument or None,
            acceptance=exact,
            acceptance_flag=None
            if exact is not None
            else "the printed criterion is not in a shape Execution judges exactly: edit it",
            stage=stage,
            witness_required=witness_required,
            source="draft",
        )
    if r.test_step is None:
        return None
    d = r.test_step.draft
    return RowStep(
        origin="accepted_draft",
        proposal_id=r.test_step.standing.proposal_id,
        version=None,
        decision=r.test_step.standing.decisions[0],
        description=d.description,
        method=d.method,
        instrument=d.instrument,
        acceptance=d.acceptance,
        acceptance_flag=d.acceptance_flag,
        stage=stage,
        witness_required=witness_required,
    )


def _decided_class(s: Standing, proposed: dict[str, Any]) -> CoverageClass | None:
    if s.state != "decided":
        return None
    current = s.decisions[0]
    return current.coverage if current.decision == "edited" else proposed.get("coverage")


def _from_content(origin: PrefillOrigin, c: WrittenContent) -> Prefill:
    return Prefill(origin, c.description, c.method, c.instrument, c.acceptance)


def _from_draft(d: DraftedTestStep) -> Prefill:
    a = d.acceptance
    return Prefill("draft", d.description, d.method, d.instrument, a if shaped(a) else None)


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


def _test_step_blockers(
    drafts: tuple[DraftOfRow, ...],
    accepted: DraftOfRow | None,
    step: WrittenVersion | None,
    candidates: tuple[DraftCandidate, ...] = (),
    accepted_candidate: DraftCandidate | None = None,
) -> tuple[Blocker, ...]:
    out: list[Blocker] = []
    if any(d.standing.state != "decided" for d in drafts) or any(not c.ready for c in candidates):
        out.append("draft_undecided")
    if accepted is None and accepted_candidate is None and step is None:
        out.append("no_test_step")
    if step is None and accepted is not None and not shaped(accepted.draft.acceptance):
        out.append("acceptance_not_shaped")
    if step is None and accepted_candidate is not None:
        c = accepted_candidate.criterion
        if exact_acceptance(None if c is None else c.value) is None:
            out.append("acceptance_not_shaped")
    return tuple(out)


def shaped(acceptance: Value | Acceptance | None) -> TypeGuard[Acceptance]:
    """An Acceptance Criterion in one of the shapes: range, exclusive range, tolerance, number,
    one of, present.

    A range, exclusive or not, whose lower bound is above its upper bound is no shape (as a
    written Test Step's)."""
    if acceptance is None or isinstance(acceptance, Text):
        return False
    return not (
        isinstance(acceptance, Range | ExclusiveRange)
        and acceptance.min is not None
        and acceptance.max is not None
        and acceptance.min > acceptance.max
    )


def proposed_of(session: Session, run_id: str) -> dict[int, dict[str, Any]]:
    return {
        r.proposal_id: r.proposed
        for r in session.execute(
            select(RUN_PROPOSALS.c.proposal_id, RUN_PROPOSALS.c.proposed).where(
                RUN_PROPOSALS.c.run_id == run_id
            )
        )
    }


def draft_listing(
    session: Session,
    protocol: AssembledProtocol,
    stood: list[Standing] | None = None,
    proposed: dict[int, dict[str, Any]] | None = None,
    versions: dict[str, tuple[WrittenVersion, ...]] | None = None,
) -> tuple[list[DraftStepListing], dict[str, list[DraftCandidate]]]:
    """Every Test Step of the Protocol's pinned Protocol Draft in draft order, and per
    requirement the ones that stand for it (empty for a Protocol not started from the draft)."""
    if protocol.draft is None:
        return [], {}
    stood = standings(session, protocol.run_id) or [] if stood is None else stood
    proposed = proposed_of(session, protocol.run_id) if proposed is None else proposed
    versions = written.versions_of(session, protocol.id) if versions is None else versions
    mappings = draft_source.mappings_of(session, protocol.id)
    edits = {
        v.decision_id for history in versions.values() for v in history if v.decision_id is not None
    }
    criteria: dict[str, tuple[Standing, DraftCriterionProposal]] = {}
    for s in stood:
        if s.kind == "draft_criterion":
            c = DraftCriterionProposal.model_validate(proposed[s.proposal_id])
            criteria.setdefault(c.id, (s, c))
    listing: list[DraftStepListing] = []
    candidates: dict[str, list[DraftCandidate]] = {}
    for s in stood:
        if s.kind != "draft_step":
            continue
        step = DraftStepProposal.model_validate(proposed[s.proposal_id])
        human = mappings.get(step.id, ())
        requirement = draft_source.effective_requirement(step.mapped_to, human)
        listing.append(DraftStepListing(step, s, human, requirement))
        if requirement is None:
            continue
        crit = criteria.get(step.id)
        candidates.setdefault(requirement, []).append(
            DraftCandidate(
                step=step,
                standing=s,
                criterion=None if crit is None else crit[1],
                criterion_standing=None if crit is None else crit[0],
                mapping=human[-1] if human and len(step.mapped_to) != 1 else None,
                edited_here=s.state == "decided" and s.decisions[0].id in edits,
            )
        )
    return listing, candidates


def unresolved_steps(session: Session, protocol: AssembledProtocol) -> list[str]:
    """The ids of the Test Steps of the pinned draft that stand for no requirement and that no
    human rejected: listed on the Protocol and holding its submission back."""
    listing, _ = draft_listing(session, protocol)
    return [e.step.id for e in listing if not e.resolved]


def _findings_by_requirement(
    session: Session,
    protocol: AssembledProtocol,
    stood: list[Standing],
    proposed: dict[int, dict[str, Any]],
) -> dict[str, list[RowFinding]]:
    if protocol.draft is None:
        return {}
    reasons = draft_source.reasons_of(session, protocol.id)
    out: dict[str, list[RowFinding]] = {}
    for s in stood:
        if s.kind != "draft":
            continue
        finding = DraftCheckFinding.model_validate(proposed[s.proposal_id])
        out.setdefault(finding.requirement, []).append(
            RowFinding(s, finding, reasons.get(s.proposal_id, ()))
        )
    return out


def _same_as_drafted(content: WrittenContent, candidates: tuple[DraftCandidate, ...]) -> bool:
    """The written Test Step holds what a draft Test Step of the row has, to the letter (blanks
    around the text aside): description, method, instrument and Acceptance Criterion. Saving
    the form as it started changes nothing."""
    for c in candidates:
        start = _from_candidate(c)
        if (
            content.description.strip() == start.description.strip()
            and content.method.strip() == start.method.strip()
            and (content.instrument or None) == (start.instrument or None)
            and content.acceptance == start.acceptance
        ):
            return True
    return False


def _changed_from_draft(
    in_force: WrittenVersion | None, candidates: tuple[DraftCandidate, ...]
) -> bool:
    """A human wrote a Test Step that differs from the draft's (ADR 0012, "Findings": a
    finding accepted on a row whose Test Step is unchanged needs a written reason). Saving a
    Test Step unchanged does not count."""
    if in_force is None or in_force.content is None:
        return False
    return not _same_as_drafted(in_force.content, candidates)


def _finding_blockers(findings: tuple[RowFinding, ...], changed: bool) -> tuple[Blocker, ...]:
    out: list[Blocker] = []
    if any(f.standing.state != "decided" for f in findings):
        out.append("finding_undecided")
    if not changed and any(f.accepted and not f.reason_current for f in findings):
        out.append("finding_reason_missing")
    return tuple(out)


def rows_of(session: Session, protocol: AssembledProtocol) -> list[ProtocolRow]:
    """The rows of a Protocol in Draft status, from its run, in requirement order."""
    run_id = protocol.run_id
    versions = written.versions_of(session, protocol.id)
    attrs = attributes.attributes_of(session, protocol.id)
    carried = written.carried_over(session, protocol)
    stood = standings(session, run_id) or []
    proposed = proposed_of(session, run_id)
    from_draft = protocol.draft is not None
    _, covering = draft_listing(session, protocol, stood, proposed, versions)
    found = _findings_by_requirement(session, protocol, stood, proposed)
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
        candidates = tuple(covering.get(s.requirement, ()))
        # A requirement the draft covers takes its Test Step from the draft, never from
        # TraceQ's own drafts: a row holds one source.
        mine = () if candidates else tuple(drafts.get(s.requirement, ()))
        accepted = next((d for d in mine if d.accepted), None)
        accepted_candidate = next((c for c in candidates if c.accepted), None)
        history = versions.get(s.requirement, ())
        in_force = written.current(history)
        if in_force is not None:
            accepted = accepted_candidate = None
        kind: RowKind
        blockers: tuple[Blocker, ...]
        if decided is None:
            kind, accepted, accepted_candidate, step = "undecided", None, None, None
            blockers = ("coverage_undecided",)
        elif (
            decided == "covered_by_vendor"
            and accepted is None
            and accepted_candidate is None
            and in_force is None
        ):
            kind, blockers, step = "vendor_reference", (), None
        else:
            kind, step = "test_step", in_force
            blockers = _test_step_blockers(mine, accepted, step, candidates, accepted_candidate)
        row_attrs = attrs.get(s.requirement, ()) if kind == "test_step" else ()
        findings = tuple(found.get(s.requirement, ()))
        if from_draft:
            blockers = (
                *blockers,
                *_finding_blockers(findings, _changed_from_draft(in_force, candidates)),
            )
            has_step = accepted is not None or accepted_candidate is not None or step is not None
            if kind == "test_step" and has_step and attributes.current(row_attrs)[0] is None:
                blockers = (*blockers, "stage_missing")
        prefill = (
            _from_candidate(candidates[0])
            if candidates and in_force is None and s.requirement not in carried
            else _prefill(in_force, carried.get(s.requirement), mine)
        )
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
                prefill=prefill,
                blockers=blockers,
                step_attributes=row_attrs,
                candidates=candidates,
                accepted_candidate=accepted_candidate,
                findings=findings,
            )
        )
    return out


def _from_candidate(c: DraftCandidate) -> Prefill:
    exact = exact_acceptance(None if c.criterion is None else c.criterion.value)
    return Prefill(
        "draft",
        c.step.description or "",
        c.step.method or "",
        c.step.instrument or None,
        exact if shaped(exact) else None,
    )
