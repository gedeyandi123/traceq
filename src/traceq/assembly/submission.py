"""Submitting a Protocol: the checks that block it, its frozen copy and the copy's hash (spec
#247, "Submission, freezing and approval"; ADR 0012 "Freezing and approval").

Five checks block submission, each with the rows or numbers it concerns: Coverage not decided
by a human on the run's content; a drafted Test Step of a Test Step row not decided; a Test
Step row without its one Test Step; a Test Step whose Acceptance Criterion is missing or free
text; a printed requirement number the run missed without its disposition. When none blocks,
a person with the deciding role submits and becomes the **Preparer**.

The copy is one JSON document of everything the Protocol rests on: every row, with the
decision in force on its Coverage and on each of its drafted Test Steps (rejections too) and
who made it, its Test Step with the decision it came from and every version of its written one
with its author; the missed numbers with every version of their dispositions in this Protocol
and the one in force; the unquoted text. Its hash is the SHA-256 of its canonical
JSON, the canonicalisation of Proposal hashes. The ``submitted`` event stores both, so a
decision recorded later (decisions are shared across runs) never changes what the Approver
reads. A Protocol started from the Protocol Draft (spec #375, S4a2) is frozen as a **version 2**
copy (``schema_version`` 2), which also records the draft it was pinned to, the source of each
row, every finding with its decisions and reasons, and every draft Test Step with its mapping
and decisions. Every decision of a version 2 copy also records its ``provenance``: the run it was
made on, the content hash it was made on and the revision of the Protocol Draft that run read,
so the Approver can tell a decision made on revision 0 and carried to revision 2 from one made
on revision 2 (decisions are shared across runs and draft revisions). A decision of a version 1
copy has no ``provenance`` and dumps without the key, so a stored version 1 copy keeps its hash
byte for byte, and its hash is never recomputed from a version 2 model. Submitting takes the
per-Protocol lock and checks the status inside it, and has its Audit Trail entry in the same
transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import draft_source, lifecycle
from traceq.assembly.attributes import Stage, StepAttribute
from traceq.assembly.lifecycle import EVENTS, Conflict
from traceq.assembly.missed import (
    Disposition,
    Key,
    MissedKind,
    MissedNumber,
    UrsMissed,
    missed_of,
)
from traceq.assembly.rows import (
    DraftCandidate,
    ProtocolRow,
    RowSource,
    draft_listing,
    proposed_of,
    rows_of,
    shaped,
    step_of,
    unresolved_steps,
)
from traceq.assembly.written import Acceptance, WrittenContent, WrittenVersion
from traceq.proposals.decisions import Decision, Standing, Verdict, standings
from traceq.proposals.keys import digest
from traceq.proposals.store import RUNS
from traceq.review.draft_rules import DraftType
from traceq.runs.schemas import (
    Cite,
    Completeness,
    DraftCheckFinding,
    DraftCriterionProposal,
    EvidenceStep,
    UnquotedText,
)
from traceq.traceability.coverage import CoverageClass

type Check = Literal[
    "coverage_undecided",
    "draft_undecided",
    "no_test_step",
    "acceptance_not_shaped",
    "missed_undecided",
    "finding_undecided",
    "finding_reason_missing",
    "stage_missing",
    "draft_step_unresolved",
]
"""The submission checks, in the order the page lists them. The first four are row blockers;
``missed_undecided``: a printed number the run missed, without its disposition. The last four
apply to a Protocol started from the Protocol Draft only (ADR 0012, amended 26 November
2026): ``finding_undecided``, ``finding_reason_missing`` and ``stage_missing`` are row
blockers; ``draft_step_unresolved``: a Test Step of the pinned draft that maps to no
requirement or to several, or that the citation check dropped, that no human mapped or
rejected."""

CHECKS: tuple[Check, ...] = (
    "coverage_undecided",
    "draft_undecided",
    "no_test_step",
    "acceptance_not_shaped",
    "missed_undecided",
)
DRAFT_CHECKS: tuple[Check, ...] = (
    "finding_undecided",
    "finding_reason_missing",
    "stage_missing",
    "draft_step_unresolved",
)


@dataclass(frozen=True)
class Blocking:
    """One submission check: the rows, the missed numbers and the draft Test Steps it holds
    back."""

    check: Check
    requirements: tuple[str, ...]
    numbers: tuple[Key, ...]
    steps: tuple[str, ...] = ()
    """For ``draft_step_unresolved``: the draft Test Step ids."""

    @property
    def count(self) -> int:
        return len(self.requirements) + len(self.numbers) + len(self.steps)


def checklist(
    rows: list[ProtocolRow],
    urs: list[UrsMissed] | None,
    *,
    from_draft: bool = False,
    unresolved: tuple[str, ...] = (),
) -> list[Blocking]:
    """Every submission check, blocking or not, in ``CHECKS`` order, then (``from_draft``: the
    Protocol was started from the Protocol Draft) in ``DRAFT_CHECKS`` order. ``unresolved``:
    the draft Test Steps that stand for no requirement and that nobody rejected."""
    numbers = tuple((u.doc, u.rev, m.number) for u in urs or [] for m in u.missed if m.blocking)
    return [
        Blocking(
            check,
            tuple(r.requirement.id for r in rows if check in r.blockers),
            numbers if check == "missed_undecided" else (),
            unresolved if check == "draft_step_unresolved" else (),
        )
        for check in (*CHECKS, *(DRAFT_CHECKS if from_draft else ()))
    ]


# --- The copy -------------------------------------------------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Author(_Frozen):
    """Who: the token's subject and issuer, and the name shown at the time."""

    subject: str
    issuer: str
    name: str


