"""Written Test Steps of a Protocol in Draft status, and editing a drafted Test Step (spec #247,
"Written Test Steps", "Acceptance Criterion shapes", "Concurrency"; ADR 0012).

A written Test Step belongs to one Protocol and one requirement and is versioned 1, 2, ...;
each version holds the full content or is a removal, which takes it back (the row falls back
to its accepted draft or to Vendor Reference). Adding a version needs a Protocol in Draft
status and no Reason for Change. Editing a drafted Test Step records the ``edited`` decision,
with its Reason for Change, and the version it produces in one transaction.

A row never holds two Test Steps: writing is refused while a draft of the requirement is
accepted on the Protocol's run, and accepting a draft is refused while the open Protocol of
its Equipment holds a written Test Step for it. Both take one lock per Equipment and
requirement; every write takes the per-Protocol lock first and checks the status inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
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
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle
from traceq.assembly.lifecycle import AssembledProtocol, Conflict, NotFound
from traceq.proposals import decisions
from traceq.proposals.store import PROPOSALS, RUN_PROPOSALS
from traceq.traceability.values import Number, OneOf, Present, Range

type Acceptance = Annotated[Range | Number | OneOf | Present, Field(discriminator="type")]
"""The shapes an Acceptance Criterion a human sets may take: range (one or two bounds, with
unit), number (an exact value with unit), one of (allowed values), present (no value). Free
text is not one: Execution must judge every Test Step by code (ADR 0002)."""


class WrittenContent(BaseModel):
    """The content of a Test Step a human writes or edits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1)
    method: str = Field(min_length=1)
    instrument: str | None = None
    acceptance: Acceptance

    @model_validator(mode="after")
    def _filled(self) -> WrittenContent:
        if not self.description.strip() or not self.method.strip():
            raise ValueError("a Test Step needs a description and a method")
        a = self.acceptance
        if isinstance(a, Present) and a.value is not None:
            raise ValueError("present takes no value")
        if isinstance(a, Range | Number) and not a.unit.strip():
            raise ValueError("a range or a number needs a unit")
        if isinstance(a, Range) and a.min is not None and a.max is not None and a.min > a.max:
            raise ValueError("a range's lower bound is above its upper bound")
        if isinstance(a, OneOf) and not all(v.strip() for v in a.allowed):
            raise ValueError("one of needs non-blank allowed values")
        return self


_META = MetaData()
WRITTEN = Table(
    "written_test_steps",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("protocol_id", BigInteger),
    Column("requirement", Text),
    Column("version", Integer),
    Column("removed", Boolean),
    Column("description", Text),
    Column("method", Text),
    Column("instrument", Text),
    Column("acceptance", JSONB),
    Column("from_proposal_id", BigInteger),
    Column("decision_id", BigInteger),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)


@dataclass(frozen=True)
class WrittenVersion:
    id: int
    at: datetime
    protocol_id: int
    requirement: str
    version: int
    content: WrittenContent | None
    """``None`` for a removal."""
    from_proposal_id: int | None
    """For a version made by the edit route: the drafted Test Step it was edited from."""
    decision_id: int | None
    """For a version made by the edit route: the ``edited`` decision recorded with it."""
    actor: audit.Actor

    @property
    def removed(self) -> bool:
        return self.content is None


def _version(m: RowMapping) -> WrittenVersion:
    content = (
        None
        if m["removed"]
        else WrittenContent(
            description=m["description"],
            method=m["method"],
            instrument=m["instrument"],
            acceptance=m["acceptance"],
        )
    )
    return WrittenVersion(
        id=m["id"],
        at=m["at"],
        protocol_id=m["protocol_id"],
        requirement=m["requirement"],
        version=m["version"],
        content=content,
        from_proposal_id=m["from_proposal_id"],
        decision_id=m["decision_id"],
        actor=audit.actor_of_row(m),
    )


