"""The routes of the Protocol assembled in TraceQ (spec #247, "API"): start the Protocol of a
run's Equipment, read the Protocol of a run, add a version of a written Test Step, edit a
drafted Test Step, decide a printed requirement number the run missed, submit a Protocol in
Draft status, withdraw one, approve or return a Submitted one.

Every route needs a valid bearer token; every write needs the deciding role, approving and
returning the approving role, so the Audit Trail names who did it. Reading is open to any
signed-in role. Accepting and rejecting a drafted Test Step go through ``recordDecision``.
Errors: 401 without a token, 403 without the role, 404 unknown, 409 for a refused state change
with the reason in words.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import (
    approval,
    attributes,
    draft_source,
    lifecycle,
    missed,
    submission,
    written,
)
from traceq.assembly.attributes import Stage
from traceq.assembly.lifecycle import EventKind, Status
from traceq.assembly.missed import MissedKind, UrsMissed
from traceq.assembly.rows import (
    Blocker,
    DraftCandidate,
    DraftOfRow,
    DraftStepListing,
    PrefillOrigin,
    ProtocolRow,
    RowFinding,
    RowKind,
    RowSource,
    draft_listing,
    rows_of,
    step_of,
)
from traceq.assembly.submission import Check, ProtocolCopy
from traceq.assembly.written import Acceptance, WrittenContent, WrittenVersion
from traceq.db import transaction
from traceq.identity import Principal, reauthentication_required
from traceq.proposals import decisions
from traceq.proposals.api import Proposal, actor_of, proposal_view
from traceq.runs.api import DRAFTS_FILE, find_run
from traceq.runs.schemas import (
    Cite,
    Completeness,
    DraftCheckFinding,
    DraftCriterionProposal,
    DraftedTestStep,
    DraftStepProposal,
    EvidenceStep,
    UnquotedText,
)
from traceq.traceability.coverage import CoverageClass
from traceq.traceability.values import Value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProtocolEvent(_Model):
    """A status change of a Protocol: what, who, when and why."""

    id: int
    event: EventKind
    status: Status
    """The status after it: ``started`` and ``returned`` give ``draft``."""
    reason: str | None
    """For a return or a withdrawal: the reason given."""
    subject: str
    issuer: str
    name: str
    """The name shown for the person at the time."""
    at: datetime
    electronic_signature: audit.ElectronicSignatureView | None = None


class RowDraft(_Model):
    """A drafted Test Step of the row's requirement, as the run drafted it, and the Proposal it
    was imported as, decided with ``recordDecision`` (accepted or rejected)."""

    draft: DraftedTestStep
    proposal: Proposal


class RowTestStep(_Model):
    """The one Test Step of a Test Step row."""

    origin: Literal["accepted_draft", "written"]
    """``accepted_draft``: a drafted Test Step accepted as drafted. ``written``: a Test Step a
    human wrote in this Protocol, or edited from a draft."""
    proposal_id: int | None
    """For an accepted draft: its Proposal. For a written one: the draft it was edited from,
    ``null`` when written without one."""
    version: int | None
    """For a written Test Step: the version in force."""
    description: str
    method: str
    instrument: str | None
    acceptance: Value | None
    """The Acceptance Criterion; ``null`` while it is "to be set by a human"."""
    acceptance_flag: str | None
    stage: Stage | None = None
    witness_required: bool = False
    source: RowSource | None = None
    """Where the Test Step comes from: the site's Protocol Draft (``draft``), a Test Step
    TraceQ drafted (``traceq_drafted``) or one a person wrote (``traceq_written``)."""


class WrittenVersionView(_Model):
    """A version of a written Test Step: its full content, or a removal, who and when."""

    id: int
    version: int
    """1, 2, ... per Protocol and requirement."""
    removed: bool
    """A removal takes the written Test Step back: the row falls back to its accepted draft
    or to Vendor Reference."""
    test_step: WrittenContent | None
    """The full content; ``null`` for a removal."""
    from_proposal_id: int | None
    """For a version made by editing a drafted Test Step: that draft's Proposal."""
    decision_id: int | None
    """For a version made by editing a drafted Test Step: the ``edited`` decision."""
    subject: str
    issuer: str
    name: str
    """The name shown for the person at the time."""
    at: datetime


class RowPrefill(_Model):
    """What the row's write form starts from."""

    origin: PrefillOrigin
    """``written``: the written Test Step in force. ``withdrawn``: its latest version in the
    most recent withdrawn Protocol of the Equipment (it does not carry over; saving it makes a
    version of this Protocol). ``draft``: the first drafted Test Step of the requirement."""
    description: str
    method: str
    instrument: str | None
    acceptance: Acceptance | None
    """``null`` when the source has no Acceptance Criterion in one of the four shapes."""


