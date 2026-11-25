"""Recording Execution Results judged by code, with instruments and automatic Deviations
(ADR 0013, spec #270, #272).

Every write takes the per-Execution advisory lock (namespace 4) and re-checks ``in_progress``
status inside the transaction. The database clock stamps every row's ``at``, and instrument
calibration due dates are checked against the database's current UTC date.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
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


_META = MetaData()
ATTEMPTS = Table(
    "execution_attempts",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("execution_id", BigInteger),
    Column("requirement", Text),
    Column("attempt_number", Integer),
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


def _version_from_row(m: RowMapping) -> AttemptVersion:
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
) -> None:
    """Enforces instrument presence (422) and calibration due date >= DB UTC date (409)."""
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
        today_utc = database_utc_date(session)
        for inst in req.instruments:
            if inst.calibration_due_date < today_utc:
                raise lifecycle.Conflict(
                    f"Instrument '{inst.identifier}' calibration expired on "
                    f"{inst.calibration_due_date.isoformat()} "
                    f"(database UTC date is {today_utc.isoformat()})"
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


def _version_hash(
    *,
    execution_id: int,
    requirement: str,
    attempt_number: int,
    version: int,
    req: RecordAttemptRequest,
    verdict: Verdict,
    actor: audit.Actor,
) -> str:
    payload: dict[str, Any] = {
        "execution_id": execution_id,
        "requirement": requirement,
        "attempt_number": attempt_number,
        "version": version,
        "outcome_kind": req.outcome_kind,
        "not_performable_reason": (
            req.not_performable_reason.strip() if req.not_performable_reason else None
        ),
        "value": None if req.value is None else req.value.model_dump(mode="json"),
        "observation": req.observation,
        "instruments": [i.model_dump(mode="json") for i in req.instruments],
        "no_calibrated_instrument_reason": (
            req.no_calibrated_instrument_reason.strip()
            if req.no_calibrated_instrument_reason
            else None
        ),
        "evidence": list(req.evidence),
        "verdict": verdict,
        "actor": {"subject": actor.subject, "issuer": actor.issuer, "name": actor.name},
    }
    return digest(payload)


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
    versions_by_attempt: dict[int, list[AttemptVersion]] = {}
    for vm in (
        session.execute(
            select(ATTEMPT_VERSIONS)
            .where(ATTEMPT_VERSIONS.c.attempt_id.in_(attempt_ids))
            .order_by(ATTEMPT_VERSIONS.c.version)
        )
        .mappings()
        .all()
    ):
        versions_by_attempt.setdefault(vm["attempt_id"], []).append(_version_from_row(vm))

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
    lifecycle.lock_execution(session, execution_id)
    ex = lifecycle.get(session, execution_id)
    if ex is None:
        raise lifecycle.NotFound(f"no Execution {execution_id}")
    if ex.status != "in_progress":
        raise lifecycle.Conflict(
            f"Execution {execution_id} is {ex.status}: Results are recorded only while In progress"
        )

    copy = frozen_copy(session, ex)
    row = next((r for r in copy.rows if r.requirement == requirement), None)
    if row is None:
        raise lifecycle.NotFound(f"no row {requirement} in Execution {execution_id}")
    if row.kind != "test_step" or row.test_step is None:
        raise lifecycle.Conflict(f"row {requirement} is a Vendor Reference, not a Test Step")

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
    v_hash = _version_hash(
        execution_id=execution_id,
        requirement=requirement,
        attempt_number=attempt_number,
        version=version_number,
        req=req,
        verdict=verdict,
        actor=actor,
    )

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
                attempt_id=attempt_row["id"],
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
                reason_for_change=None,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*ATTEMPT_VERSIONS.c)
        )
        .mappings()
        .one()
    )
    ver = _version_from_row(version_row)

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

    causes: list[Literal["failed", "no_calibrated_instrument"]] = []
    if verdict == "fail":
        causes.append("failed")
    if no_inst_reason is not None:
        causes.append("no_calibrated_instrument")

    opened_deviations: list[Deviation] = []
    if causes:
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
                        requirement=requirement,
                        attempt_id=attempt_row["id"],
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
                requirement=requirement,
                attempt_id=attempt_row["id"],
                cause=cause,
                description=desc,
                actor=audit.actor_of_row(dev_row),
                events=(ev,),
            )
            opened_deviations.append(dev)
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
                    "requirement": requirement,
                    "attempt_id": attempt_row["id"],
                    "cause": cause,
                    "status": dev.status,
                },
            )

    attempt = Attempt(
        id=attempt_row["id"],
        at=attempt_row["at"],
        execution_id=execution_id,
        requirement=requirement,
        attempt_number=attempt_number,
        actor=audit.actor_of_row(attempt_row),
        versions=(ver,),
    )
    return attempt, tuple(opened_deviations)