def versions_of(session: Session, protocol_id: int) -> dict[str, tuple[WrittenVersion, ...]]:
    """Every version of the Protocol's written Test Steps per requirement, oldest first."""
    out: dict[str, list[WrittenVersion]] = {}
    for m in session.execute(
        select(WRITTEN).where(WRITTEN.c.protocol_id == protocol_id).order_by(WRITTEN.c.version)
    ).mappings():
        out.setdefault(m["requirement"], []).append(_version(m))
    return {k: tuple(v) for k, v in out.items()}


def current(versions: tuple[WrittenVersion, ...]) -> WrittenVersion | None:
    """The written Test Step in force: the latest version unless it is a removal."""
    if not versions or versions[-1].removed:
        return None
    return versions[-1]


def carried_over(session: Session, protocol: AssembledProtocol) -> dict[str, WrittenContent]:
    """Per requirement, the latest version in the most recent withdrawn Protocol of the
    Equipment started before this one, unless that version is a removal: what the form of a
    row of this Protocol starts from. A written Test Step itself does not carry over."""
    withdrawn = [
        p
        for p in lifecycle.of_equipment(session, protocol.equipment)
        if p.id < protocol.id and p.status == "withdrawn"
    ]
    if not withdrawn:
        return {}
    out: dict[str, WrittenContent] = {}
    for requirement, versions in versions_of(session, withdrawn[-1].id).items():
        latest = current(versions)
        if latest is not None and latest.content is not None:
            out[requirement] = latest.content
    return out


def _audit_value(v: WrittenVersion) -> dict[str, Any]:
    return {
        "written_id": v.id,
        "protocol_id": v.protocol_id,
        "requirement": v.requirement,
        "version": v.version,
        "removed": v.removed,
        "test_step": None if v.content is None else v.content.model_dump(mode="json"),
        "from_proposal_id": v.from_proposal_id,
        "decision_id": v.decision_id,
    }