class DraftMappingView(_Model):
    """A requirement a human mapped a draft Test Step to, who and when."""

    version: int
    requirement: str
    subject: str
    issuer: str
    name: str
    at: datetime


class FindingReasonView(_Model):
    """A Preparer's written reason on an accepted finding, who and when."""

    id: int
    version: int
    reason: str
    subject: str
    issuer: str
    name: str
    at: datetime


class RowCandidate(_Model):
    """A Test Step of the site's Protocol Draft that stands for the row's requirement, with its
    Acceptance Criterion and where each stands. Decided with ``recordDecision`` (accepted or
    rejected) or edited with ``editDraftedTestStep``; an edit made in another Protocol does not
    decide it here."""

    step: DraftStepProposal
    proposal: Proposal
    criterion: DraftCriterionProposal | None
    """``null`` when the draft's reading of the step holds no Acceptance Criterion."""
    criterion_proposal: Proposal | None
    mapping: DraftMappingView | None
    """The human mapping in force, for a step the table maps to none or to several
    requirements; ``null`` when the table maps it to exactly one."""
    ready: bool
    """Nothing is left to decide here: the step, and its criterion once the step is accepted."""
    accepted: bool
    """Accepted with its criterion accepted: usable as the row's Test Step."""


class RowFindingView(_Model):
    """A finding of the Protocol Draft about the row's requirement, its decision state and the
    reasons written for it in this Protocol."""

    finding: DraftCheckFinding
    proposal: Proposal
    reasons: list[FindingReasonView]
    """Every reason, oldest first; the latest counts."""


class DraftStepView(_Model):
    """A Test Step of the Protocol's pinned Protocol Draft: the ones that stand for no
    requirement are listed and unusable until a human maps one or rejects the step."""

    step: DraftStepProposal
    proposal: Proposal
    mappings: list[DraftMappingView]
    """Every mapping of it in this Protocol, oldest first."""
    requirement: str | None
    """The requirement it stands for in this Protocol; ``null``: unusable."""
    resolved: bool
    """It stands for a requirement, or a person rejected it."""


class ProtocolSource(_Model):
    """The Protocol Draft a Protocol was started from: pinned at creation, with the run, and
    never re-synced in Draft, Submitted or Returned. A later revision never clears a warning
    on it; Return or Withdraw it and start a new one from the latest revision."""

    doc: str
    rev: int
    sha256: str


class ProtocolRowView(_Model):
    """One requirement of the run and what the Protocol holds for it."""

    requirement: str
    text: str
    source: Cite
    """Where the requirement is printed in the URS."""
    coverage: Proposal
    """The requirement's Coverage row and where it stands."""
    decided_class: CoverageClass | None
    """The class a human decided on this run's content; ``null`` while undecided or changed
    since it was decided."""
    kind: RowKind
    """``undecided``: Coverage not decided on this run's content, so the kind is unknown.
    ``vendor_reference``: decided ``covered_by_vendor`` with no accepted draft, proven by the
    vendor's Evidence and not tested again on site. ``test_step``: needs one Test Step."""
    evidence: tuple[EvidenceStep, ...]
    """For a Vendor Reference: the vendor's Evidence steps (document, revision, step)."""
    test_step: RowTestStep | None
    """For a Test Step row: its Test Step, ``null`` while it has none."""
    drafts: list[RowDraft]
    """The drafted Test Steps of the requirement, with their decision state."""
    written: list[WrittenVersionView]
    """Every version of the requirement's written Test Step in this Protocol, oldest first."""
    prefill: RowPrefill | None
    """What the write form starts from; ``null`` with no source at all."""
    blockers: list[Blocker]
    """What blocks this row: ``coverage_undecided``; for a Test Step row ``draft_undecided``
    (a drafted Test Step not decided), ``no_test_step``, ``acceptance_not_shaped`` (its Test
    Step is an accepted draft whose Acceptance Criterion is missing or free text). In a
    Protocol started from the Protocol Draft also ``finding_undecided``,
    ``finding_reason_missing`` and ``stage_missing``."""
    stage: Stage | None = None
    witness_required: bool = False
    step_source: RowSource | None = None
    """Where the row's Test Step comes from; ``null`` while it has none."""
    candidates: list[RowCandidate] = []
    """In a Protocol started from the Protocol Draft: its Test Steps that stand for the
    requirement. When there are some, ``drafts`` is empty: a row holds one source."""
    findings: list[RowFindingView] = []
    """In a Protocol started from the Protocol Draft: the findings about the requirement."""
    changed: bool = False
    """The row's Test Step is one a person wrote or edited in this Protocol: an accepted
    finding on it then needs no written reason."""


# The spec called a human's ruling on a missed number its "answer"; the code names it a
# disposition, because the schema must never name an answer key (tests/test_api.py).


