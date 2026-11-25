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
reads. Submitting takes the per-Protocol lock and checks the status inside it, and has its
Audit Trail entry in the same transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle
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
from traceq.assembly.rows import ProtocolRow, rows_of, shaped, step_of
from traceq.assembly.written import Acceptance, WrittenContent, WrittenVersion
from traceq.proposals.decisions import Decision, Verdict
from traceq.proposals.keys import digest
from traceq.runs.schemas import Cite, Completeness, EvidenceStep, UnquotedText
from traceq.traceability.coverage import CoverageClass

type Check = Literal[
    "coverage_undecided",
    "draft_undecided",
    "no_test_step",
    "acceptance_not_shaped",
    "missed_undecided",
]
"""The five submission checks, in the order the page lists them. The first four are row
blockers; ``missed_undecided``: a printed number the run missed, without its disposition."""

CHECKS: tuple[Check, ...] = (
    "coverage_undecided",
    "draft_undecided",
    "no_test_step",
    "acceptance_not_shaped",
    "missed_undecided",
)


@dataclass(frozen=True)
class Blocking:
    """One submission check: the rows and the missed numbers it holds back."""

    check: Check
    requirements: tuple[str, ...]
    numbers: tuple[Key, ...]

    @property
    def count(self) -> int:
        return len(self.requirements) + len(self.numbers)


def checklist(rows: list[ProtocolRow], urs: list[UrsMissed] | None) -> list[Blocking]:
    """Every submission check, blocking or not, in ``CHECKS`` order."""
    numbers = tuple((u.doc, u.rev, m.number) for u in urs or [] for m in u.missed if m.blocking)
    return [
        Blocking(
            check,
            tuple(r.requirement.id for r in rows if check in r.blockers),
            numbers if check == "missed_undecided" else (),
        )
        for check in CHECKS
    ]


# --- The copy -------------------------------------------------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Author(_Frozen):
    """Who: the token's subject and issuer, and the name shown at the time."""

    subject: str
    issuer: str
    name: str


class FrozenDecision(_Frozen):
    """A Proposal Decision in force when the Protocol was submitted, and who made it."""

    id: int
    decision: Verdict
    coverage: CoverageClass | None
    reason: str | None
    author: Author
    at: datetime


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


def _author(a: audit.Actor) -> Author:
    return Author(subject=a.subject, issuer=a.issuer, name=a.name)


def _utc(at: datetime) -> datetime:
    """The same instant in UTC, so the session's time zone never changes the hash."""
    return at.astimezone(UTC)


def _decision(d: Decision) -> FrozenDecision:
    return FrozenDecision(
        id=d.id,
        decision=d.decision,
        coverage=d.coverage,
        reason=d.reason,
        author=_author(d.actor),
        at=_utc(d.at),
    )


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


def _test_step(r: ProtocolRow) -> FrozenTestStep | None:
    step = step_of(r)
    if step is None:
        return None
    if not shaped(step.acceptance):
        raise NotFrozen(f"the Test Step of {r.requirement.id} has no shaped Acceptance Criterion")
    return FrozenTestStep(
        origin=step.origin,
        proposal_id=step.proposal_id,
        version=step.version,
        decision=None if step.decision is None else _decision(step.decision),
        description=step.description,
        method=step.method,
        instrument=step.instrument,
        acceptance=step.acceptance,
        stage=step.stage,
        witness_required=step.witness_required,
    )


def _row(r: ProtocolRow) -> FrozenRow:
    if r.kind == "undecided" or r.decided_class is None:
        raise NotFrozen(f"the Coverage of {r.requirement.id} is not decided")
    req = r.requirement
    return FrozenRow(
        requirement=req.id,
        text=req.text,
        source=req.source,
        coverage=FrozenCoverage(
            coverage_class=r.decided_class, decision=_decision(r.coverage.decisions[0])
        ),
        kind=r.kind,
        evidence=req.evidence if r.kind == "vendor_reference" else (),
        test_step=_test_step(r),
        drafts=tuple(
            FrozenDraft(
                proposal_id=d.standing.proposal_id,
                draft_id=d.draft.id,
                decision=_decision(d.standing.decisions[0])
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


# --- Submitting -----------------------------------------------------------------------


@dataclass(frozen=True)
class Submission:
    """A ``submitted`` event: its frozen copy and hash."""

    event_id: int
    at: datetime
    copy: ProtocolCopy
    hash: str


def submissions_of(session: Session, protocol_id: int) -> list[Submission]:
    """Every submission of the Protocol, oldest first; earlier ones were returned."""
    return [
        Submission(
            event_id=m["id"],
            at=m["at"],
            copy=ProtocolCopy.model_validate(m["frozen_copy"]),
            hash=m["copy_hash"],
        )
        for m in session.execute(
            select(EVENTS.c.id, EVENTS.c.at, EVENTS.c.frozen_copy, EVENTS.c.copy_hash)
            .where(EVENTS.c.protocol_id == protocol_id, EVENTS.c.event == "submitted")
            .order_by(EVENTS.c.id)
        ).mappings()
    ]


def submit(
    session: Session, actor: audit.Actor, protocol_id: int, check: Completeness | None
) -> lifecycle.AssembledProtocol:
    """Submits a Protocol in Draft status that nothing blocks: freezes its copy and hash in
    the ``submitted`` event. ``check``: the completeness check of the Protocol's run."""
    current = lifecycle.locked(
        session, protocol_id, "draft", "only a Protocol in Draft status can be submitted"
    )
    rows = rows_of(session, current)
    urs = missed_of(session, protocol_id, check)
    blocking = [b for b in checklist(rows, urs) if b.count]
    if blocking:
        listed = ", ".join(f"{b.check} ({b.count})" for b in blocking)
        raise Conflict(f"Protocol {protocol_id} cannot be submitted while it is blocked: {listed}")
    copy = ProtocolCopy(
        protocol_id=current.id,
        equipment=current.equipment,
        run_id=current.run_id,
        preparer=_author(actor),
        rows=tuple(_row(r) for r in rows),
        urs=None if urs is None else tuple(_urs(u) for u in urs),
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
    )
    audit.append(
        session,
        actor,
        "protocol submitted",
        "protocol",
        str(protocol_id),
        old={"status": current.status},
        new={"status": done.status, "event_id": done.id, "hash": hashed},
    )
    return current.after(done)
