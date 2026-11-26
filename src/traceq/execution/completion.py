"""Completing an Execution: blocking checklist, frozen copy and its SHA-256 hash (ADR 0013,
spec #270, #275).

An Execution completes when every Test Step row has at least one Result (attempt) and every
Deviation is Closed. Vendor Reference rows never block, a row whose latest attempt failed does not
block once its Deviations are Closed, and no Witness confirmation is required. On completion, one
canonical JSON document of the Execution and its SHA-256 ``copy_hash`` are stored in
``execution_completions`` alongside the ``completed`` event and Audit Trail entry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, DateTime, MetaData, Table, Text, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly.attributes import Stage
from traceq.assembly.submission import Author, FrozenRow, ProtocolCopy
from traceq.assembly.written import Acceptance
from traceq.execution import lifecycle, results
from traceq.execution.deviations import recomputed_closure_hash
from traceq.execution.lifecycle import EVENTS, Conflict, NotFound
from traceq.execution.results import (
    Attempt,
    AttemptVersion,
    Deviation,
    DeviationCause,
    DeviationClass,
    DeviationEvent,
    DeviationEventKind,
    DeviationInvestigation,
    DeviationStatus,
    InstrumentInput,
    OutcomeKind,
    ResultValue,
    Verdict,
    WitnessConfirmation,
)
from traceq.proposals.keys import digest
from traceq.runs.schemas import Cite, EvidenceStep

_META = MetaData()
COMPLETIONS = Table(
    "execution_completions",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("execution_id", BigInteger),
    Column("event_id", BigInteger),
    Column("frozen_copy", JSONB),
    Column("copy_hash", Text),
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Blockers -------------------------------------------------------------------------


class RowsWithoutResultBlocker(_Frozen):
    """Test Step rows that still have no recorded Result (attempts empty)."""

    count: int
    requirements: tuple[str, ...]


class OpenDeviationBlockerItem(_Frozen):
    """One Deviation that is not yet Closed (``open`` or ``submitted``)."""

    deviation_number: int
    status: DeviationStatus


class OpenDeviationsBlocker(_Frozen):
    """Deviations that are not yet Closed."""

    count: int
    items: tuple[OpenDeviationBlockerItem, ...]


class UnconfirmedWitnessBlocker(_Frozen):
    """Test Step rows requiring Witness whose latest attempt lacks an active Witness."""

    count: int
    requirements: tuple[str, ...]


class CompletionBlockers(_Frozen):
    """Blocking checklist computed for every Execution view."""

    blocked: bool
    rows_without_result: RowsWithoutResultBlocker
    open_deviations: OpenDeviationsBlocker
    unconfirmed_witness_rows: UnconfirmedWitnessBlocker


def compute_blockers(
    copy: ProtocolCopy,
    attempts_by_req: dict[str, tuple[Attempt, ...]],
    deviations_list: Sequence[Deviation],
) -> CompletionBlockers:
    """Computes completion blockers in Protocol row order and Deviation number order."""
    missing_rows = tuple(
        r.requirement
        for r in copy.rows
        if r.kind == "test_step" and not attempts_by_req.get(r.requirement)
    )
    open_devs = tuple(
        OpenDeviationBlockerItem(deviation_number=d.deviation_number, status=d.status)
        for d in sorted(deviations_list, key=lambda item: item.deviation_number)
        if d.status != "closed"
    )
    unconfirmed_witness: list[str] = []
    for r in copy.rows:
        if r.kind != "test_step" or r.test_step is None or not r.test_step.witness_required:
            continue
        attempts = attempts_by_req.get(r.requirement)
        if attempts:
            latest_ver = attempts[-1].latest
            if not any(not w.voided for w in latest_ver.witness_confirmations):
                unconfirmed_witness.append(r.requirement)
    unconfirmed_tuple = tuple(unconfirmed_witness)
    return CompletionBlockers(
        blocked=bool(missing_rows or open_devs or unconfirmed_tuple),
        rows_without_result=RowsWithoutResultBlocker(
            count=len(missing_rows),
            requirements=missing_rows,
        ),
        open_deviations=OpenDeviationsBlocker(
            count=len(open_devs),
            items=open_devs,
        ),
        unconfirmed_witness_rows=UnconfirmedWitnessBlocker(
            count=len(unconfirmed_tuple),
            requirements=unconfirmed_tuple,
        ),
    )


# --- Frozen copy ----------------------------------------------------------------------


class FrozenExecutionTestStep(_Frozen):
    """The Test Step of a Test Step row from the Approved Protocol's frozen copy."""

    origin: Literal["accepted_draft", "written"]
    description: str
    method: str
    instrument: str | None
    acceptance: Acceptance
    stage: Stage | None = None
    witness_required: bool = False


