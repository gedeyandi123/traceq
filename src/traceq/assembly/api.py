"""The routes of the Protocol assembled in TraceQ (spec #247, "API"): start the Protocol of a
run's Equipment, read the Protocol of a run, add a version of a written Test Step, edit a
drafted Test Step, decide a printed requirement number the run missed, submit a Protocol in
Draft status, withdraw one.

Every route needs a valid bearer token; every write needs the deciding role, so the
Audit Trail names who did it. Reading is open to any signed-in role. Accepting and rejecting a
drafted Test Step go through ``recordDecision``. Errors: 401 without a token, 403 without the
role, 404 unknown, 409 for a refused state change with the reason in words.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from traceq.assembly import lifecycle, missed, submission, written
from traceq.assembly.lifecycle import EventKind, Status
from traceq.assembly.missed import MissedKind, UrsMissed
from traceq.assembly.rows import (
    Blocker,
    DraftOfRow,
    PrefillOrigin,
    ProtocolRow,
    RowKind,
    rows_of,
)
from traceq.assembly.submission import Check, ProtocolCopy
from traceq.assembly.written import Acceptance, WrittenContent, WrittenVersion
from traceq.db import transaction
from traceq.identity import Principal
from traceq.proposals import decisions
from traceq.proposals.api import Proposal, actor_of, proposal_view
from traceq.runs.api import DRAFTS_FILE, find_run
from traceq.runs.schemas import Cite, Completeness, DraftedTestStep, EvidenceStep, UnquotedText
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
    Step is an accepted draft whose Acceptance Criterion is missing or free text)."""


# The spec calls a human's ruling on a missed number its "answer"; the API names it a
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


class SubmissionView(_Model):
    """A submission of the Protocol: the frozen copy it stored and that copy's hash."""

    event_id: int
    """The ``submitted`` event; approving names it, with the hash."""
    hash: str
    """The SHA-256 of the copy's canonical JSON (keys sorted, no spaces, UTF-8)."""
    at: datetime
    frozen_copy: ProtocolCopy
    """Every row, its decisions in force and who made them, its Test Step and every version
    of its written one; the missed numbers with their dispositions; the unquoted text."""


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
    submission: SubmissionView | None
    """While Submitted or Approved: the current submission, which the page shows instead of
    live rows. ``null`` in any other status."""
    submissions: list[SubmissionView]
    """Every submission, oldest first: those before the current one were returned to Draft."""


class Withdrawal(_Model):
    reason: str
    """Why the Protocol is given up."""


class NewWrittenVersion(_Model):
    """A version of a requirement's written Test Step. No Reason for Change."""

    test_step: WrittenContent | None
    """The full content; ``null`` removes the written Test Step."""


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


class DraftEdit(_Model):
    """An edit of a drafted Test Step: the ``edited`` decision and the Test Step it gives."""

    reason: str
    """The Reason for Change of the ``edited`` decision."""
    test_step: WrittenContent
    """The Test Step as edited, saved as a version of the written Test Step."""


def _event(e: lifecycle.Event) -> ProtocolEvent:
    return ProtocolEvent(
        id=e.id,
        event=e.event,
        status=e.status,
        reason=e.reason,
        subject=e.actor.subject,
        issuer=e.actor.issuer,
        name=e.actor.name,
        at=e.at,
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


def _written_step(v: WrittenVersion) -> RowTestStep:
    c = v.content
    assert c is not None  # the step in force is never a removal
    return RowTestStep(
        origin="written",
        proposal_id=v.from_proposal_id,
        version=v.version,
        description=c.description,
        method=c.method,
        instrument=c.instrument,
        acceptance=c.acceptance,
        acceptance_flag=None,
    )


def _row_step(r: ProtocolRow) -> RowTestStep | None:
    if r.written_step is not None:
        return _written_step(r.written_step)
    return None if r.test_step is None else _test_step(r.test_step)


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


def _test_step(d: DraftOfRow) -> RowTestStep:
    s = d.draft
    return RowTestStep(
        origin="accepted_draft",
        proposal_id=d.standing.proposal_id,
        version=None,
        description=s.description,
        method=s.method,
        instrument=s.instrument,
        acceptance=s.acceptance,
        acceptance_flag=s.acceptance_flag,
    )


def _disposition(a: missed.Answer) -> MissedDispositionView:
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
                disposition=None if m.answer is None else _disposition(m.answer),
                dispositions=[_disposition(a) for a in m.answers],
                blocking=m.blocking,
            )
            for m in u.missed
        ],
        unquoted=list(u.unquoted),
    )