class MissedDispositionView(_Model):
    """What a human decided a missed number is: its kind and justification, who and when."""

    id: int
    version: int
    """1, 2, ... per URS document, revision and number; the latest counts."""
    kind: MissedKind
    """``not_a_requirement``: the printed number names no requirement. ``not_tested_here``: a
    requirement this Protocol does not test."""
    justification: str
    subject: str
    issuer: str
    name: str
    """The name shown for the person at the time."""
    at: datetime


class MissedNumberView(_Model):
    """A printed requirement number that did not become a requirement of the run."""

    number: str
    page: int
    """The first page it is printed on."""
    disposition: MissedDispositionView | None
    """The disposition in force (the latest); ``null`` while there is none."""
    dispositions: list[MissedDispositionView]
    """Every disposition of it in this Protocol, oldest first."""
    blocking: bool
    """Without a disposition: it blocks submission."""


class ProtocolUrs(_Model):
    """One URS of the run's completeness check: its missed numbers and its unquoted text."""

    doc: str
    rev: int
    numbers: Literal["checked", "not_applicable"]
    """``not_applicable`` when the run read no printed requirement number in it: it then
    lists no missed number."""
    missed: list[MissedNumberView]
    unquoted: list[UnquotedText]
    """URS text no requirement quotes: shown to look for a lost requirement; it needs no
    disposition and never blocks."""


class MissedKey(_Model):
    doc: str
    rev: int
    number: str


class ChecklistItem(_Model):
    """One submission check: how many rows or missed numbers it holds back, and which."""

    check: Check
    """``coverage_undecided``: Coverage not decided by a human on the run's content.
    ``draft_undecided``: a drafted Test Step of a Test Step row not decided.
    ``no_test_step``: a Test Step row without its one Test Step. ``acceptance_not_shaped``: an
    Acceptance Criterion missing or free text. ``missed_undecided``: a printed requirement
    number the run missed, without its disposition."""
    count: int
    """0 when it blocks nothing."""
    requirements: list[str]
    """The rows concerned."""
    numbers: list[MissedKey]
    """For ``missed_undecided``: the numbers concerned."""
    steps: list[str] = []
    """For ``draft_step_unresolved``: the draft Test Steps concerned. The checks
    ``finding_undecided``, ``finding_reason_missing``, ``stage_missing`` and
    ``draft_step_unresolved`` are listed only for a Protocol started from the Protocol Draft;
    that one cannot be submitted yet (``draft_hash`` stays ``null``): its frozen copy is built by
    the next ticket."""


class SubmissionView(_Model):
    """A submission of the Protocol: the frozen copy it stored and that copy's hash."""

    event_id: int
    """The ``submitted`` event; approving names it, with the hash."""
    hash: str
    """The SHA-256 of the copy's canonical JSON (keys sorted, no spaces, UTF-8)."""
    at: datetime
    frozen_copy: ProtocolCopy
    """Every row, its decisions in force and who made them, its Test Step and every version
    of its written one; the missed numbers with every version of their dispositions; the
    unquoted text."""
    outcome: ProtocolEvent | None
    """The approval or the return that followed this submission, with who, when and (for a
    return) why; ``null`` while it awaits one. An approval is a recorded status, not an
    Electronic Signature (ADR 0007 phase 2)."""


class ProtocolView(_Model):
    """A Protocol assembled in TraceQ, for one Equipment, started from one imported run. Not
    a Protocol Draft: that is the site's document under Pre-review."""

    id: int
    equipment: str
    run_id: str
    """The run it was started from."""
    status: Status
    """The latest event's status."""
    events: list[ProtocolEvent]
    """Every status change, oldest first."""
    rows: list[ProtocolRowView] | None
    """In Draft status: one row per requirement of the run, in requirement order, computed
    from the current decisions. ``null`` in any other status."""
    urs: list[ProtocolUrs] | None
    """In Draft status: per URS of the run's completeness check, the printed numbers the run
    missed with their dispositions, and the unquoted text. ``null`` in any other status, and for a
    run written before the completeness check existed."""
    checklist: list[ChecklistItem] | None
    """In Draft status: the five submission checks, in order, each with its count; it may be
    submitted when every count is 0. ``null`` in any other status."""
    draft_hash: str | None
    """In Draft status when no check blocks: the SHA-256 of the copy a submission would freeze
    now, without its Preparer (the same canonical JSON as the copy's hash). The Preparer
    submits it as ``expected_draft_hash``; any change to a row, decision, Test Step, step
    attribute or disposition changes it. ``null`` while a check blocks, and in any other
    status."""
    submission: SubmissionView | None
    """While Submitted or Approved: the current submission, which the page shows instead of
    live rows. ``null`` in any other status."""
    submissions: list[SubmissionView]
    """Every submission, oldest first: those before the current one were returned to Draft."""
    source: ProtocolSource | None = None
    """The Protocol Draft it was started from, pinned with ``run_id``; ``null`` for a Protocol
    assembled from TraceQ's own drafted Test Steps."""
    draft_steps: list[DraftStepView] | None = None
    """In Draft status, for a Protocol started from the draft: every Test Step of the pinned
    draft in draft order, with the requirement it stands for; the ones that stand for none
    (the table maps them to none or several requirements, or the citation check dropped them)
    are unusable until a human maps them with ``mapDraftStep`` or rejects them."""