class FrozenWitnessConfirmation(_Frozen):
    """One Witness confirmation bound to an attempt version's hash."""

    id: int
    recorded_at: datetime
    version_id: int
    version_hash: str
    witness: Author
    voided: bool
    note: str
    electronic_signature: audit.ElectronicSignatureView | None = None


class FrozenAttemptVersion(_Frozen):
    """One immutable version of an attempt's Result."""

    id: int
    version: int
    outcome_kind: OutcomeKind
    not_performable_reason: str | None
    value: ResultValue | None
    observation: str | None
    instruments: tuple[InstrumentInput, ...]
    no_calibrated_instrument_reason: str | None
    evidence_references: tuple[str, ...]
    verdict: Verdict
    version_hash: str
    performer: Author
    recorded_at: datetime
    reason_for_change: str | None
    witness_confirmations: tuple[FrozenWitnessConfirmation, ...]


class FrozenAttempt(_Frozen):
    """One attempt on a Test Step row, with its versions oldest first."""

    id: int
    attempt_number: int
    performer: Author
    recorded_at: datetime
    versions: tuple[FrozenAttemptVersion, ...]
    retest_deviation_id: int | None = None
    retest_reason: str | None = None


class FrozenExecutionRow(_Frozen):
    """One row of the completed Execution, in Protocol order."""

    requirement: str
    text: str
    source: Cite
    kind: Literal["vendor_reference", "test_step"]
    evidence: tuple[EvidenceStep, ...]
    test_step: FrozenExecutionTestStep | None
    attempts: tuple[FrozenAttempt, ...]


class FrozenDeviationEvent(_Frozen):
    """One status event on a Deviation."""

    id: int
    at: datetime
    event: DeviationEventKind
    status: DeviationStatus
    reason: str | None
    actor: Author
    electronic_signature: audit.ElectronicSignatureView | None = None


class FrozenDeviationInvestigation(_Frozen):
    """One immutable version of a Deviation's Investigation."""

    id: int
    at: datetime
    version: int
    investigation: str
    deviation_class: DeviationClass
    capa: str | None
    reason_for_change: str | None
    actor: Author


class FrozenDeviation(_Frozen):
    """One Deviation of the completed Execution, in deviation_number order."""

    id: int
    deviation_number: int
    description: str
    deviation_class: DeviationClass | None
    requirement: str | None
    attempt_id: int | None
    cause: DeviationCause
    status: DeviationStatus
    opener: Author
    opened_at: datetime
    investigations: tuple[FrozenDeviationInvestigation, ...]
    events: tuple[FrozenDeviationEvent, ...]


class ExecutionCopy(_Frozen):
    """The canonical frozen copy of a completed Execution (ADR 0013, spec #275)."""

    execution_id: int
    protocol_id: int
    equipment: str
    run_id: str
    submission_event_id: int
    submission_hash: str
    completed_event_id: int
    completed_at: datetime
    completer: Author
    rows: tuple[FrozenExecutionRow, ...]
    deviations: tuple[FrozenDeviation, ...]


def _author(a: audit.Actor) -> Author:
    return Author(subject=a.subject, issuer=a.issuer, name=a.name)


def _utc(at: datetime) -> datetime:
    """Normalises timestamps to UTC so session timezone never alters the canonical hash."""
    return at.astimezone(UTC)


def _frozen_witness(
    w: WitnessConfirmation, recomputed_version_hash: str, sig: audit.ElectronicSignature | None
) -> FrozenWitnessConfirmation:
    return FrozenWitnessConfirmation(
        id=w.id,
        recorded_at=_utc(w.at),
        version_id=w.version_id,
        version_hash=w.version_hash,
        witness=_author(w.actor),
        voided=w.voided,
        note=audit.signature_label(sig),
        electronic_signature=audit.signature_view(
            sig, verified=audit.verified_against(sig, recomputed_version_hash)
        ),
    )