def _row(r: ProtocolRow) -> ProtocolRowView:
    req = r.requirement
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
    )


def _item(b: submission.Blocking) -> ChecklistItem:
    return ChecklistItem(
        check=b.check,
        count=b.count,
        requirements=list(b.requirements),
        numbers=[MissedKey(doc=d, rev=r, number=n) for d, r, n in b.numbers],
    )


def _submission(x: submission.Submission) -> SubmissionView:
    return SubmissionView(event_id=x.event_id, hash=x.hash, at=x.at, frozen_copy=x.copy)


def create_router(runs: Path, db: Engine | None, principal: Callable[..., Principal]) -> APIRouter:
    """``db``: the database as the application role; none with default settings, when
    ``principal`` refuses every request."""
    router = APIRouter()

    def database() -> Engine:
        if db is None:  # unreachable: without a database no token is accepted
            raise HTTPException(401, "no database is configured")
        return db

    def check_of(run_id: str) -> Completeness | None:
        return missed.check_of(find_run(runs, run_id))

    def view(session: Session, p: lifecycle.AssembledProtocol) -> ProtocolView:
        draft = p.status == "draft"
        rows = rows_of(session, p) if draft else None
        urs = missed.missed_of(session, p.id, check_of(p.run_id)) if draft else None
        submissions = [_submission(x) for x in submission.submissions_of(session, p.id)]
        frozen = p.status in ("submitted", "approved") and bool(submissions)
        return ProtocolView(
            id=p.id,
            equipment=p.equipment,
            run_id=p.run_id,
            status=p.status,
            events=[_event(e) for e in p.events],
            rows=None if rows is None else [_row(r) for r in rows],
            urs=None if urs is None else [_urs(u) for u in urs],
            checklist=None if rows is None else [_item(b) for b in submission.checklist(rows, urs)],
            submission=submissions[-1] if frozen else None,
            submissions=submissions,
        )

    @router.post("/runs/{run_id}/protocol", operation_id="startProtocol", status_code=201)
    def start_protocol(run_id: str, who: Annotated[Principal, Depends(principal)]) -> ProtocolView:
        """Starts the Protocol of the run's Equipment from this imported run, in Draft status,
        with its Audit Trail entry. Refused (409) while a Protocol of the Equipment is open
        (Draft or Submitted), once one is approved, and for a run whose folder has
        ``drafts.json`` but which holds no drafted Test Step Proposals. Needs the deciding
        role."""
        if not who.may_decide:
            raise HTTPException(403, "starting a Protocol needs the deciding role")
        folder = find_run(runs, run_id)
        if folder is None:
            raise HTTPException(404, f"no run {run_id}")
        try:
            with transaction(database()) as session:
                started = lifecycle.start(
                    session, actor_of(who), run_id, drafted=(folder / DRAFTS_FILE).is_file()
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
        assert found is not None  # just written under its lock
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
            raise HTTPException(403, "answering a missed number needs the deciding role")
        try:
            with transaction(database()) as session:
                found = lifecycle.get(session, protocol_id)
                missed.answer(
                    session,
                    actor_of(who),
                    protocol_id,
                    None if found is None else check_of(found.run_id),
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
        protocol_id: int, who: Annotated[Principal, Depends(principal)]
    ) -> ProtocolView:
        """Submits a Protocol in Draft status that no check blocks; the submitter becomes its
        Preparer. Stores the frozen copy and its hash in the ``submitted`` event, with its
        Audit Trail entry; from then on the Protocol shows that copy, and written Test Steps
        and missed-number dispositions are refused. Refused (409) unless in Draft status, and
        while any check of ``checklist`` blocks (the reason lists them with their counts).
        Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "submitting a Protocol needs the deciding role")
        try:
            with transaction(database()) as session:
                found = lifecycle.get(session, protocol_id)
                done = submission.submit(
                    session,
                    actor_of(who),
                    protocol_id,
                    None if found is None else check_of(found.run_id),
                )
                return view(session, done)
        except lifecycle.NotFound as e:
            raise HTTPException(404, str(e)) from e
        except lifecycle.Conflict as e:
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

    return router