def _add(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    requirement: str,
    earlier: tuple[WrittenVersion, ...],
    content: WrittenContent | None,
    from_proposal_id: int | None = None,
    decision_id: int | None = None,
) -> WrittenVersion:
    fields: dict[str, Any] = (
        {"removed": True}
        if content is None
        else {"removed": False, **content.model_dump(mode="json")}
    )
    added = _version(
        session.execute(
            insert(WRITTEN)
            .values(
                protocol_id=protocol_id,
                requirement=requirement,
                version=len(earlier) + 1,
                from_proposal_id=from_proposal_id,
                decision_id=decision_id,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
                **fields,
            )
            .returning(*WRITTEN.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "test step removed" if added.removed else "test step written",
        "written_test_step",
        f"{protocol_id}/{requirement}",
        old=None if not earlier else _audit_value(earlier[-1]),
        new=_audit_value(added),
    )
    return added


def _draft_protocol(session: Session, protocol_id: int) -> AssembledProtocol:
    """The Protocol under its lock, refused unless in Draft status."""
    return lifecycle.locked(
        session,
        protocol_id,
        "draft",
        "Test Steps are written only while it is in Draft status",
    )


def _requirements(session: Session, run_id: str) -> set[str]:
    return set(
        session.execute(
            select(RUN_PROPOSALS.c.requirement)
            .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
            .where(RUN_PROPOSALS.c.run_id == run_id, PROPOSALS.c.kind == "coverage")
        ).scalars()
    )


def _accepted_drafts(session: Session, run_id: str, requirement: str) -> list[int]:
    """The drafted Test Steps of the requirement currently accepted on the run's content."""
    return [
        s.proposal_id
        for s in decisions.standings(session, run_id) or []
        if s.kind == "test_step"
        and s.requirement == requirement
        and s.state == "decided"
        and s.decisions[0].decision == "accepted"
    ]


def write(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    requirement: str,
    content: WrittenContent | None,
) -> WrittenVersion:
    """Adds a version of the requirement's written Test Step: its full content, or a removal
    (``content`` ``None``). No Reason for Change; the Protocol must be in Draft status."""
    protocol = _draft_protocol(session, protocol_id)
    if requirement not in _requirements(session, protocol.run_id):
        raise NotFound(f"run {protocol.run_id} has no requirement {requirement}")
    lifecycle.lock_requirement(session, protocol.equipment, requirement)
    earlier = versions_of(session, protocol_id).get(requirement, ())
    if content is None:
        if current(earlier) is None:
            raise Conflict(f"{requirement} has no written Test Step to remove")
    elif _accepted_drafts(session, protocol.run_id, requirement):
        raise Conflict(
            f"a drafted Test Step of {requirement} is accepted: reject it, or replace that"
            " decision, before writing one, so the row holds one Test Step"
        )
    return _add(session, actor, protocol_id, requirement, earlier, content)


def edit(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    proposal_id: int,
    reason: str,
    content: WrittenContent,
) -> tuple[decisions.Decision, WrittenVersion]:
    """Records the ``edited`` decision on a drafted Test Step of the Protocol's run, with its
    Reason for Change, and the version of the written Test Step it produces, edited from it."""
    protocol = _draft_protocol(session, protocol_id)
    requirement = session.execute(
        select(RUN_PROPOSALS.c.requirement)
        .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
        .where(
            RUN_PROPOSALS.c.run_id == protocol.run_id,
            RUN_PROPOSALS.c.proposal_id == proposal_id,
            PROPOSALS.c.kind == "test_step",
        )
    ).scalar_one_or_none()
    if requirement is None:
        raise NotFound(f"run {protocol.run_id} holds no drafted Test Step {proposal_id}")
    lifecycle.lock_requirement(session, protocol.equipment, requirement)
    earlier = versions_of(session, protocol_id).get(requirement, ())
    if current(earlier) is not None:
        raise Conflict(
            f"{requirement} has a written Test Step: change it instead of editing a draft"
        )
    if [p for p in _accepted_drafts(session, protocol.run_id, requirement) if p != proposal_id]:
        raise Conflict(
            f"another drafted Test Step of {requirement} is accepted: reject it, or replace"
            " that decision, first, so the row holds one Test Step"
        )
    made = decisions.record(
        session, actor, protocol.run_id, proposal_id, "edited", None, reason, edit=True
    )
    added = _add(session, actor, protocol_id, requirement, earlier, content, proposal_id, made.id)
    return made, added


def guard_accepting(session: Session, run_id: str, proposal_id: int) -> None:
    """Before a drafted Test Step is accepted: refused while the open Protocol of its Equipment
    holds a written Test Step for its requirement. Takes the requirement's lock, so a write
    for it cannot land in between. Anything else passes: ``decisions.record`` judges it."""
    held = session.execute(
        select(PROPOSALS.c.kind, PROPOSALS.c.equipment, RUN_PROPOSALS.c.requirement)
        .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
        .where(RUN_PROPOSALS.c.run_id == run_id, RUN_PROPOSALS.c.proposal_id == proposal_id)
    ).first()
    if held is None or held.kind != "test_step" or held.requirement is None:
        return
    equipment = cast(str, held.equipment)
    requirement = cast(str, held.requirement)
    lifecycle.lock_requirement(session, equipment, requirement)
    if [p for p in _accepted_drafts(session, run_id, requirement) if p != proposal_id]:
        raise decisions.Conflict(
            f"another drafted Test Step of {requirement} is accepted: reject it, or replace"
            " that decision, first, so the row holds one Test Step"
        )
    for p in lifecycle.of_equipment(session, equipment):
        if p.status in lifecycle.OPEN and current(versions_of(session, p.id).get(requirement, ())):
            raise decisions.Conflict(
                f"Protocol {p.id} of {equipment} holds a written Test Step for {requirement}:"
                " remove it before accepting a draft, so the row holds one Test Step"
            )