def _frozen_version(
    a: Attempt, v: AttemptVersion, witness_sigs: dict[int, audit.ElectronicSignature]
) -> FrozenAttemptVersion:
    recomputed = results.recomputed_version_hash(a, v)
    return FrozenAttemptVersion(
        id=v.id,
        version=v.version,
        outcome_kind=v.outcome_kind,
        not_performable_reason=v.not_performable_reason,
        value=v.value,
        observation=v.observation,
        instruments=v.instruments,
        no_calibrated_instrument_reason=v.no_calibrated_instrument_reason,
        evidence_references=v.evidence,
        verdict=v.verdict,
        version_hash=v.version_hash,
        performer=_author(v.actor),
        recorded_at=_utc(v.at),
        reason_for_change=v.reason_for_change,
        witness_confirmations=tuple(
            _frozen_witness(w, recomputed, witness_sigs.get(w.id)) for w in v.witness_confirmations
        ),
    )


def _frozen_attempt(
    a: Attempt, witness_sigs: dict[int, audit.ElectronicSignature]
) -> FrozenAttempt:
    return FrozenAttempt(
        id=a.id,
        attempt_number=a.attempt_number,
        performer=_author(a.actor),
        recorded_at=_utc(a.at),
        versions=tuple(_frozen_version(a, v, witness_sigs) for v in a.versions),
        retest_deviation_id=a.retest_deviation_id,
        retest_reason=a.retest_reason,
    )


def _frozen_row(
    r: FrozenRow,
    attempts: tuple[Attempt, ...],
    witness_sigs: dict[int, audit.ElectronicSignature],
) -> FrozenExecutionRow:
    step = r.test_step
    return FrozenExecutionRow(
        requirement=r.requirement,
        text=r.text,
        source=r.source,
        kind=r.kind,
        evidence=r.evidence,
        test_step=None
        if step is None
        else FrozenExecutionTestStep(
            origin=step.origin,
            description=step.description,
            method=step.method,
            instrument=step.instrument,
            acceptance=step.acceptance,
            stage=step.stage,
            witness_required=step.witness_required,
        ),
        attempts=tuple(_frozen_attempt(a, witness_sigs) for a in attempts),
    )


def _frozen_dev_event(
    d: Deviation, e: DeviationEvent, sig: audit.ElectronicSignature | None
) -> FrozenDeviationEvent:
    recomputed = None if sig is None else recomputed_closure_hash(d, e.id)
    return FrozenDeviationEvent(
        id=e.id,
        at=_utc(e.at),
        event=e.event,
        status=e.status,
        reason=e.reason,
        actor=_author(e.actor),
        electronic_signature=audit.signature_view(
            sig, verified=audit.verified_against(sig, recomputed)
        ),
    )


def _frozen_dev_investigation(inv: DeviationInvestigation) -> FrozenDeviationInvestigation:
    return FrozenDeviationInvestigation(
        id=inv.id,
        at=_utc(inv.at),
        version=inv.version,
        investigation=inv.investigation,
        deviation_class=inv.deviation_class,
        capa=inv.capa,
        reason_for_change=inv.reason_for_change,
        actor=_author(inv.actor),
    )


def _frozen_deviation(
    d: Deviation, dev_sigs: dict[int, audit.ElectronicSignature]
) -> FrozenDeviation:
    return FrozenDeviation(
        id=d.id,
        deviation_number=d.deviation_number,
        description=d.description,
        deviation_class=d.deviation_class,
        requirement=d.requirement,
        attempt_id=d.attempt_id,
        cause=d.cause,
        status=d.status,
        opener=_author(d.actor),
        opened_at=_utc(d.at),
        investigations=tuple(_frozen_dev_investigation(inv) for inv in d.investigations),
        events=tuple(_frozen_dev_event(d, e, dev_sigs.get(e.id)) for e in d.events),
    )


def hash_of(copy: ExecutionCopy) -> str:
    """The SHA-256 of the Execution copy's canonical JSON."""
    return digest(copy.model_dump(mode="json"))


@dataclass(frozen=True)
class Completion:
    """The stored frozen copy and SHA-256 hash of a completed Execution."""

    id: int
    at: datetime
    execution_id: int
    event_id: int
    copy: ExecutionCopy
    copy_hash: str