class Provenance(_Frozen):
    """Where a decision of a version 2 copy comes from."""

    run_id: str
    """The run on whose Proposal it was made."""
    content_hash: str
    """The content it was made on: what the Approver sees is what this hash names."""
    draft_rev: int | None
    """The revision of the Protocol Draft the Protocol is pinned to that ``run_id`` read, or
    ``null`` when that run read no revision of it."""


class FrozenDecision(_Frozen):
    """A Proposal Decision in force when the Protocol was submitted, and who made it."""

    id: int
    decision: Verdict
    coverage: CoverageClass | None
    reason: str | None
    author: Author
    at: datetime
    provenance: Provenance | None = Field(default=None, exclude_if=lambda v: v is None)
    """Version 2 copies only: every decision of one records it. A version 1 decision has none and
    dumps without the key, which keeps the hash of every stored version 1 copy."""


class FrozenCoverage(_Frozen):
    """The Coverage class a human decided, and the decision in force that settled it."""

    coverage_class: CoverageClass
    decision: FrozenDecision


class FrozenDraft(_Frozen):
    """A drafted Test Step of the row and the decision in force on it; ``null`` for an
    undecided draft of a Vendor Reference, which needs none."""

    proposal_id: int
    draft_id: str
    decision: FrozenDecision | None


class FrozenVersion(_Frozen):
    """A version of the row's written Test Step: a removal, or its full content."""

    version: int
    removed: bool
    test_step: WrittenContent | None
    from_proposal_id: int | None
    decision_id: int | None
    author: Author
    at: datetime


class FrozenStepAttribute(_Frozen):
    """One version of a Test Step row's attributes (stage and witness_required)."""

    version: int
    stage: Stage | None = None
    witness_required: bool = False
    author: Author
    at: datetime


class FrozenTestStep(_Frozen):
    """The row's one Test Step and where it came from."""

    origin: Literal["accepted_draft", "written"]
    """``accepted_draft``: a drafted Test Step accepted as drafted (``decision``, the
    ``accepted`` one). ``written``: the written Test Step in force (``version``), edited from
    the draft ``proposal_id`` with the ``edited`` decision (``decision``) when not ``null``."""
    proposal_id: int | None
    version: int | None
    decision: FrozenDecision | None
    description: str
    method: str
    instrument: str | None
    acceptance: Acceptance
    stage: Stage | None = None
    witness_required: bool = False


