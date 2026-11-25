"""Append-only step attributes (``stage`` and ``witness_required``) on Test Step rows
of a Protocol in Draft status (Step 7, #326).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    RowMapping,
    Table,
    Text,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle
from traceq.assembly.lifecycle import Conflict, NotFound

type Stage = Literal["IQ", "OQ"]

_META = MetaData()
STEP_ATTRIBUTES = Table(
    "protocol_step_attributes",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("protocol_id", BigInteger),
    Column("requirement", Text),
    Column("version", Integer),
    Column("stage", Text),
    Column("witness_required", Boolean),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)


@dataclass(frozen=True)
class StepAttribute:
    """One immutable version of a Test Step row's attributes."""

    id: int
    at: datetime
    protocol_id: int
    requirement: str
    version: int
    stage: Stage | None
    witness_required: bool
    actor: audit.Actor


def _attr(m: RowMapping) -> StepAttribute:
    stage = m["stage"]
    return StepAttribute(
        id=int(m["id"]),
        at=m["at"],
        protocol_id=int(m["protocol_id"]),
        requirement=str(m["requirement"]),
        version=int(m["version"]),
        stage=cast(Stage, stage) if stage is not None else None,
        witness_required=bool(m["witness_required"]),
        actor=audit.actor_of_row(m),
    )


def attributes_of(session: Session, protocol_id: int) -> dict[str, tuple[StepAttribute, ...]]:
    """Every version of the Protocol's step attributes per requirement, oldest first."""
    out: dict[str, list[StepAttribute]] = {}
    for m in session.execute(
        select(STEP_ATTRIBUTES)
        .where(STEP_ATTRIBUTES.c.protocol_id == protocol_id)
        .order_by(STEP_ATTRIBUTES.c.version)
    ).mappings():
        out.setdefault(str(m["requirement"]), []).append(_attr(m))
    return {k: tuple(v) for k, v in out.items()}


def current(attrs: tuple[StepAttribute, ...]) -> tuple[Stage | None, bool]:
    """The current ``(stage, witness_required)`` from ``attrs``, defaulting to ``(None, False)``."""
    if not attrs:
        return None, False
    latest = attrs[-1]
    return latest.stage, latest.witness_required


def set_attributes(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    requirement: str,
    stage: Stage | None,
    witness_required: bool,
) -> StepAttribute:
    """Appends a new version of step attributes on a ``test_step`` row of a Draft Protocol."""
    from traceq.assembly.rows import rows_of

    current_proto = lifecycle.locked(
        session,
        protocol_id,
        "draft",
        "step attributes are set only while it is in Draft status",
    )
    lifecycle.lock_requirement(session, current_proto.equipment, requirement)
    row = next(
        (r for r in rows_of(session, current_proto) if r.requirement.id == requirement),
        None,
    )
    if row is None:
        raise NotFound(f"no requirement {requirement} in Protocol {protocol_id}")
    if row.kind != "test_step":
        raise Conflict(
            f"requirement {requirement} is {row.kind}: step attributes can only be set on a"
            " Test Step row"
        )

    earlier = attributes_of(session, protocol_id).get(requirement, ())
    added = _attr(
        session.execute(
            insert(STEP_ATTRIBUTES)
            .values(
                protocol_id=protocol_id,
                requirement=requirement,
                version=len(earlier) + 1,
                stage=stage,
                witness_required=witness_required,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*STEP_ATTRIBUTES.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "step attributes set",
        "protocol_step_attribute",
        f"{protocol_id}/{requirement}",
        old=None
        if not earlier
        else {
            "version": earlier[-1].version,
            "stage": earlier[-1].stage,
            "witness_required": earlier[-1].witness_required,
        },
        new={
            "attribute_id": added.id,
            "protocol_id": protocol_id,
            "requirement": requirement,
            "version": added.version,
            "stage": added.stage,
            "witness_required": added.witness_required,
        },
    )
    return added