def get_completion(session: Session, execution_id: int) -> Completion | None:
    """Reads the stored completion record for ``execution_id``, or ``None`` if not completed."""
    row = (
        session.execute(
            select(
                COMPLETIONS.c.id,
                COMPLETIONS.c.at,
                COMPLETIONS.c.execution_id,
                COMPLETIONS.c.event_id,
                COMPLETIONS.c.frozen_copy,
                COMPLETIONS.c.copy_hash,
            ).where(COMPLETIONS.c.execution_id == execution_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return Completion(
        id=row["id"],
        at=row["at"],
        execution_id=row["execution_id"],
        event_id=row["event_id"],
        copy=ExecutionCopy.model_validate(row["frozen_copy"]),
        copy_hash=row["copy_hash"],
    )


def _format_blockers(blockers: CompletionBlockers) -> str:
    parts: list[str] = []
    if blockers.rows_without_result.count:
        reqs = ", ".join(blockers.rows_without_result.requirements)
        parts.append(f"rows_without_result ({blockers.rows_without_result.count}: {reqs})")
    if blockers.open_deviations.count:
        devs = ", ".join(
            f"#{d.deviation_number} ({d.status})" for d in blockers.open_deviations.items
        )
        parts.append(f"open_deviations ({blockers.open_deviations.count}: {devs})")
    if blockers.unconfirmed_witness_rows.count:
        reqs = ", ".join(blockers.unconfirmed_witness_rows.requirements)
        parts.append(
            f"unconfirmed_witness_rows ({blockers.unconfirmed_witness_rows.count}: {reqs})"
        )
    return "; ".join(parts)


def complete_execution(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
) -> Completion:
    """Completes an ``in_progress`` Execution under the per-Execution advisory lock (namespace 4).

    Refuses (409) if the Execution is already ``completed``, if any Test Step row has no Result,
    or if any Deviation is not ``closed``. Stores the frozen copy and its SHA-256 ``copy_hash``
    in ``execution_completions`` and appends the Audit Trail entry in the same transaction.
    """
    lifecycle.lock_execution(session, execution_id)
    ex = lifecycle.get(session, execution_id)
    if ex is None:
        raise NotFound(f"no Execution {execution_id}")
    if ex.status != "in_progress":
        raise Conflict(
            f"Execution {execution_id} is {ex.status}: only an In progress Execution can be"
            " completed"
        )

    protocol_copy = results.frozen_copy(session, ex)
    attempts_by_req = results.attempts_of(session, execution_id)
    deviations_list = sorted(
        results.deviations_of(session, execution_id),
        key=lambda d: d.deviation_number,
    )
    blockers = compute_blockers(protocol_copy, attempts_by_req, deviations_list)
    if blockers.blocked:
        raise Conflict(
            f"Execution {execution_id} cannot be completed while blocked: "
            f"{_format_blockers(blockers)}"
        )

    ev_row = (
        session.execute(
            insert(EVENTS)
            .values(
                execution_id=execution_id,
                event="completed",
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*EVENTS.c)
        )
        .mappings()
        .one()
    )
    witness_ids = [
        w.id
        for attempts in attempts_by_req.values()
        for a in attempts
        for v in a.versions
        for w in v.witness_confirmations
    ]
    dev_event_ids = [e.id for d in deviations_list for e in d.events]
    witness_sigs = audit.signatures_by_witness_confirmations(session, witness_ids)
    dev_sigs = audit.signatures_by_deviation_events(session, dev_event_ids)

    copy = ExecutionCopy(
        execution_id=ex.id,
        protocol_id=ex.protocol_id,
        equipment=protocol_copy.equipment,
        run_id=protocol_copy.run_id,
        submission_event_id=ex.submission_event_id,
        submission_hash=ex.submission_hash,
        completed_event_id=ev_row["id"],
        completed_at=_utc(ev_row["at"]),
        completer=_author(actor),
        rows=tuple(
            _frozen_row(r, attempts_by_req.get(r.requirement, ()), witness_sigs)
            for r in protocol_copy.rows
        ),
        deviations=tuple(_frozen_deviation(d, dev_sigs) for d in deviations_list),
    )
    copy_hash = hash_of(copy)
    comp_row = (
        session.execute(
            insert(COMPLETIONS)
            .values(
                execution_id=execution_id,
                event_id=ev_row["id"],
                frozen_copy=copy.model_dump(mode="json"),
                copy_hash=copy_hash,
            )
            .returning(COMPLETIONS.c.id, COMPLETIONS.c.at)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "execution completed",
        "execution",
        str(execution_id),
        old={"status": ex.status},
        new={
            "execution_id": execution_id,
            "protocol_id": ex.protocol_id,
            "event_id": ev_row["id"],
            "status": "completed",
            "copy_hash": copy_hash,
        },
    )
    return Completion(
        id=comp_row["id"],
        at=comp_row["at"],
        execution_id=execution_id,
        event_id=ev_row["id"],
        copy=copy,
        copy_hash=copy_hash,
    )