class FrozenRow(_Frozen):
    requirement: str
    text: str
    source: Cite
    coverage: FrozenCoverage
    kind: Literal["vendor_reference", "test_step"]
    evidence: tuple[EvidenceStep, ...]
    """For a Vendor Reference: the vendor's Evidence steps."""
    test_step: FrozenTestStep | None
    """For a Test Step row: its Test Step."""
    drafts: tuple[FrozenDraft, ...]
    written: tuple[FrozenVersion, ...]
    """Every version of the row's written Test Step in this Protocol, oldest first."""
    step_attributes: tuple[FrozenStepAttribute, ...] = ()
    """Every version of the row's step attributes in this Protocol (Test Step rows only)."""


class FrozenDisposition(_Frozen):
    """A disposition of a missed number, and who recorded it."""

    version: int
    kind: MissedKind
    justification: str
    author: Author
    at: datetime


class FrozenMissed(_Frozen):
    number: str
    page: int
    disposition: FrozenDisposition
    """The disposition in force: the latest of ``dispositions``."""
    dispositions: tuple[FrozenDisposition, ...]
    """Every version of its disposition in this Protocol, oldest first, as for a written Test
    Step: the Approver is none of their authors."""


class FrozenUrs(_Frozen):
    doc: str
    rev: int
    numbers: Literal["checked", "not_applicable"]
    missed: tuple[FrozenMissed, ...]
    unquoted: tuple[UnquotedText, ...]


class ProtocolCopy(_Frozen):
    """The frozen copy of a submitted Protocol: what the Approver reads."""

    protocol_id: int
    equipment: str
    run_id: str
    preparer: Author
    """Who submitted it."""
    rows: tuple[FrozenRow, ...]
    """One per requirement of the run, in requirement order."""
    urs: tuple[FrozenUrs, ...] | None
    """Per URS of the run's completeness check: the missed numbers with every version of their
    dispositions, and the unquoted text; ``null`` for a run written before the check existed."""


class FrozenCandidate(_Frozen):
    """A draft Test Step that stands for the row's requirement, and who decided it."""

    proposal_id: int
    step: str
    step_decision: FrozenDecision | None
    """The decision in force on the step in this Protocol; ``null`` while undecided."""
    criterion_proposal_id: int | None
    criterion_decision: FrozenDecision | None
    mapping_version: int | None
    """The human mapping in force, for a step the traceability table maps to none or to
    several requirements; ``null`` when the table maps it to exactly one."""


class FrozenFindingReason(_Frozen):
    version: int
    reason: str
    author: Author
    at: datetime


class FrozenFinding(_Frozen):
    """A finding of the Protocol Draft in the run: every decision on it with its author and
    reason (rejections too), and the reasons written for submitting its row. Findings tied to
    no row of the Protocol are here too."""

    proposal_id: int
    type: DraftType
    requirement: str
    test_step: str | None
    row: str | None
    detail: str
    label: str | None
    decisions: tuple[FrozenDecision, ...]
    """Every decision on this content, the one in force first; empty while undecided."""
    reasons: tuple[FrozenFindingReason, ...]
    """Every reason written in this Protocol, oldest first."""


class FrozenMapping(_Frozen):
    version: int
    requirement: str
    author: Author
    at: datetime


class FrozenDraftStep(_Frozen):
    """A Test Step of the pinned Protocol Draft: mapped by a human, dropped by the citation
    check or traced by the table, with every decision on it and on its criterion."""

    step: str
    proposal_id: int
    traced_to: tuple[str, ...]
    """The requirements the draft's traceability table traces it to."""
    not_read: str | None
    """Why the citation check dropped its reading, or ``null``."""
    requirement: str | None
    """The requirement it stands for in the Protocol; ``null``: none (it was rejected)."""
    mappings: tuple[FrozenMapping, ...]
    """Every human mapping of it in this Protocol, oldest first."""
    decisions: tuple[FrozenDecision, ...]
    criterion_decisions: tuple[FrozenDecision, ...]


class FrozenSource(_Frozen):
    """The Protocol Draft the Protocol was pinned to, and the run that read it."""

    doc: str
    rev: int
    sha256: str
    run_id: str


