"""Recording Execution Results judged by code, with instruments and automatic Deviations
(ADR 0013, spec #270, #272).

Every write takes the per-Execution advisory lock (namespace 4) and re-checks ``in_progress``
status inside the transaction. The database clock stamps every row's ``at``, and instrument
calibration due dates are checked against the database's current UTC date.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    RowMapping,
    Table,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import submission
from traceq.assembly.submission import FrozenRow, FrozenTestStep, ProtocolCopy
from traceq.assembly.written import Acceptance
from traceq.execution import lifecycle
from traceq.proposals.keys import digest
from traceq.traceability.values import Number, OneOf, Range

type OutcomeKind = Literal["value", "not_performable"]
type Verdict = Literal["pass", "fail"]
type DeviationCause = Literal["failed", "no_calibrated_instrument", "manual"]
type DeviationStatus = Literal["open", "submitted", "closed"]
type DeviationEventKind = Literal["opened", "submitted", "returned", "closed"]
type DeviationClass = Literal["minor", "major", "critical"]

DEVIATION_STATUS_AFTER: dict[DeviationEventKind, DeviationStatus] = {
    "opened": "open",
    "submitted": "submitted",
    "returned": "open",
    "closed": "closed",
}

WITNESS_NOTE = "a recorded status, not an Electronic Signature (ADR 0007 phase 2)"


class InvalidResult(ValueError):
    """The Result payload is malformed or does not match the Acceptance Criterion (422)."""


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InstrumentInput(_Input):
    """One calibrated instrument used during a Test Step."""

    identifier: str
    calibration_due_date: date

    @field_validator("identifier")
    @classmethod
    def _non_blank_id(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("instrument identifier must not be blank")
        return stripped


class NumberResultValue(_Input):
    """Numeric measurement for a ``number`` or ``range`` Acceptance Criterion (no unit)."""

    type: Literal["number"] = "number"
    value: float

    @field_validator("value", mode="before")
    @classmethod
    def _finite_number(cls, v: Any) -> float:
        if isinstance(v, bool):
            raise ValueError("number value cannot be a boolean")
        f = float(v)
        if not math.isfinite(f):
            raise ValueError("number value must be finite (not inf or nan)")
        return f


class OneOfResultValue(_Input):
    """Choice for a ``one_of`` Acceptance Criterion, or ``not_one_of`` with observed text."""

    type: Literal["one_of"] = "one_of"
    value: str
    not_one_of: bool = False

    @field_validator("value")
    @classmethod
    def _non_blank_value(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("one_of value must not be blank")
        return v


class PresentResultValue(_Input):
    """Observation for a ``present`` Acceptance Criterion."""

    type: Literal["present"] = "present"
    value: StrictBool


type ResultValue = Annotated[
    NumberResultValue | OneOfResultValue | PresentResultValue,
    Field(discriminator="type"),
]


class RecordAttemptRequest(_Input):
    """Payload to record the first attempt on a Test Step row."""

    outcome_kind: OutcomeKind
    not_performable_reason: str | None = None
    value: ResultValue | None = None
    observation: str | None = None
    instruments: tuple[InstrumentInput, ...] = ()
    no_calibrated_instrument_reason: str | None = None
    evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _consistent_outcome_and_instruments(self) -> RecordAttemptRequest:
        if self.outcome_kind == "not_performable":
            if self.not_performable_reason is None or not self.not_performable_reason.strip():
                raise ValueError("not_performable requires a non-blank reason")
            if self.value is not None:
                raise ValueError("not_performable takes no value")
        else:
            if self.not_performable_reason is not None and self.not_performable_reason.strip():
                raise ValueError("value outcome takes no not_performable_reason")
            if self.value is None:
                raise ValueError("value outcome requires a value")

        has_no_inst_reason = self.no_calibrated_instrument_reason is not None and bool(
            self.no_calibrated_instrument_reason.strip()
        )
        if self.instruments and has_no_inst_reason:
            raise ValueError(
                "provide either instruments or no_calibrated_instrument_reason, not both"
            )
        return self


class CorrectAttemptRequest(RecordAttemptRequest):
    """Payload to add a new version to an existing attempt, with a required Reason for Change."""

    reason_for_change: str

    @field_validator("reason_for_change")
    @classmethod
    def _non_blank_reason_for_change(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("reason_for_change must not be blank")
        return stripped


class RetestRowRequest(RecordAttemptRequest):
    """Payload to record a Retest (new attempt) on a failed Test Step row."""

    retest_reason: str | None = None
    reason: str | None = None
    deviation_number: int | None = Field(default=None, ge=1)
    deviation_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _require_reason_and_deviation(self) -> RetestRowRequest:
        r1 = self.retest_reason.strip() if self.retest_reason is not None else ""
        r2 = self.reason.strip() if self.reason is not None else ""
        if not (r1 or r2):
            raise ValueError("retest_reason must not be blank")
        if self.deviation_number is None and self.deviation_id is None:
            raise ValueError("deviation_number or deviation_id is required")
        return self

    def effective_reason(self) -> str:
        r1 = self.retest_reason.strip() if self.retest_reason is not None else ""
        return r1 or (self.reason or "").strip()


class ConfirmWitnessRequest(_Input):
    """Payload to confirm an attempt's latest version as a Witness."""

    version_number: int = Field(ge=1)
    version_hash: str

    @field_validator("version_hash")
    @classmethod
    def _non_blank_hash(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("version_hash must not be blank")
        return stripped


_META = MetaData()
ATTEMPTS = Table(
    "execution_attempts",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("execution_id", BigInteger),
    Column("requirement", Text),
    Column("attempt_number", Integer),
    Column("retest_deviation_id", BigInteger),
    Column("retest_reason", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)
ATTEMPT_VERSIONS = Table(
    "execution_attempt_versions",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("attempt_id", BigInteger),
    Column("version", Integer),
    Column("outcome_kind", Text),
    Column("not_performable_reason", Text),
    Column("value", JSONB(none_as_null=True)),
    Column("observation", Text),
    Column("instruments", JSONB),
    Column("no_calibrated_instrument_reason", Text),
    Column("evidence", JSONB),
    Column("verdict", Text),
    Column("version_hash", Text),
    Column("reason_for_change", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)
DEVIATIONS = Table(
    "execution_deviations",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("execution_id", BigInteger),
    Column("deviation_number", Integer),
    Column("requirement", Text),
    Column("attempt_id", BigInteger),
    Column("cause", Text),
    Column("description", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)
DEVIATION_EVENTS = Table(
    "execution_deviation_events",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("deviation_id", BigInteger),
    Column("event", Text),
    Column("reason", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)
DEVIATION_INVESTIGATIONS = Table(
    "execution_deviation_investigations",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("deviation_id", BigInteger),
    Column("version", Integer),
    Column("investigation", Text),
    Column("deviation_class", Text),
    Column("capa", Text),
    Column("reason_for_change", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)
WITNESS_CONFIRMATIONS = Table(
    "execution_witness_confirmations",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("version_id", BigInteger),
    Column("version_hash", Text),
    Column("witness_subject", Text),
    Column("witness_issuer", Text),
    Column("witness_name", Text),
)


@dataclass(frozen=True)
class WitnessConfirmation:
    """One Witness confirmation bound to an attempt version's hash."""

    id: int
    at: datetime
    version_id: int
    version_hash: str
    actor: audit.Actor
    voided: bool


@dataclass(frozen=True)
class AttemptVersion:
    """One immutable version of an attempt's Result."""

    id: int
    at: datetime
    attempt_id: int
    version: int
    outcome_kind: OutcomeKind
    not_performable_reason: str | None
    value: ResultValue | None
    observation: str | None
    instruments: tuple[InstrumentInput, ...]
    no_calibrated_instrument_reason: str | None
    evidence: tuple[str, ...]
    verdict: Verdict
    version_hash: str
    reason_for_change: str | None
    actor: audit.Actor
    witness_confirmations: tuple[WitnessConfirmation, ...] = ()


@dataclass(frozen=True)
class Attempt:
    """One attempt on a Test Step row, with its versions oldest first."""

    id: int
    at: datetime
    execution_id: int
    requirement: str
    attempt_number: int
    actor: audit.Actor
    versions: tuple[AttemptVersion, ...]
    retest_deviation_id: int | None = None
    retest_reason: str | None = None

    @property
    def latest(self) -> AttemptVersion:
        return self.versions[-1]


@dataclass(frozen=True)
class DeviationEvent:
    """One status event on a Deviation."""

    id: int
    at: datetime
    deviation_id: int
    event: DeviationEventKind
    reason: str | None
    actor: audit.Actor

    @property
    def status(self) -> DeviationStatus:
        return DEVIATION_STATUS_AFTER[self.event]


@dataclass(frozen=True)
class DeviationInvestigation:
    """One immutable version of a Deviation's Investigation."""

    id: int
    at: datetime
    deviation_id: int
    version: int
    investigation: str
    deviation_class: DeviationClass
    capa: str | None
    reason_for_change: str | None
    actor: audit.Actor


@dataclass(frozen=True)
class Deviation:
    """One Deviation on an Execution, with status events and Investigation versions."""

    id: int
    at: datetime
    execution_id: int
    deviation_number: int
    requirement: str | None
    attempt_id: int | None
    cause: DeviationCause
    description: str
    actor: audit.Actor
    events: tuple[DeviationEvent, ...]
    investigations: tuple[DeviationInvestigation, ...] = ()

    @property
    def status(self) -> DeviationStatus:
        return self.events[-1].status

    @property
    def deviation_class(self) -> DeviationClass | None:
        return self.investigations[-1].deviation_class if self.investigations else None


def _parse_value(raw: dict[str, Any] | None) -> ResultValue | None:
    if raw is None:
        return None
    kind = raw.get("type")
    if kind == "number":
        return NumberResultValue.model_validate(raw)
    if kind == "one_of":
        return OneOfResultValue.model_validate(raw)
    if kind == "present":
        return PresentResultValue.model_validate(raw)
    raise ValueError(f"unknown stored result value type: {kind!r}")


def _witness_from_row(m: RowMapping, *, voided: bool) -> WitnessConfirmation:
    return WitnessConfirmation(
        id=m["id"],
        at=m["at"],
        version_id=m["version_id"],
        version_hash=m["version_hash"],
        actor=audit.Actor(
            subject=m["witness_subject"],
            issuer=m["witness_issuer"],
            name=m["witness_name"],
        ),
        voided=voided,
    )


def _version_from_row(
    m: RowMapping,
    witness_confirmations: tuple[WitnessConfirmation, ...] = (),
) -> AttemptVersion:
    return AttemptVersion(
        id=m["id"],
        at=m["at"],
        attempt_id=m["attempt_id"],
        version=m["version"],
        outcome_kind=cast(OutcomeKind, m["outcome_kind"]),
        not_performable_reason=m["not_performable_reason"],
        value=_parse_value(m["value"]),
        observation=m["observation"],
        instruments=tuple(InstrumentInput.model_validate(i) for i in (m["instruments"] or ())),
        no_calibrated_instrument_reason=m["no_calibrated_instrument_reason"],
        evidence=tuple(m["evidence"] or ()),
        verdict=cast(Verdict, m["verdict"]),
        version_hash=m["version_hash"],
        reason_for_change=m["reason_for_change"],
        actor=audit.actor_of_row(m),
        witness_confirmations=witness_confirmations,
    )


def deviation_event_from_row(m: RowMapping) -> DeviationEvent:
    return DeviationEvent(
        id=m["id"],
        at=m["at"],
        deviation_id=m["deviation_id"],
        event=cast(DeviationEventKind, m["event"]),
        reason=m["reason"],
        actor=audit.actor_of_row(m),
    )


def deviation_investigation_from_row(m: RowMapping) -> DeviationInvestigation:
    return DeviationInvestigation(
        id=m["id"],
        at=m["at"],
        deviation_id=m["deviation_id"],
        version=m["version"],
        investigation=m["investigation"],
        deviation_class=cast(DeviationClass, m["deviation_class"]),
        capa=m["capa"],
        reason_for_change=m["reason_for_change"],
        actor=audit.actor_of_row(m),
    )


def judge(acceptance: Acceptance, req: RecordAttemptRequest) -> Verdict:
    """Judges a Result against the frozen Acceptance Criterion (ADR 0013 exact rules)."""
    if req.outcome_kind == "not_performable":
        return "fail"

    val = req.value
    if val is None:
        raise InvalidResult("value outcome requires a value")

    if isinstance(acceptance, Range):
        if not isinstance(val, NumberResultValue):
            raise InvalidResult(
                f"range Acceptance Criterion requires a number value, got {val.type}"
            )
        if (
            acceptance.min is not None
            and acceptance.max is not None
            and acceptance.min > acceptance.max
        ):
            return "fail"
        if acceptance.min is not None and val.value < acceptance.min:
            return "fail"
        if acceptance.max is not None and val.value > acceptance.max:
            return "fail"
        return "pass"

    if isinstance(acceptance, Number):
        if not isinstance(val, NumberResultValue):
            raise InvalidResult(
                f"number Acceptance Criterion requires a number value, got {val.type}"
            )
        return "pass" if val.value == acceptance.value else "fail"

    if isinstance(acceptance, OneOf):
        if not isinstance(val, OneOfResultValue):
            raise InvalidResult(
                f"one_of Acceptance Criterion requires a one_of value, got {val.type}"
            )
        if val.not_one_of:
            return "fail"
        if val.value not in acceptance.allowed:
            raise InvalidResult(
                f"value {val.value!r} is not in allowed values {acceptance.allowed!r}; "
                "use not_one_of=true for an out-of-list observation"
            )
        return "pass"

    # Present
    if not isinstance(val, PresentResultValue):
        raise InvalidResult(
            f"present Acceptance Criterion requires a present value, got {val.type}"
        )
    return "pass" if val.value else "fail"


def database_utc_date(session: Session) -> date:
    """The database's current UTC calendar date (ALCOA contemporaneous)."""
    return session.execute(text("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date")).scalar_one()


def validate_instruments(
    session: Session,
    step_instrument: str | None,
    req: RecordAttemptRequest,
    *,
    reference_date: date | None = None,
) -> None:
    """Enforces instrument presence (422) and calibration due date >= reference UTC date (409)."""
    step_requires_instrument = step_instrument is not None and step_instrument.strip() != ""
    has_no_inst_reason = (
        req.no_calibrated_instrument_reason is not None
        and req.no_calibrated_instrument_reason.strip() != ""
    )
    if step_requires_instrument and not req.instruments and not has_no_inst_reason:
        raise InvalidResult(
            "Test Step names an instrument: provide at least one calibrated instrument "
            "or a non-blank no_calibrated_instrument_reason"
        )
    if req.instruments:
        ref_date = database_utc_date(session) if reference_date is None else reference_date
        for inst in req.instruments:
            if inst.calibration_due_date < ref_date:
                raise lifecycle.Conflict(
                    f"Instrument '{inst.identifier}' calibration expired on "
                    f"{inst.calibration_due_date.isoformat()} "
                    f"(reference UTC date is {ref_date.isoformat()})"
                )


def _format_acceptance(a: Acceptance) -> str:
    if isinstance(a, Range):
        if a.min is not None and a.max is not None:
            return f"{a.min}–{a.max} {a.unit}"
        if a.min is not None:
            return f">= {a.min} {a.unit}"
        return f"<= {a.max} {a.unit}"
    if isinstance(a, Number):
        return f"{a.value} {a.unit}"
    if isinstance(a, OneOf):
        return "one of [" + ", ".join(a.allowed) + "]"
    return "present"


def _format_result(step: FrozenTestStep, req: RecordAttemptRequest) -> str:
    if req.outcome_kind == "not_performable":
        reason = (req.not_performable_reason or "").strip()
        return f"not performable ({reason})"
    val = req.value
    if isinstance(val, NumberResultValue):
        unit = step.acceptance.unit if isinstance(step.acceptance, Range | Number) else ""
        return f"{val.value} {unit}".strip()
    if isinstance(val, OneOfResultValue):
        return f"not one of these: {val.value}" if val.not_one_of else val.value
    if isinstance(val, PresentResultValue):
        return "present" if val.value else "absent"
    return ""


def _deviation_description(
    row: FrozenRow,
    step: FrozenTestStep,
    req: RecordAttemptRequest,
    cause: Literal["failed", "no_calibrated_instrument"],
) -> str:
    ac_text = _format_acceptance(step.acceptance)
    result_text = _format_result(step, req)
    if cause == "failed":
        return (
            f"Test Step {row.requirement} ({step.description}) failed Acceptance Criterion "
            f"({ac_text}) with Result: {result_text}."
        )
    reason = (req.no_calibrated_instrument_reason or "").strip()
    return (
        f"Test Step {row.requirement} ({step.description}) recorded without a calibrated "
        f"instrument (protocol instrument: {step.instrument}; reason: {reason}). "
        f"Acceptance Criterion ({ac_text}), Result: {result_text}."
    )


def _version_digest(
    *,
    execution_id: int,
    requirement: str,
    attempt_number: int,
    version: int,
    outcome_kind: OutcomeKind,
    not_performable_reason: str | None,
    value: ResultValue | None,
    observation: str | None,
    instruments: Sequence[InstrumentInput],
    no_calibrated_instrument_reason: str | None,
    evidence: Sequence[str],
    verdict: Verdict,
    actor: audit.Actor,
    reason_for_change: str | None,
) -> str:
    rfc = reason_for_change.strip() if reason_for_change is not None else None
    if rfc == "":
        rfc = None
    payload: dict[str, Any] = {
        "execution_id": execution_id,
        "requirement": requirement,
        "attempt_number": attempt_number,
        "version": version,
        "outcome_kind": outcome_kind,
        "not_performable_reason": (
            not_performable_reason.strip() if not_performable_reason else None
        ),
        "value": None if value is None else value.model_dump(mode="json"),
        "observation": observation,
        "instruments": [i.model_dump(mode="json") for i in instruments],
        "no_calibrated_instrument_reason": (
            no_calibrated_instrument_reason.strip() if no_calibrated_instrument_reason else None
        ),
        "evidence": list(evidence),
        "verdict": verdict,
        "reason_for_change": rfc,
        "actor": {"subject": actor.subject, "issuer": actor.issuer, "name": actor.name},
    }
    return digest(payload)


def _version_hash(
    *,
    execution_id: int,
    requirement: str,
    attempt_number: int,
    version: int,
    req: RecordAttemptRequest,
    verdict: Verdict,
    actor: audit.Actor,
    reason_for_change: str | None = None,
) -> str:
    return _version_digest(
        execution_id=execution_id,
        requirement=requirement,
        attempt_number=attempt_number,
        version=version,
        outcome_kind=req.outcome_kind,
        not_performable_reason=req.not_performable_reason,
        value=req.value,
        observation=req.observation,
        instruments=req.instruments,
        no_calibrated_instrument_reason=req.no_calibrated_instrument_reason,
        evidence=req.evidence,
        verdict=verdict,
        actor=actor,
        reason_for_change=reason_for_change,
    )


def recomputed_version_hash(attempt: Attempt, v: AttemptVersion) -> str:
    """The hash of version ``v`` of ``attempt``, recomputed from what is stored: differs from
    ``v.version_hash`` when the stored Result was altered after it was recorded."""
    return _version_digest(
        execution_id=attempt.execution_id,
        requirement=attempt.requirement,
        attempt_number=attempt.attempt_number,
        version=v.version,
        outcome_kind=v.outcome_kind,
        not_performable_reason=v.not_performable_reason,
        value=v.value,
        observation=v.observation,
        instruments=v.instruments,
        no_calibrated_instrument_reason=v.no_calibrated_instrument_reason,
        evidence=v.evidence,
        verdict=v.verdict,
        actor=v.actor,
        reason_for_change=v.reason_for_change,
    )


def frozen_copy(session: Session, ex: lifecycle.Execution) -> ProtocolCopy:
    for sub in submission.submissions_of(session, ex.protocol_id):
        if sub.event_id == ex.submission_event_id:
            return sub.copy
    raise lifecycle.NotFound(
        f"submission {ex.submission_event_id} of Protocol {ex.protocol_id} not found"
    )


def attempts_of(session: Session, execution_id: int) -> dict[str, tuple[Attempt, ...]]:
    """All attempts of ``execution_id``, grouped by requirement and ordered by attempt_number."""
    attempt_rows = (
        session.execute(
            select(ATTEMPTS)
            .where(ATTEMPTS.c.execution_id == execution_id)
            .order_by(ATTEMPTS.c.attempt_number)
        )
        .mappings()
        .all()
    )
    if not attempt_rows:
        return {}
    attempt_ids = [r["id"] for r in attempt_rows]
    version_rows = (
        session.execute(
            select(ATTEMPT_VERSIONS)
            .where(ATTEMPT_VERSIONS.c.attempt_id.in_(attempt_ids))
            .order_by(ATTEMPT_VERSIONS.c.version)
        )
        .mappings()
        .all()
    )
    version_ids = [vm["id"] for vm in version_rows]
    witness_rows_by_version: dict[int, list[RowMapping]] = {}
    if version_ids:
        for wm in (
            session.execute(
                select(WITNESS_CONFIRMATIONS)
                .where(WITNESS_CONFIRMATIONS.c.version_id.in_(version_ids))
                .order_by(WITNESS_CONFIRMATIONS.c.id)
            )
            .mappings()
            .all()
        ):
            witness_rows_by_version.setdefault(wm["version_id"], []).append(wm)

    raw_versions_by_attempt: dict[int, list[RowMapping]] = {}
    for vm in version_rows:
        raw_versions_by_attempt.setdefault(vm["attempt_id"], []).append(vm)

    versions_by_attempt: dict[int, list[AttemptVersion]] = {}
    for aid, vms in raw_versions_by_attempt.items():
        latest_ver_num = vms[-1]["version"]
        versions_by_attempt[aid] = [
            _version_from_row(
                vm,
                witness_confirmations=tuple(
                    _witness_from_row(wm, voided=vm["version"] < latest_ver_num)
                    for wm in witness_rows_by_version.get(vm["id"], ())
                ),
            )
            for vm in vms
        ]

    by_req: dict[str, list[Attempt]] = {}
    for am in attempt_rows:
        attempt = Attempt(
            id=am["id"],
            at=am["at"],
            execution_id=am["execution_id"],
            requirement=am["requirement"],
            attempt_number=am["attempt_number"],
            actor=audit.actor_of_row(am),
            versions=tuple(versions_by_attempt.get(am["id"], ())),
            retest_deviation_id=am["retest_deviation_id"],
            retest_reason=am["retest_reason"],
        )
        by_req.setdefault(attempt.requirement, []).append(attempt)
    return {req: tuple(items) for req, items in by_req.items()}


def deviations_of(session: Session, execution_id: int) -> tuple[Deviation, ...]:
    """All Deviations of ``execution_id``, ordered by deviation_number."""
    dev_rows = (
        session.execute(
            select(DEVIATIONS)
            .where(DEVIATIONS.c.execution_id == execution_id)
            .order_by(DEVIATIONS.c.deviation_number)
        )
        .mappings()
        .all()
    )
    if not dev_rows:
        return ()
    dev_ids = [r["id"] for r in dev_rows]
    events_by_dev: dict[int, list[DeviationEvent]] = {}
    for em in (
        session.execute(
            select(DEVIATION_EVENTS)
            .where(DEVIATION_EVENTS.c.deviation_id.in_(dev_ids))
            .order_by(DEVIATION_EVENTS.c.id)
        )
        .mappings()
        .all()
    ):
        events_by_dev.setdefault(em["deviation_id"], []).append(deviation_event_from_row(em))

    inv_by_dev: dict[int, list[DeviationInvestigation]] = {}
    for im in (
        session.execute(
            select(DEVIATION_INVESTIGATIONS)
            .where(DEVIATION_INVESTIGATIONS.c.deviation_id.in_(dev_ids))
            .order_by(DEVIATION_INVESTIGATIONS.c.version)
        )
        .mappings()
        .all()
    ):
        inv_by_dev.setdefault(im["deviation_id"], []).append(deviation_investigation_from_row(im))

    return tuple(
        Deviation(
            id=dm["id"],
            at=dm["at"],
            execution_id=dm["execution_id"],
            deviation_number=dm["deviation_number"],
            requirement=dm["requirement"],
            attempt_id=dm["attempt_id"],
            cause=cast(DeviationCause, dm["cause"]),
            description=dm["description"],
            actor=audit.actor_of_row(dm),
            events=tuple(events_by_dev.get(dm["id"], ())),
            investigations=tuple(inv_by_dev.get(dm["id"], ())),
        )
        for dm in dev_rows
    )


def _require_test_step_row(
    session: Session,
    execution_id: int,
    requirement: str,
    *,
    action_label: str,
) -> FrozenRow:
    """Locks the Execution, verifies ``in_progress``, and returns the frozen Test Step row."""
    lifecycle.lock_execution(session, execution_id)
    ex = lifecycle.get(session, execution_id)
    if ex is None:
        raise lifecycle.NotFound(f"no Execution {execution_id}")
    if ex.status != "in_progress":
        raise lifecycle.Conflict(
            f"Execution {execution_id} is {ex.status}: {action_label} only while In progress"
        )

    copy = frozen_copy(session, ex)
    row = next((r for r in copy.rows if r.requirement == requirement), None)
    if row is None:
        raise lifecycle.NotFound(f"no row {requirement} in Execution {execution_id}")
    if row.kind != "test_step" or row.test_step is None:
        raise lifecycle.Conflict(f"row {requirement} is a Vendor Reference, not a Test Step")
    return row


def _insert_attempt_version(
    session: Session,
    actor: audit.Actor,
    *,
    execution_id: int,
    requirement: str,
    attempt_id: int,
    attempt_number: int,
    version_number: int,
    req: RecordAttemptRequest,
    verdict: Verdict,
    reason_for_change: str | None,
) -> AttemptVersion:
    v_hash = _version_hash(
        execution_id=execution_id,
        requirement=requirement,
        attempt_number=attempt_number,
        version=version_number,
        req=req,
        verdict=verdict,
        actor=actor,
        reason_for_change=reason_for_change,
    )
    not_perf_reason = (
        req.not_performable_reason.strip() if req.not_performable_reason is not None else None
    )
    if not_perf_reason == "":
        not_perf_reason = None
    no_inst_reason = (
        req.no_calibrated_instrument_reason.strip()
        if req.no_calibrated_instrument_reason is not None
        else None
    )
    if no_inst_reason == "":
        no_inst_reason = None

    version_row = (
        session.execute(
            insert(ATTEMPT_VERSIONS)
            .values(
                attempt_id=attempt_id,
                version=version_number,
                outcome_kind=req.outcome_kind,
                not_performable_reason=not_perf_reason,
                value=None if req.value is None else req.value.model_dump(mode="json"),
                observation=req.observation,
                instruments=[i.model_dump(mode="json") for i in req.instruments],
                no_calibrated_instrument_reason=no_inst_reason,
                evidence=list(req.evidence),
                verdict=verdict,
                version_hash=v_hash,
                reason_for_change=reason_for_change,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*ATTEMPT_VERSIONS.c)
        )
        .mappings()
        .one()
    )
    return _version_from_row(version_row)


def _open_automatic_deviations(
    session: Session,
    actor: audit.Actor,
    *,
    execution_id: int,
    row: FrozenRow,
    attempt_id: int,
    req: RecordAttemptRequest,
    verdict: Verdict,
    existing_causes: frozenset[str] = frozenset(),
) -> tuple[Deviation, ...]:
    assert row.test_step is not None
    no_inst_reason = (
        req.no_calibrated_instrument_reason.strip()
        if req.no_calibrated_instrument_reason is not None
        else None
    )
    if no_inst_reason == "":
        no_inst_reason = None

    causes: list[Literal["failed", "no_calibrated_instrument"]] = []
    if verdict == "fail" and "failed" not in existing_causes:
        causes.append("failed")
    if no_inst_reason is not None and "no_calibrated_instrument" not in existing_causes:
        causes.append("no_calibrated_instrument")

    opened: list[Deviation] = []
    if not causes:
        return ()

    max_num: int = session.execute(
        select(func.coalesce(func.max(DEVIATIONS.c.deviation_number), 0)).where(
            DEVIATIONS.c.execution_id == execution_id
        )
    ).scalar_one()
    for cause in causes:
        max_num += 1
        desc = _deviation_description(row, row.test_step, req, cause)
        dev_row = (
            session.execute(
                insert(DEVIATIONS)
                .values(
                    execution_id=execution_id,
                    deviation_number=max_num,
                    requirement=row.requirement,
                    attempt_id=attempt_id,
                    cause=cause,
                    description=desc,
                    subject=actor.subject,
                    issuer=actor.issuer,
                    name=actor.name,
                )
                .returning(*DEVIATIONS.c)
            )
            .mappings()
            .one()
        )
        ev_row = (
            session.execute(
                insert(DEVIATION_EVENTS)
                .values(
                    deviation_id=dev_row["id"],
                    event="opened",
                    reason=None,
                    subject=actor.subject,
                    issuer=actor.issuer,
                    name=actor.name,
                )
                .returning(*DEVIATION_EVENTS.c)
            )
            .mappings()
            .one()
        )
        ev = deviation_event_from_row(ev_row)
        dev = Deviation(
            id=dev_row["id"],
            at=dev_row["at"],
            execution_id=execution_id,
            deviation_number=max_num,
            requirement=row.requirement,
            attempt_id=attempt_id,
            cause=cause,
            description=desc,
            actor=audit.actor_of_row(dev_row),
            events=(ev,),
        )
        opened.append(dev)
        audit.append(
            session,
            actor,
            "deviation opened",
            "execution_deviation",
            f"{execution_id}/{max_num}",
            new={
                "execution_id": execution_id,
                "deviation_id": dev.id,
                "deviation_number": max_num,
                "requirement": row.requirement,
                "attempt_id": attempt_id,
                "cause": cause,
                "status": dev.status,
            },
        )
    return tuple(opened)


def record_attempt(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    requirement: str,
    req: RecordAttemptRequest,
) -> tuple[Attempt, tuple[Deviation, ...]]:
    """Records the first attempt (attempt 1, version 1) on a Test Step row of an ``in_progress``
    Execution, judges it by code, validates instrument calibration dates against the DB UTC
    date, opens automatic Deviations for ``failed`` / ``no_calibrated_instrument``, and appends
    Audit Trail entries in the same transaction."""
    row = _require_test_step_row(
        session, execution_id, requirement, action_label="Results are recorded"
    )
    assert row.test_step is not None

    existing_attempt = session.execute(
        select(ATTEMPTS.c.id).where(
            ATTEMPTS.c.execution_id == execution_id,
            ATTEMPTS.c.requirement == requirement,
        )
    ).first()
    if existing_attempt is not None:
        raise lifecycle.Conflict(
            f"row {requirement} in Execution {execution_id} already has an attempt"
        )

    verdict = judge(row.test_step.acceptance, req)
    validate_instruments(session, row.test_step.instrument, req)

    attempt_number = 1
    version_number = 1
    attempt_row = (
        session.execute(
            insert(ATTEMPTS)
            .values(
                execution_id=execution_id,
                requirement=requirement,
                attempt_number=attempt_number,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*ATTEMPTS.c)
        )
        .mappings()
        .one()
    )
    ver = _insert_attempt_version(
        session,
        actor,
        execution_id=execution_id,
        requirement=requirement,
        attempt_id=attempt_row["id"],
        attempt_number=attempt_number,
        version_number=version_number,
        req=req,
        verdict=verdict,
        reason_for_change=None,
    )

    audit.append(
        session,
        actor,
        "attempt recorded",
        "execution_attempt",
        f"{execution_id}/{requirement}/{attempt_number}",
        new={
            "execution_id": execution_id,
            "requirement": requirement,
            "attempt_id": attempt_row["id"],
            "attempt_number": attempt_number,
            "version_id": ver.id,
            "version": version_number,
            "outcome_kind": ver.outcome_kind,
            "verdict": ver.verdict,
            "version_hash": ver.version_hash,
        },
    )

    opened_deviations = _open_automatic_deviations(
        session,
        actor,
        execution_id=execution_id,
        row=row,
        attempt_id=attempt_row["id"],
        req=req,
        verdict=verdict,
    )

    attempt = Attempt(
        id=attempt_row["id"],
        at=attempt_row["at"],
        execution_id=execution_id,
        requirement=requirement,
        attempt_number=attempt_number,
        actor=audit.actor_of_row(attempt_row),
        versions=(ver,),
        retest_deviation_id=attempt_row["retest_deviation_id"],
        retest_reason=attempt_row["retest_reason"],
    )
    return attempt, opened_deviations


def correct_attempt(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    requirement: str,
    attempt_number: int,
    req: CorrectAttemptRequest,
) -> tuple[Attempt, tuple[Deviation, ...]]:
    """Adds a new version (``latest + 1``) to an existing attempt while the Execution is
    ``in_progress``.

    Enforces Performer ownership, Deviation status lock (refused while any Deviation linked to
    that attempt is ``submitted`` or ``closed``), instrument calibration against the UTC date of
    version 1, and automatic Deviation rules without closing existing Deviations.
    """
    row = _require_test_step_row(
        session, execution_id, requirement, action_label="Results can be corrected"
    )
    assert row.test_step is not None

    attempt_row = (
        session.execute(
            select(ATTEMPTS).where(
                ATTEMPTS.c.execution_id == execution_id,
                ATTEMPTS.c.requirement == requirement,
                ATTEMPTS.c.attempt_number == attempt_number,
            )
        )
        .mappings()
        .first()
    )
    if attempt_row is None:
        raise lifecycle.NotFound(
            f"no attempt {attempt_number} for row {requirement} in Execution {execution_id}"
        )

    if (actor.subject, actor.issuer) != (attempt_row["subject"], attempt_row["issuer"]):
        raise lifecycle.Conflict("only the Performer of this attempt may correct it")

    attempt_devs = [
        d for d in deviations_of(session, execution_id) if d.attempt_id == attempt_row["id"]
    ]
    for d in attempt_devs:
        if d.status in ("submitted", "closed"):
            raise lifecycle.Conflict(
                f"attempt {attempt_number} cannot be corrected while Deviation"
                f" #{d.deviation_number} is {d.status}"
            )

    version_rows = (
        session.execute(
            select(ATTEMPT_VERSIONS)
            .where(ATTEMPT_VERSIONS.c.attempt_id == attempt_row["id"])
            .order_by(ATTEMPT_VERSIONS.c.version)
        )
        .mappings()
        .all()
    )
    prev = version_rows[-1]
    first_version_utc_date = version_rows[0]["at"].astimezone(UTC).date()
    next_version = prev["version"] + 1

    verdict = judge(row.test_step.acceptance, req)
    validate_instruments(
        session, row.test_step.instrument, req, reference_date=first_version_utc_date
    )

    ver = _insert_attempt_version(
        session,
        actor,
        execution_id=execution_id,
        requirement=requirement,
        attempt_id=attempt_row["id"],
        attempt_number=attempt_number,
        version_number=next_version,
        req=req,
        verdict=verdict,
        reason_for_change=req.reason_for_change,
    )

    audit.append(
        session,
        actor,
        "attempt corrected",
        "execution_attempt",
        f"{execution_id}/{requirement}/{attempt_number}",
        old={
            "version_id": prev["id"],
            "version": prev["version"],
            "outcome_kind": prev["outcome_kind"],
            "verdict": prev["verdict"],
            "version_hash": prev["version_hash"],
        },
        new={
            "execution_id": execution_id,
            "requirement": requirement,
            "attempt_id": attempt_row["id"],
            "attempt_number": attempt_number,
            "version_id": ver.id,
            "version": next_version,
            "outcome_kind": ver.outcome_kind,
            "verdict": ver.verdict,
            "version_hash": ver.version_hash,
            "reason_for_change": req.reason_for_change,
        },
        reason=req.reason_for_change,
    )

    existing_causes = frozenset(d.cause for d in attempt_devs)
    opened_deviations = _open_automatic_deviations(
        session,
        actor,
        execution_id=execution_id,
        row=row,
        attempt_id=attempt_row["id"],
        req=req,
        verdict=verdict,
        existing_causes=existing_causes,
    )

    updated_attempt = next(
        a
        for a in attempts_of(session, execution_id)[requirement]
        if a.attempt_number == attempt_number
    )
    return updated_attempt, opened_deviations


def retest_row(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    requirement: str,
    req: RetestRowRequest,
) -> tuple[Attempt, tuple[Deviation, ...]]:
    """Records a new attempt (``latest + 1``, version 1) on a failed Test Step row of an
    ``in_progress`` Execution, naming an ``open`` Deviation linked to that Test Step."""
    row = _require_test_step_row(
        session, execution_id, requirement, action_label="Test Steps can be retested"
    )
    assert row.test_step is not None

    existing_attempts = attempts_of(session, execution_id).get(requirement, ())
    if not existing_attempts:
        raise lifecycle.Conflict(
            f"row {requirement} has no attempt yet; record the first attempt before retesting"
        )
    latest_attempt = existing_attempts[-1]
    if latest_attempt.latest.verdict == "pass":
        raise lifecycle.Conflict(
            f"row {requirement} latest Result passes; Retest is only allowed when it fails"
        )

    all_devs = deviations_of(session, execution_id)
    dev: Deviation | None = None
    for d in all_devs:
        if req.deviation_id is not None and d.id != req.deviation_id:
            continue
        if req.deviation_number is not None and d.deviation_number != req.deviation_number:
            continue
        dev = d
        break
    if dev is None:
        raise lifecycle.NotFound(f"no matching Deviation in Execution {execution_id}")
    if dev.requirement is None:
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} is linked to the Execution only, not to"
            f" {requirement}"
        )
    if dev.requirement != requirement:
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} is linked to {dev.requirement}, not {requirement}"
        )
    if dev.status != "open":
        raise lifecycle.Conflict(
            f"Deviation #{dev.deviation_number} is {dev.status}; Retest requires an Open Deviation"
        )

    verdict = judge(row.test_step.acceptance, req)
    validate_instruments(session, row.test_step.instrument, req)

    attempt_number = latest_attempt.attempt_number + 1
    version_number = 1
    retest_reason = req.effective_reason()
    attempt_row = (
        session.execute(
            insert(ATTEMPTS)
            .values(
                execution_id=execution_id,
                requirement=requirement,
                attempt_number=attempt_number,
                retest_deviation_id=dev.id,
                retest_reason=retest_reason,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*ATTEMPTS.c)
        )
        .mappings()
        .one()
    )
    ver = _insert_attempt_version(
        session,
        actor,
        execution_id=execution_id,
        requirement=requirement,
        attempt_id=attempt_row["id"],
        attempt_number=attempt_number,
        version_number=version_number,
        req=req,
        verdict=verdict,
        reason_for_change=None,
    )

    audit.append(
        session,
        actor,
        "attempt retested",
        "execution_attempt",
        f"{execution_id}/{requirement}/{attempt_number}",
        old={
            "attempt_id": latest_attempt.id,
            "attempt_number": latest_attempt.attempt_number,
            "verdict": latest_attempt.latest.verdict,
        },
        new={
            "execution_id": execution_id,
            "requirement": requirement,
            "attempt_id": attempt_row["id"],
            "attempt_number": attempt_number,
            "version_id": ver.id,
            "version": version_number,
            "outcome_kind": ver.outcome_kind,
            "verdict": ver.verdict,
            "version_hash": ver.version_hash,
            "deviation_id": dev.id,
            "deviation_number": dev.deviation_number,
            "retest_reason": retest_reason,
        },
        reason=retest_reason,
    )

    opened_deviations = _open_automatic_deviations(
        session,
        actor,
        execution_id=execution_id,
        row=row,
        attempt_id=attempt_row["id"],
        req=req,
        verdict=verdict,
    )

    attempt = Attempt(
        id=attempt_row["id"],
        at=attempt_row["at"],
        execution_id=execution_id,
        requirement=requirement,
        attempt_number=attempt_number,
        actor=audit.actor_of_row(attempt_row),
        versions=(ver,),
        retest_deviation_id=attempt_row["retest_deviation_id"],
        retest_reason=attempt_row["retest_reason"],
    )
    return attempt, opened_deviations


def confirm_witness(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    requirement: str,
    attempt_number: int,
    req: ConfirmWitnessRequest,
    *,
    auth_time: datetime | None,
    jti: str | None,
    is_demo: bool = False,
) -> WitnessConfirmation:
    """Records a Witness confirmation bound to the latest version's ``version_hash`` of an
    attempt while the Execution is ``in_progress``.

    Refuses (409) when the Execution is not ``in_progress``, when ``version_number`` or
    ``version_hash`` does not match the attempt's latest version, when the Witness is the
    Performer of that version (same ``subject`` and ``issuer``), or when the same Witness has
    already confirmed that version. Signs the confirmation: ``SignatureAuthRequired`` without a
    fresh ``auth_time`` and ``jti``, before anything is written.
    """
    auth_time, jti = audit.require_signing_claims(auth_time, jti)
    lifecycle.lock_execution(session, execution_id)
    ex = lifecycle.get(session, execution_id)
    if ex is None:
        raise lifecycle.NotFound(f"no Execution {execution_id}")
    if ex.status != "in_progress":
        raise lifecycle.Conflict(
            f"Execution {execution_id} is {ex.status}: Witness confirmations are recorded only "
            "while In progress"
        )

    copy = frozen_copy(session, ex)
    row = next((r for r in copy.rows if r.requirement == requirement), None)
    if row is None:
        raise lifecycle.NotFound(f"no row {requirement} in Execution {execution_id}")
    if row.kind != "test_step" or row.test_step is None:
        raise lifecycle.Conflict(f"row {requirement} is a Vendor Reference, not a Test Step")

    attempt_row = (
        session.execute(
            select(ATTEMPTS).where(
                ATTEMPTS.c.execution_id == execution_id,
                ATTEMPTS.c.requirement == requirement,
                ATTEMPTS.c.attempt_number == attempt_number,
            )
        )
        .mappings()
        .first()
    )
    if attempt_row is None:
        raise lifecycle.NotFound(
            f"no attempt {attempt_number} for row {requirement} in Execution {execution_id}"
        )

    version_rows = (
        session.execute(
            select(ATTEMPT_VERSIONS)
            .where(ATTEMPT_VERSIONS.c.attempt_id == attempt_row["id"])
            .order_by(ATTEMPT_VERSIONS.c.version)
        )
        .mappings()
        .all()
    )
    latest = _version_from_row(version_rows[-1])

    if req.version_number != latest.version:
        raise lifecycle.Conflict(
            f"version {req.version_number} is stale: latest version of attempt {attempt_number} "
            f"is {latest.version}"
        )
    if req.version_hash != latest.version_hash:
        raise lifecycle.Conflict("version_hash does not match the latest version's hash")
    if (actor.subject, actor.issuer) == (latest.actor.subject, latest.actor.issuer):
        raise lifecycle.Conflict("the Witness cannot be the Performer of this Result version")

    existing = session.execute(
        select(WITNESS_CONFIRMATIONS.c.id).where(
            WITNESS_CONFIRMATIONS.c.version_id == latest.id,
            WITNESS_CONFIRMATIONS.c.witness_subject == actor.subject,
            WITNESS_CONFIRMATIONS.c.witness_issuer == actor.issuer,
        )
    ).first()
    if existing is not None:
        raise lifecycle.Conflict("this Witness has already confirmed this version")

    inserted = (
        session.execute(
            insert(WITNESS_CONFIRMATIONS)
            .values(
                version_id=latest.id,
                version_hash=latest.version_hash,
                witness_subject=actor.subject,
                witness_issuer=actor.issuer,
                witness_name=actor.name,
            )
            .returning(*WITNESS_CONFIRMATIONS.c)
        )
        .mappings()
        .one()
    )
    confirmation = _witness_from_row(inserted, voided=False)
    sig = audit.record_signature(
        session,
        actor,
        record_type="witness_confirmation",
        signature_meaning="witnessed",
        content_hash=latest.version_hash,
        auth_time=auth_time,
        jti=jti,
        is_demo=is_demo,
        witness_confirmation_id=confirmation.id,
    )

    new_audit: dict[str, audit.JsonValue] = {
        "execution_id": execution_id,
        "requirement": requirement,
        "attempt_number": attempt_number,
        "version_id": latest.id,
        "version": latest.version,
        "version_hash": latest.version_hash,
        "confirmation_id": confirmation.id,
        "note": audit.DEMO_SIGNATURE_LABEL if is_demo else audit.ELECTRONIC_SIGNATURE_LABEL,
        "signature_id": sig.id,
    }
    audit.append(
        session,
        actor,
        "witness confirmed",
        "execution_attempt_version",
        f"{execution_id}/{requirement}/{attempt_number}/v{latest.version}",
        new=new_audit,
    )
    return confirmation