class Withdrawal(_Model):
    reason: str
    """Why the Protocol is given up."""


class Approval(_Model):
    """What the Approver read: approval is bound to that submission and its hash."""

    submission_event_id: int
    """The ``event_id`` of the current submission."""
    hash: str
    """The ``hash`` of the current submission's frozen copy."""


class SubmitRequest(_Model):
    """What the Preparer read: submission is bound to that draft and its hash."""

    expected_draft_hash: str = Field(min_length=1)
    """The ``draft_hash`` of the Protocol view the Preparer was reading."""


class Return(_Model):
    reason: str
    """Why the Protocol goes back to Draft: never blank."""


class NewWrittenVersion(_Model):
    """A version of a requirement's written Test Step. No Reason for Change."""

    test_step: WrittenContent | None
    """The full content; ``null`` removes the written Test Step."""


class StepAttributesUpdate(_Model):
    """Step attributes for a Test Step row in a Draft Protocol."""

    stage: Stage | None = None
    witness_required: bool = False


class MissedDisposition(_Model):
    """A disposition of a printed requirement number the run missed. No Reason for Change: a
    later one replaces it, and every one is kept."""

    doc: str
    rev: int
    number: str
    """URS document, revision and printed number: what the disposition is keyed by."""
    kind: MissedKind
    justification: str
    """Why: never blank."""


class StartProtocol(_Model):
    """How a Protocol is started."""

    from_draft: bool = False
    """Start from the site's Protocol Draft the run read instead of from TraceQ's own drafted
    Test Steps alone (ADR 0012, amended 26 November 2026): pinned to the run and the draft's
    document, revision and hash."""


class DraftMapping(_Model):
    """The requirement a draft Test Step is mapped to."""

    requirement: str


class FindingReason(_Model):
    """Why a row on which a finding was accepted is submitted as it is."""

    reason: str
    """Never blank."""


class DraftEdit(_Model):
    """An edit of a drafted Test Step: the ``edited`` decision and the Test Step it gives."""

    reason: str
    """The Reason for Change of the ``edited`` decision."""
    test_step: WrittenContent
    """The Test Step as edited, saved as a version of the written Test Step."""


def _event(
    e: lifecycle.Event,
    sig: audit.ElectronicSignature | None = None,
    expected_hash: str | None = None,
) -> ProtocolEvent:
    return ProtocolEvent(
        id=e.id,
        event=e.event,
        status=e.status,
        reason=e.reason,
        subject=e.actor.subject,
        issuer=e.actor.issuer,
        name=e.actor.name,
        at=e.at,
        electronic_signature=audit.signature_view(
            sig, verified=audit.verified_against(sig, expected_hash)
        ),
    )


def _draft(d: DraftOfRow) -> RowDraft:
    return RowDraft(draft=d.draft, proposal=proposal_view(d.standing))


def _version(v: WrittenVersion) -> WrittenVersionView:
    return WrittenVersionView(
        id=v.id,
        version=v.version,
        removed=v.removed,
        test_step=v.content,
        from_proposal_id=v.from_proposal_id,
        decision_id=v.decision_id,
        subject=v.actor.subject,
        issuer=v.actor.issuer,
        name=v.actor.name,
        at=v.at,
    )


def _mapping(m: draft_source.Mapping) -> DraftMappingView:
    return DraftMappingView(
        version=m.version,
        requirement=m.requirement,
        subject=m.actor.subject,
        issuer=m.actor.issuer,
        name=m.actor.name,
        at=m.at,
    )


def _candidate(c: DraftCandidate) -> RowCandidate:
    return RowCandidate(
        step=c.step,
        proposal=proposal_view(c.standing),
        criterion=c.criterion,
        criterion_proposal=None
        if c.criterion_standing is None
        else proposal_view(c.criterion_standing),
        mapping=None if c.mapping is None else _mapping(c.mapping),
        ready=c.ready,
        accepted=c.accepted,
    )