class FrozenRowDetail(_Frozen):
    """What a version 2 copy records about one row beyond a version 1 row."""

    requirement: str
    source: RowSource | None
    """Where the row's Test Step comes from; ``null`` for a Vendor Reference."""
    criterion_decision: FrozenDecision | None
    """For an accepted draft step: the decision on its Acceptance Criterion."""
    candidates: tuple[FrozenCandidate, ...]
    findings: tuple[int, ...]
    """The Proposal ids of the findings about the row's requirement (see ``findings`` of the
    copy)."""


class ProtocolCopyV2(ProtocolCopy):
    """The frozen copy of a Protocol started from the Protocol Draft: the version 1 content
    (``rows``, ``urs``, the Preparer) and what the draft adds."""

    schema_version: Literal[2] = 2
    source: FrozenSource
    row_details: tuple[FrozenRowDetail, ...]
    """One per row of ``rows``, in the same order."""
    draft_steps: tuple[FrozenDraftStep, ...]
    """Every Test Step of the pinned draft, in draft order."""
    findings: tuple[FrozenFinding, ...]
    """Every finding of the run, whatever row it concerns."""


def parse_copy(raw: dict[str, Any]) -> ProtocolCopy:
    """A stored copy through the model of its ``schema_version``: a copy without one is version
    1 and is read by the unchanged version 1 model."""
    if raw.get("schema_version") == 2:
        return ProtocolCopyV2.model_validate(raw)
    return ProtocolCopy.model_validate(raw)


def _author(a: audit.Actor) -> Author:
    return Author(subject=a.subject, issuer=a.issuer, name=a.name)


def _utc(at: datetime) -> datetime:
    """The same instant in UTC, so the session's time zone never changes the hash."""
    return at.astimezone(UTC)


def _decision(d: Decision, draft_revs: dict[str, int] | None = None) -> FrozenDecision:
    """``d`` as frozen: with its provenance when ``draft_revs`` (for each run, the revision of
    the pinned Protocol Draft it read) is given, as in a version 2 copy."""
    return FrozenDecision(
        id=d.id,
        decision=d.decision,
        coverage=d.coverage,
        reason=d.reason,
        author=_author(d.actor),
        at=_utc(d.at),
        provenance=None
        if draft_revs is None
        else Provenance(
            run_id=d.run_id, content_hash=d.content_hash, draft_rev=draft_revs.get(d.run_id)
        ),
    )


def draft_revisions(session: Session, equipment: str, doc: str) -> dict[str, int]:
    """For each imported run of the Equipment that read a revision of the Protocol Draft
    ``doc``, that revision."""
    out: dict[str, int] = {}
    for run_id, documents in session.execute(
        select(RUNS.c.run_id, RUNS.c.documents).where(RUNS.c.equipment == equipment)
    ):
        for d in cast(list[dict[str, Any]], documents or []):
            if d.get("doc_id") == doc and d.get("rev") is not None:
                out[run_id] = int(d["rev"])
    return out


def _version(v: WrittenVersion) -> FrozenVersion:
    return FrozenVersion(
        version=v.version,
        removed=v.removed,
        test_step=v.content,
        from_proposal_id=v.from_proposal_id,
        decision_id=v.decision_id,
        author=_author(v.actor),
        at=_utc(v.at),
    )


class NotFrozen(Exception):
    """What a copy is made of breaks a rule the submission checks enforce: never, after them."""


def _step_attribute(a: StepAttribute) -> FrozenStepAttribute:
    return FrozenStepAttribute(
        version=a.version,
        stage=a.stage,
        witness_required=a.witness_required,
        author=_author(a.actor),
        at=_utc(a.at),
    )


def _test_step(r: ProtocolRow, revs: dict[str, int] | None) -> FrozenTestStep | None:
    step = step_of(r)
    if step is None:
        return None
    if not shaped(step.acceptance):
        raise NotFrozen(f"the Test Step of {r.requirement.id} has no shaped Acceptance Criterion")
    return FrozenTestStep(
        origin=step.origin,
        proposal_id=step.proposal_id,
        version=step.version,
        decision=None if step.decision is None else _decision(step.decision, revs),
        description=step.description,
        method=step.method,
        instrument=step.instrument,
        acceptance=step.acceptance,
        stage=step.stage,
        witness_required=step.witness_required,
    )


def _row(r: ProtocolRow, revs: dict[str, int] | None = None) -> FrozenRow:
    if r.kind == "undecided" or r.decided_class is None:
        raise NotFrozen(f"the Coverage of {r.requirement.id} is not decided")
    req = r.requirement
    return FrozenRow(
        requirement=req.id,
        text=req.text,
        source=req.source,
        coverage=FrozenCoverage(
            coverage_class=r.decided_class, decision=_decision(r.coverage.decisions[0], revs)
        ),
        kind=r.kind,
        evidence=req.evidence if r.kind == "vendor_reference" else (),
        test_step=_test_step(r, revs),
        drafts=tuple(
            FrozenDraft(
                proposal_id=d.standing.proposal_id,
                draft_id=d.draft.id,
                decision=_decision(d.standing.decisions[0], revs)
                if d.standing.state == "decided"
                else None,
            )
            for d in r.drafts
        ),
        written=tuple(_version(v) for v in r.written),
        step_attributes=tuple(_step_attribute(a) for a in r.step_attributes)
        if r.kind == "test_step"
        else (),
    )


def _disposition(d: Disposition) -> FrozenDisposition:
    return FrozenDisposition(
        version=d.version,
        kind=d.kind,
        justification=d.justification,
        author=_author(d.actor),
        at=_utc(d.at),
    )


def _missed(u: UrsMissed, m: MissedNumber) -> FrozenMissed:
    if m.disposition is None:
        raise NotFrozen(f"{m.number} of {u.doc} revision {u.rev} has no disposition")
    return FrozenMissed(
        number=m.number,
        page=m.page,
        disposition=_disposition(m.disposition),
        dispositions=tuple(_disposition(d) for d in m.dispositions),
    )


def _urs(u: UrsMissed) -> FrozenUrs:
    return FrozenUrs(
        doc=u.doc,
        rev=u.rev,
        numbers=u.numbers,
        missed=tuple(_missed(u, m) for m in u.missed),
        unquoted=u.unquoted,
    )


def hash_of(copy: ProtocolCopy) -> str:
    """The SHA-256 of the copy's canonical JSON."""
    return digest(copy.model_dump(mode="json"))


def _copy(
    current: lifecycle.AssembledProtocol,
    rows: list[ProtocolRow],
    urs: list[UrsMissed] | None,
    preparer: Author,
) -> ProtocolCopy:
    return ProtocolCopy(
        protocol_id=current.id,
        equipment=current.equipment,
        run_id=current.run_id,
        preparer=preparer,
        rows=tuple(_row(r) for r in rows),
        urs=None if urs is None else tuple(_urs(u) for u in urs),
    )


def _decisions(s: Standing | None, revs: dict[str, int]) -> tuple[FrozenDecision, ...]:
    if s is None or s.state != "decided":
        return ()
    return tuple(_decision(d, revs) for d in s.decisions)


def _candidate(c: DraftCandidate, revs: dict[str, int]) -> FrozenCandidate:
    d, k = c.step_decision, c.criterion_decision
    k_standing = c.criterion_standing
    return FrozenCandidate(
        proposal_id=c.standing.proposal_id,
        step=c.step.id,
        step_decision=None if d is None else _decision(d, revs),
        criterion_proposal_id=None if k_standing is None else k_standing.proposal_id,
        criterion_decision=None if k is None else _decision(k, revs),
        mapping_version=None if c.mapping is None else c.mapping.version,
    )


def _row_detail(r: ProtocolRow, revs: dict[str, int]) -> FrozenRowDetail:
    crit = None
    accepted = r.accepted_candidate
    if accepted is not None and not r.changed and accepted.criterion_decision is not None:
        crit = _decision(accepted.criterion_decision, revs)
    return FrozenRowDetail(
        requirement=r.requirement.id,
        source=r.source,
        criterion_decision=crit,
        candidates=tuple(_candidate(c, revs) for c in r.candidates),
        findings=tuple(f.standing.proposal_id for f in r.findings),
    )