def _finding(f: RowFinding) -> RowFindingView:
    return RowFindingView(
        finding=f.finding,
        proposal=proposal_view(f.standing),
        reasons=[
            FindingReasonView(
                id=x.id,
                version=x.version,
                reason=x.reason,
                subject=x.actor.subject,
                issuer=x.actor.issuer,
                name=x.actor.name,
                at=x.at,
            )
            for x in f.reasons
        ],
    )


def _draft_step(e: DraftStepListing) -> DraftStepView:
    return DraftStepView(
        step=e.step,
        proposal=proposal_view(e.standing),
        mappings=[_mapping(m) for m in e.mappings],
        requirement=e.requirement,
        resolved=e.resolved,
    )


def _row_step(r: ProtocolRow) -> RowTestStep | None:
    step = step_of(r)
    if step is None:
        return None
    return RowTestStep(
        source=step.source,
        origin=step.origin,
        proposal_id=step.proposal_id,
        version=step.version,
        description=step.description,
        method=step.method,
        instrument=step.instrument,
        acceptance=step.acceptance,
        acceptance_flag=step.acceptance_flag,
        stage=step.stage,
        witness_required=step.witness_required,
    )


def _prefill(r: ProtocolRow) -> RowPrefill | None:
    f = r.prefill
    if f is None:
        return None
    return RowPrefill(
        origin=f.origin,
        description=f.description,
        method=f.method,
        instrument=f.instrument,
        acceptance=f.acceptance,
    )


def _disposition(a: missed.Disposition) -> MissedDispositionView:
    return MissedDispositionView(
        id=a.id,
        version=a.version,
        kind=a.kind,
        justification=a.justification,
        subject=a.actor.subject,
        issuer=a.actor.issuer,
        name=a.actor.name,
        at=a.at,
    )


def _urs(u: UrsMissed) -> ProtocolUrs:
    return ProtocolUrs(
        doc=u.doc,
        rev=u.rev,
        numbers=u.numbers,
        missed=[
            MissedNumberView(
                number=m.number,
                page=m.page,
                disposition=None if m.disposition is None else _disposition(m.disposition),
                dispositions=[_disposition(a) for a in m.dispositions],
                blocking=m.blocking,
            )
            for m in u.missed
        ],
        unquoted=list(u.unquoted),
    )


def _row(r: ProtocolRow) -> ProtocolRowView:
    req = r.requirement
    stage, witness_required = (
        attributes.current(r.step_attributes) if r.kind == "test_step" else (None, False)
    )
    return ProtocolRowView(
        requirement=req.id,
        text=req.text,
        source=req.source,
        coverage=proposal_view(r.coverage),
        decided_class=r.decided_class,
        kind=r.kind,
        evidence=req.evidence if r.kind == "vendor_reference" else (),
        test_step=_row_step(r),
        drafts=[_draft(d) for d in r.drafts],
        written=[_version(v) for v in r.written],
        prefill=_prefill(r),
        blockers=list(r.blockers),
        stage=stage,
        witness_required=witness_required,
        step_source=r.source,
        candidates=[_candidate(c) for c in r.candidates],
        findings=[_finding(f) for f in r.findings],
        changed=r.changed,
    )


def _item(b: submission.Blocking) -> ChecklistItem:
    return ChecklistItem(
        check=b.check,
        count=b.count,
        requirements=list(b.requirements),
        numbers=[MissedKey(doc=d, rev=r, number=n) for d, r, n in b.numbers],
        steps=list(b.steps),
    )


def _submission(
    x: submission.Submission,
    p: lifecycle.AssembledProtocol,
    sigs: dict[int, audit.ElectronicSignature],
) -> SubmissionView:
    """``outcome`` signatures are checked against the hash recomputed from ``frozen_copy``."""
    after = (e for e in p.events if e.id > x.event_id and e.event in ("approved", "returned"))
    outcome = next(after, None)
    return SubmissionView(
        event_id=x.event_id,
        hash=x.hash,
        at=x.at,
        frozen_copy=x.copy,
        outcome=(
            None
            if outcome is None
            else _event(
                outcome,
                sigs.get(outcome.id),
                x.recomputed_hash if outcome.event == "approved" else None,
            )
        ),
    )