def _finding(
    s: Standing,
    f: DraftCheckFinding,
    reasons: tuple[draft_source.Reason, ...],
    revs: dict[str, int],
) -> FrozenFinding:
    return FrozenFinding(
        proposal_id=s.proposal_id,
        type=f.type,
        requirement=f.requirement,
        test_step=f.test_step,
        row=f.row,
        detail=f.detail,
        label=f.label,
        decisions=_decisions(s, revs),
        reasons=tuple(
            FrozenFindingReason(
                version=x.version, reason=x.reason, author=_author(x.actor), at=_utc(x.at)
            )
            for x in reasons
        ),
    )


def _copy_v2(
    session: Session,
    current: lifecycle.AssembledProtocol,
    rows: list[ProtocolRow],
    urs: list[UrsMissed] | None,
    preparer: Author,
) -> ProtocolCopyV2:
    pin = current.draft
    if pin is None:
        raise NotFrozen(f"Protocol {current.id} was not started from a Protocol Draft")
    stood = standings(session, current.run_id) or []
    proposed = proposed_of(session, current.run_id)
    criteria: dict[str, Standing] = {}
    for s in stood:
        if s.kind == "draft_criterion":
            c = DraftCriterionProposal.model_validate(proposed[s.proposal_id])
            criteria.setdefault(c.id, s)
    listing, _ = draft_listing(session, current, stood, proposed)
    reasons = draft_source.reasons_of(session, current.id)
    revs = draft_revisions(session, current.equipment, pin.doc)
    return ProtocolCopyV2(
        protocol_id=current.id,
        equipment=current.equipment,
        run_id=current.run_id,
        preparer=preparer,
        rows=tuple(_row(r, revs) for r in rows),
        row_details=tuple(_row_detail(r, revs) for r in rows),
        urs=None if urs is None else tuple(_urs(u) for u in urs),
        source=FrozenSource(doc=pin.doc, rev=pin.rev, sha256=pin.sha256, run_id=current.run_id),
        draft_steps=tuple(
            FrozenDraftStep(
                step=e.step.id,
                proposal_id=e.standing.proposal_id,
                traced_to=e.step.mapped_to,
                not_read=e.step.not_read,
                requirement=e.requirement,
                mappings=tuple(
                    FrozenMapping(
                        version=m.version,
                        requirement=m.requirement,
                        author=_author(m.actor),
                        at=_utc(m.at),
                    )
                    for m in e.mappings
                ),
                decisions=_decisions(e.standing, revs),
                criterion_decisions=_decisions(criteria.get(e.step.id), revs),
            )
            for e in listing
        ),
        findings=tuple(
            _finding(
                s,
                DraftCheckFinding.model_validate(proposed[s.proposal_id]),
                reasons.get(s.proposal_id, ()),
                revs,
            )
            for s in stood
            if s.kind == "draft"
        ),
    )


def build_copy(
    session: Session,
    current: lifecycle.AssembledProtocol,
    rows: list[ProtocolRow],
    urs: list[UrsMissed] | None,
    preparer: Author,
) -> ProtocolCopy:
    """The copy a submission freezes: version 2 for a Protocol started from the Protocol
    Draft, version 1 for any other."""
    if current.draft is not None:
        return _copy_v2(session, current, rows, urs, preparer)
    return _copy(current, rows, urs, preparer)


def draft_hash_of(copy: ProtocolCopy) -> str:
    """The SHA-256 of the copy's canonical JSON without its Preparer: what a Preparer confirms
    before submitting, whoever they are. Every row, decision, Test Step, step attribute and
    disposition of the copy is in it, so it changes whenever the copy would."""
    return digest(copy.model_dump(mode="json", exclude={"preparer"}))


_NO_ONE = Author(subject="", issuer="", name="")


def draft_hash(
    session: Session,
    current: lifecycle.AssembledProtocol,
    rows: list[ProtocolRow],
    urs: list[UrsMissed] | None,
    unresolved: tuple[str, ...] = (),
) -> str | None:
    """``draft_hash_of`` the copy a submission would freeze now; ``None`` while a check of
    ``checklist`` blocks it (there is nothing to submit yet)."""
    from_draft = current.draft is not None
    if any(b.count for b in checklist(rows, urs, from_draft=from_draft, unresolved=unresolved)):
        return None
    return draft_hash_of(build_copy(session, current, rows, urs, _NO_ONE))