def create_router(
    runs: Path,
    db: Engine | None,
    principal: Callable[..., Principal],
    *,
    fresh_auth: Callable[[Principal], Principal],
) -> APIRouter:
    """``db``: the database as the application role; none with default settings, when
    ``principal`` refuses every request."""
    router = APIRouter()

    def database() -> Engine:
        if db is None:  # unreachable: without a database no token is accepted
            raise HTTPException(401, "no database is configured")
        return db

    def check_of(session: Session, run_id: str) -> Completeness | None:
        return missed.check_for_run(session, run_id, find_run(runs, run_id))

    def view(session: Session, p: lifecycle.AssembledProtocol) -> ProtocolView:
        draft = p.status == "draft"
        rows = rows_of(session, p) if draft else None
        urs = missed.missed_of(session, p.id, check_of(session, p.run_id)) if draft else None
        raw_subs = submission.submissions_of(session, p.id)
        sigs = audit.signatures_by_protocol_events(session, [e.id for e in p.events])
        sub_hashes = {s.event_id: s.recomputed_hash for s in raw_subs}
        submissions = [_submission(x, p, sigs) for x in raw_subs]
        frozen = p.status in ("submitted", "approved") and bool(submissions)
        event_views: list[ProtocolEvent] = []
        last_sub_hash: str | None = None
        for e in p.events:
            if e.event == "submitted":
                last_sub_hash = sub_hashes.get(e.id)
                expected = last_sub_hash
            elif e.event == "approved":
                expected = last_sub_hash
            else:
                expected = None
            event_views.append(_event(e, sigs.get(e.id), expected))
        listing = draft_listing(session, p)[0] if draft and p.draft is not None else None
        unresolved = () if listing is None else tuple(e.step.id for e in listing if not e.resolved)
        return ProtocolView(
            id=p.id,
            equipment=p.equipment,
            run_id=p.run_id,
            status=p.status,
            events=event_views,
            rows=None if rows is None else [_row(r) for r in rows],
            urs=None if urs is None else [_urs(u) for u in urs],
            checklist=None
            if rows is None
            else [
                _item(b)
                for b in submission.checklist(
                    rows, urs, from_draft=p.draft is not None, unresolved=unresolved
                )
            ],
            draft_hash=None if rows is None else submission.draft_hash(p, rows, urs, unresolved),
            submission=submissions[-1] if frozen else None,
            submissions=submissions,
            source=None
            if p.draft is None
            else ProtocolSource(doc=p.draft.doc, rev=p.draft.rev, sha256=p.draft.sha256),
            draft_steps=None if listing is None else [_draft_step(e) for e in listing],
        )

    @router.post("/runs/{run_id}/protocol", operation_id="startProtocol", status_code=201)
    def start_protocol(
        run_id: str,
        who: Annotated[Principal, Depends(principal)],
        body: StartProtocol | None = None,
    ) -> ProtocolView:
        """Starts the Protocol of the run's Equipment from this imported run, in Draft status,
        with its Audit Trail entry. With ``from_draft`` it starts from the Protocol Draft the
        run read: pinned to the run and the draft's document, revision and hash, and never
        re-synced (a later revision is a new run: Return or Withdraw this one and start another
        from it). Refused (409) while a Protocol of the Equipment is open (Draft or Submitted),
        once one is approved, for a run whose folder has ``drafts.json`` but which holds no
        drafted Test Step Proposals, and with ``from_draft`` for a run that read no draft. Needs
        the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "starting a Protocol needs the deciding role")
        folder = find_run(runs, run_id)
        if folder is None:
            raise HTTPException(404, f"no run {run_id}")
        try:
            with transaction(database()) as session:
                started = lifecycle.start(
                    session,
                    actor_of(who),
                    run_id,
                    drafted=(folder / DRAFTS_FILE).is_file(),
                    from_draft=body is not None and body.from_draft,
                )
                return view(session, started)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.get("/runs/{run_id}/protocol", operation_id="getProtocol")
    def get_protocol(run_id: str, who: Annotated[Principal, Depends(principal)]) -> ProtocolView:
        """The Protocol most recently started from this run: its status and every status
        change, and in Draft status its rows computed from the current decisions. Any
        signed-in role may read it."""
        with transaction(database()) as session:
            found = lifecycle.latest_of_run(session, run_id)
            if found is None:
                raise HTTPException(404, f"no Protocol was started from run {run_id}")
            return view(session, found)

    def reread(session: Session, protocol_id: int) -> ProtocolView:
        found = lifecycle.get(session, protocol_id)
        if found is None:  # just written under its lock: never
            raise lifecycle.NotFound(f"no Protocol {protocol_id}")
        return view(session, found)

    @router.post(
        "/protocols/{protocol_id}/test-steps/{requirement}",
        operation_id="writeTestStep",
        status_code=201,
    )
    def write_test_step(
        protocol_id: int,
        requirement: str,
        body: NewWrittenVersion,
        who: Annotated[Principal, Depends(principal)],
    ) -> ProtocolView:
        """Adds a version of the requirement's written Test Step in a Protocol in Draft
        status: its full content (the Acceptance Criterion a range, number, one of or
        present; never free text), or a removal (``test_step`` ``null``). No Reason for
        Change; every version is kept, with its Audit Trail entry. Refused (409) unless the
        Protocol is in Draft status, while a drafted Test Step of the requirement is
        accepted, and for a removal with nothing to remove. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "writing a Test Step needs the deciding role")
        try:
            with transaction(database()) as session:
                written.write(session, actor_of(who), protocol_id, requirement, body.test_step)
                return reread(session, protocol_id)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.post(
        "/protocols/{protocol_id}/drafts/{proposal_id}/edit",
        operation_id="editDraftedTestStep",
        status_code=201,
    )
    def edit_drafted_test_step(
        protocol_id: int,
        proposal_id: int,
        body: DraftEdit,
        who: Annotated[Principal, Depends(principal)],
    ) -> ProtocolView:
        """Edits a drafted Test Step of the Protocol's run, in one transaction: the
        ``edited`` decision with its Reason for Change, and a version of the written Test
        Step with the draft it came from, each with its Audit Trail entry. This is the only
        way to record ``edited`` on a drafted Test Step. Refused (409) unless the Protocol is
        in Draft status, and while the requirement holds a written Test Step or another of
        its drafts is accepted. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "editing a drafted Test Step needs the deciding role")
        try:
            with transaction(database()) as session:
                written.edit(
                    session, actor_of(who), protocol_id, proposal_id, body.reason, body.test_step
                )
                return reread(session, protocol_id)
        except (lifecycle.NotFound, decisions.NotInRun) as e:
            raise HTTPException(404, str(e)) from e
        except decisions.Refused as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.post(
        "/protocols/{protocol_id}/missed-numbers",
        operation_id="decideMissedNumber",
        status_code=201,
    )
    def decide_missed_number(
        protocol_id: int, body: MissedDisposition, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolView:
        """Records the disposition of a printed requirement number the Protocol's run missed,
        in a Protocol in Draft status: ``not_a_requirement`` or ``not_tested_here``, with a
        non-blank justification (422 without one), and its Audit Trail entry. A later one
        replaces it; every one is kept. 404 for a number the run's completeness check did not
        miss, or one in a URS checked ``not_applicable``; 409 unless the Protocol is in Draft
        status. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "recording a disposition needs the deciding role")
        try:
            with transaction(database()) as session:
                found = lifecycle.get(session, protocol_id)
                missed.dispose(
                    session,
                    actor_of(who),
                    protocol_id,
                    None if found is None else check_of(session, found.run_id),
                    (body.doc, body.rev, body.number),
                    body.kind,
                    body.justification,
                )
                return reread(session, protocol_id)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Refused as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.post("/protocols/{protocol_id}/submit", operation_id="submitProtocol")
    def submit_protocol(
        protocol_id: int, body: SubmitRequest, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolView:
        """Submits a Protocol in Draft status that no check blocks; the submitter becomes its
        Preparer. Stores the frozen copy and its hash in the ``submitted`` event, with its
        Audit Trail entry; from then on the Protocol shows that copy, and written Test Steps
        and missed-number dispositions are refused. Refused (409) unless in Draft status, and
        while any check of ``checklist`` blocks (the reason lists them with their counts), and
        when ``expected_draft_hash`` is not the ``draft_hash`` of the draft now (another
        decider changed it after the Preparer read it); 422 without one. Needs the deciding
        role."""
        if not who.may_decide:
            raise HTTPException(403, "submitting a Protocol needs the deciding role")
        who = fresh_auth(who)
        try:
            with transaction(database()) as session:
                found = lifecycle.get(session, protocol_id)
                done = submission.submit(
                    session,
                    actor_of(who),
                    protocol_id,
                    None if found is None else check_of(session, found.run_id),
                    body.expected_draft_hash,
                    auth_time=who.auth_time,
                    jti=who.jti,
                    is_demo=who.is_demo,
                )
                return view(session, done)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except audit.SignatureAuthRequired as e:
            raise reauthentication_required(str(e)) from e
        except (lifecycle.Conflict, audit.SignatureReplayConflict) as e:
            raise HTTPException(409, str(e)) from e

    @router.post("/protocols/{protocol_id}/withdraw", operation_id="withdrawProtocol")
    def withdraw_protocol(
        protocol_id: int, body: Withdrawal, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolView:
        """Withdraws a Protocol in Draft status, with a reason and its Audit Trail entry, so
        a new Protocol of the Equipment can be started. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "withdrawing a Protocol needs the deciding role")
        try:
            with transaction(database()) as session:
                done = lifecycle.withdraw(session, actor_of(who), protocol_id, body.reason)
                return view(session, done)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Refused as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.post(
        "/protocols/{protocol_id}/approve",
        operation_id="approveProtocol",
        description=f"""Approves a Submitted Protocol: {approval.APPROVAL_NOTE}. Bound to the
submission the Approver read: ``submission_event_id`` and ``hash`` must be the current
submission's, else 409 (a resubmission after a return has the same hash but a new event id).
Refused (409) for the Preparer and for anyone the frozen copy records as an author: of a
decision in force (Coverage, and every current decision on a drafted Test Step, rejections
included), or of any version of a written Test Step or of a disposition of a missed number;
the check reads the copy only. Refused (409) unless Submitted. Once approved, no new
Protocol of the Equipment can be started (a new version is step 6). With its Audit Trail
entry. Needs the approving role.""",
    )
    def approve_protocol(
        protocol_id: int, body: Approval, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolView:
        if not who.may_approve:
            raise HTTPException(403, "approving a Protocol needs the approving role")
        who = fresh_auth(who)
        try:
            with transaction(database()) as session:
                done = approval.approve(
                    session,
                    actor_of(who),
                    protocol_id,
                    body.submission_event_id,
                    body.hash,
                    auth_time=who.auth_time,
                    jti=who.jti,
                    is_demo=who.is_demo,
                )
                return view(session, done)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except audit.SignatureAuthRequired as e:
            raise reauthentication_required(str(e)) from e
        except (lifecycle.Conflict, audit.SignatureReplayConflict) as e:
            raise HTTPException(409, str(e)) from e

    @router.post("/protocols/{protocol_id}/return", operation_id="returnProtocol")
    def return_protocol(
        protocol_id: int, body: Return, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolView:
        """Returns a Submitted Protocol to Draft with a reason (422 without one) and its Audit
        Trail entry. It reads the current decisions again; the returned copy stays readable in
        ``submissions``. Refused (409) unless Submitted. Needs the approving role."""
        if not who.may_approve:
            raise HTTPException(403, "returning a Protocol needs the approving role")
        try:
            with transaction(database()) as session:
                done = approval.return_to_draft(session, actor_of(who), protocol_id, body.reason)
                return view(session, done)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Refused as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.put(
        "/protocols/{protocol_id}/rows/{requirement}/attributes",
        operation_id="setRowAttributes",
    )
    def set_row_attributes(
        protocol_id: int,
        requirement: str,
        body: StepAttributesUpdate,
        who: Annotated[Principal, Depends(principal)],
    ) -> ProtocolView:
        """Sets ``stage`` (``IQ``, ``OQ``, or ``null``) and ``witness_required`` on a Test Step
        row of a Protocol in Draft status, appending a new version and an Audit Trail entry.
        Refused (409) unless the Protocol is in Draft status and the row is a ``test_step`` row.
        Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "setting step attributes needs the deciding role")
        try:
            with transaction(database()) as session:
                attributes.set_attributes(
                    session,
                    actor_of(who),
                    protocol_id,
                    requirement,
                    body.stage,
                    body.witness_required,
                )
                return reread(session, protocol_id)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.put(
        "/protocols/{protocol_id}/draft-steps/{step}/mapping",
        operation_id="mapDraftStep",
    )
    def map_draft_step(
        protocol_id: int,
        step: str,
        body: DraftMapping,
        who: Annotated[Principal, Depends(principal)],
    ) -> ProtocolView:
        """Maps a Test Step of the pinned Protocol Draft to exactly one requirement of the
        run, when the draft's traceability table maps it to none or to several or the citation
        check dropped it; until then it is listed and unusable. Every mapping is kept with its
        author (the Approver may be none of them), and the latest counts; it does not carry
        over to another Protocol. Refused (409) unless the Protocol is in Draft status and was
        started from the draft, for a step the table maps to exactly one requirement, and
        while the step is edited into a written Test Step of this Protocol; 404 for an unknown
        step or requirement. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "mapping a draft Test Step needs the deciding role")
        try:
            with transaction(database()) as session:
                draft_source.map_step(session, actor_of(who), protocol_id, step, body.requirement)
                return reread(session, protocol_id)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    @router.post(
        "/protocols/{protocol_id}/findings/{proposal_id}/reason",
        operation_id="giveFindingReason",
        status_code=201,
    )
    def give_finding_reason(
        protocol_id: int,
        proposal_id: int,
        body: FindingReason,
        who: Annotated[Principal, Depends(principal)],
    ) -> ProtocolView:
        """Records why the row of a finding accepted on its content is submitted as it is: a
        non-blank written reason (422 without one), every version kept with its author, the
        latest counting. Needed to submit a row whose Test Step is not written in this
        Protocol. Refused (409) unless the Protocol is in Draft status and was started from the
        draft, and for a finding not accepted; 404 for a finding the run does not hold. Needs
        the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "giving a reason needs the deciding role")
        try:
            with transaction(database()) as session:
                draft_source.give_reason(
                    session, actor_of(who), protocol_id, proposal_id, body.reason
                )
                return reread(session, protocol_id)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Refused as e:
            raise HTTPException(422, str(e)) from e
        except lifecycle.Conflict as e:
            raise HTTPException(409, str(e)) from e

    return router