# --- Submitting -----------------------------------------------------------------------


@dataclass(frozen=True)
class Submission:
    """A ``submitted`` event: its frozen copy and hash."""

    event_id: int
    at: datetime
    copy: ProtocolCopy
    hash: str
    """The stored ``copy_hash`` column."""
    recomputed_hash: str
    """``hash_of`` the parsed ``frozen_copy``: differs from ``hash`` when the copy was altered."""


def submissions_of(session: Session, protocol_id: int) -> list[Submission]:
    """Every submission of the Protocol, oldest first; earlier ones were returned."""
    out: list[Submission] = []
    for m in session.execute(
        select(EVENTS.c.id, EVENTS.c.at, EVENTS.c.frozen_copy, EVENTS.c.copy_hash)
        .where(EVENTS.c.protocol_id == protocol_id, EVENTS.c.event == "submitted")
        .order_by(EVENTS.c.id)
    ).mappings():
        copy = parse_copy(m["frozen_copy"])
        out.append(
            Submission(
                event_id=m["id"],
                at=m["at"],
                copy=copy,
                hash=m["copy_hash"],
                recomputed_hash=hash_of(copy),
            )
        )
    return out


def submit(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    check: Completeness | None,
    expected_draft_hash: str,
    *,
    auth_time: datetime | None,
    jti: str | None,
    is_demo: bool = False,
    expected_latest_draft_rev: int | None = None,
) -> lifecycle.AssembledProtocol:
    """Submits a Protocol in Draft status that nothing blocks: freezes its copy and hash in
    the ``submitted`` event. ``check``: the completeness check of the Protocol's run.
    ``expected_draft_hash``: the ``draft_hash`` the Preparer read; ``Conflict`` when the draft
    holds anything else now, so nobody signs content they did not see.
    ``expected_latest_draft_rev``: for a Protocol started from the Protocol Draft, the latest
    revision of the draft the Preparer read; ``Conflict`` when a newer one arrived since,
    ``Refused`` without it. Signs it:
    ``SignatureAuthRequired`` without a fresh ``auth_time`` and ``jti``, before anything is
    written."""
    auth_time, jti = audit.require_signing_claims(auth_time, jti)
    current = lifecycle.locked(
        session, protocol_id, "draft", "only a Protocol in Draft status can be submitted"
    )
    latest = draft_source.check_latest(session, current, expected_latest_draft_rev)
    rows = rows_of(session, current)
    urs = missed_of(session, protocol_id, check)
    from_draft = current.draft is not None
    unresolved = tuple(unresolved_steps(session, current)) if from_draft else ()
    blocking = [
        b for b in checklist(rows, urs, from_draft=from_draft, unresolved=unresolved) if b.count
    ]
    if blocking:
        listed = ", ".join(f"{b.check} ({b.count})" for b in blocking)
        raise Conflict(f"Protocol {protocol_id} cannot be submitted while it is blocked: {listed}")
    copy = build_copy(session, current, rows, urs, _author(actor))
    if draft_hash_of(copy) != expected_draft_hash:
        raise Conflict(
            f"Protocol {protocol_id} has changed since you read it: reload the page and review"
            " it before submitting"
        )
    hashed = hash_of(copy)
    done = lifecycle.append(
        session,
        actor,
        protocol_id,
        "submitted",
        None,
        frozen_copy=copy.model_dump(mode="json"),
        copy_hash=hashed,
        latest_draft_rev=latest,
    )
    sig = audit.record_signature(
        session,
        actor,
        record_type="protocol_submission",
        signature_meaning="prepared",
        content_hash=hashed,
        auth_time=auth_time,
        jti=jti,
        is_demo=is_demo,
        protocol_event_id=done.id,
    )
    new_audit: dict[str, audit.JsonValue] = {
        "status": done.status,
        "event_id": done.id,
        "hash": hashed,
        "signature_id": sig.id,
    }
    if latest is not None:
        new_audit["latest_draft_rev"] = latest
    audit.append(
        session,
        actor,
        "protocol submitted",
        "protocol",
        str(protocol_id),
        old={"status": current.status},
        new=new_audit,
    )
    return current.after(done)
