"""What a human adds to a Protocol started from the site's reviewed Protocol Draft (spec #375,
S4a1; ADR 0012, amended 26 November 2026): the requirement a draft Test Step is mapped to, and
the written reason for submitting a row on which a finding was accepted.

- **Mapping.** A draft Test Step the traceability table maps to exactly one requirement is
  that requirement's candidate. One that maps to none or to several, or whose reading the
  citation check dropped, is listed and unusable until a human maps it to exactly one
  requirement of the run. Every mapping is kept, versioned 1, 2, ... per Protocol and step,
  with its author; the latest counts. A mapping belongs to one Protocol and does not carry
  over to a later one.
- **Reason.** A Preparer writes why a row on which a finding was accepted and whose Test Step
  and Acceptance Criterion are unchanged is submitted anyway. Every version is kept, versioned
  per Protocol and finding; the latest counts. It does not carry over either.

Both are recorded in a Protocol in Draft status, under the per-Protocol lock with the status
checked inside it, each with its Audit Trail entry in the same transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle
from traceq.assembly.lifecycle import AssembledProtocol, Conflict, NotFound, Refused
from traceq.db.locks import lock_equipment
from traceq.proposals import decisions
from traceq.proposals.store import PROPOSALS, RUN_PROPOSALS
from traceq.runs.schemas import DraftStepProposal

_META = MetaData()
MAPPINGS = Table(
    "protocol_draft_mappings",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("protocol_id", BigInteger),
    Column("step", Text),
    Column("version", Integer),
    Column("requirement", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)
DOCUMENT_VERSIONS = Table(
    "document_versions",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("equipment", Text),
    Column("doc_id", Text),
    Column("rev", Integer),
    Column("doc_type", Text),
)
"""The documents the Equipment's runs read (``rounds`` owns it; read here for the latest
revision of the Protocol Draft)."""
REASONS = Table(
    "protocol_finding_reasons",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("protocol_id", BigInteger),
    Column("proposal_id", BigInteger),
    Column("version", Integer),
    Column("reason", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)


@dataclass(frozen=True)
class Mapping:
    """One version of the requirement a human mapped a draft Test Step to."""

    id: int
    at: datetime
    protocol_id: int
    step: str
    version: int
    requirement: str
    actor: audit.Actor


@dataclass(frozen=True)
class Reason:
    """One version of a Preparer's written reason on an accepted finding."""

    id: int
    at: datetime
    protocol_id: int
    proposal_id: int
    version: int
    reason: str
    actor: audit.Actor


def _mapping(m: RowMapping) -> Mapping:
    return Mapping(
        id=m["id"],
        at=m["at"],
        protocol_id=m["protocol_id"],
        step=m["step"],
        version=m["version"],
        requirement=m["requirement"],
        actor=audit.actor_of_row(m),
    )


def _reason(m: RowMapping) -> Reason:
    return Reason(
        id=m["id"],
        at=m["at"],
        protocol_id=m["protocol_id"],
        proposal_id=m["proposal_id"],
        version=m["version"],
        reason=m["reason"],
        actor=audit.actor_of_row(m),
    )


def mappings_of(session: Session, protocol_id: int) -> dict[str, tuple[Mapping, ...]]:
    """Every mapping of the Protocol per draft Test Step id, oldest first."""
    out: dict[str, list[Mapping]] = {}
    for m in session.execute(
        select(MAPPINGS).where(MAPPINGS.c.protocol_id == protocol_id).order_by(MAPPINGS.c.version)
    ).mappings():
        out.setdefault(m["step"], []).append(_mapping(m))
    return {k: tuple(v) for k, v in out.items()}


def reasons_of(session: Session, protocol_id: int) -> dict[int, tuple[Reason, ...]]:
    """Every reason of the Protocol per finding Proposal, oldest first."""
    out: dict[int, list[Reason]] = {}
    for m in session.execute(
        select(REASONS).where(REASONS.c.protocol_id == protocol_id).order_by(REASONS.c.version)
    ).mappings():
        out.setdefault(m["proposal_id"], []).append(_reason(m))
    return {k: tuple(v) for k, v in out.items()}


def effective_requirement(machine: tuple[str, ...], mappings: tuple[Mapping, ...]) -> str | None:
    """The requirement a draft Test Step stands for in a Protocol: the one the traceability
    table maps it to when exactly one, else the latest human mapping, else ``None``: unusable."""
    if len(machine) == 1:
        return machine[0]
    return mappings[-1].requirement if mappings else None


def draft_step_payloads(session: Session, run_id: str) -> dict[str, tuple[int, DraftStepProposal]]:
    """The draft Test Steps of a run by step id, each with its Proposal id."""
    out: dict[str, tuple[int, DraftStepProposal]] = {}
    for proposal_id, proposed in session.execute(
        select(RUN_PROPOSALS.c.proposal_id, RUN_PROPOSALS.c.proposed)
        .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
        .where(RUN_PROPOSALS.c.run_id == run_id, PROPOSALS.c.kind == "draft_step")
        .order_by(RUN_PROPOSALS.c.seq)
    ):
        payload = DraftStepProposal.model_validate(proposed)
        out.setdefault(payload.id, (proposal_id, payload))
    return out


def steps_of(session: Session, protocol: AssembledProtocol) -> dict[int, str | None]:
    """The requirement each draft Test Step of the Protocol's run stands for in the Protocol,
    by the step's Proposal id; ``None``: it stands for none yet. Empty for a Protocol not
    started from the draft."""
    if protocol.draft is None:
        return {}
    mappings = mappings_of(session, protocol.id)
    return {
        proposal_id: effective_requirement(payload.mapped_to, mappings.get(step, ()))
        for step, (proposal_id, payload) in draft_step_payloads(session, protocol.run_id).items()
    }


def covered(session: Session, protocol: AssembledProtocol, requirement: str) -> bool:
    """Whether a draft Test Step of the Protocol stands for the requirement: then its Test Step
    comes from the draft, never from TraceQ's own drafts."""
    return requirement in steps_of(session, protocol).values()


def accepted_steps(
    session: Session, protocol: AssembledProtocol, requirement: str, *, ignoring: int | None = None
) -> list[int]:
    """The draft Test Steps standing for the requirement in the Protocol that are accepted on
    their content (``ignoring``: one Proposal left out). A step a human mapped decides nothing
    before that mapping: an acceptance older than the mapping in force does not count, as on
    the row."""
    mappings = mappings_of(session, protocol.id)
    stands: dict[int, datetime | None] = {}
    for step, (proposal_id, payload) in draft_step_payloads(session, protocol.run_id).items():
        human = mappings.get(step, ())
        if effective_requirement(payload.mapped_to, human) == requirement:
            stands[proposal_id] = human[-1].at if human and len(payload.mapped_to) != 1 else None
    out: list[int] = []
    for s in decisions.standings(session, protocol.run_id) or []:
        if s.kind != "draft_step" or s.proposal_id not in stands or s.proposal_id == ignoring:
            continue
        if s.state != "decided" or s.decisions[0].decision != "accepted":
            continue
        mapped_at = stands[s.proposal_id]
        if mapped_at is None or s.decisions[0].at > mapped_at:
            out.append(s.proposal_id)
    return out


def latest_revision(session: Session, protocol: AssembledProtocol) -> int | None:
    """The latest revision of the Protocol Draft the Protocol is pinned to that the
    Equipment's runs have read; ``None`` for a Protocol not started from the draft."""
    if protocol.draft is None:
        return None
    return session.execute(
        select(func.max(DOCUMENT_VERSIONS.c.rev)).where(
            DOCUMENT_VERSIONS.c.equipment == protocol.equipment,
            DOCUMENT_VERSIONS.c.doc_id == protocol.draft.doc,
            DOCUMENT_VERSIONS.c.doc_type == "protocol_draft",
        )
    ).scalar_one()


def upload_revision_being_read(session: Session, protocol: AssembledProtocol) -> int | None:
    """The newest revision of an upload of the Equipment that is queued or running and newer
    than the one the Protocol is pinned to: a revision on its way that no run has registered
    yet. ``None`` when there is none (a failed or finished upload does not count)."""
    if protocol.draft is None:
        return None
    return session.execute(
        text(
            "SELECT MAX(rev) FROM upload_jobs WHERE equipment = :equipment"
            " AND status IN ('queued', 'running') AND rev > :pinned"
        ),
        {"equipment": protocol.equipment, "pinned": protocol.draft.rev},
    ).scalar_one()


def uploader_of_pinned(session: Session, protocol: AssembledProtocol) -> audit.Actor | None:
    """Who uploaded the revision of the Protocol Draft the Protocol is pinned to, as the upload
    queue records them (the uploader of that revision only, not of earlier ones). Only a
    succeeded job counts: a failed one registered no revision. ``None`` for a Protocol not
    started from the draft, and for a revision that arrived another way than an upload (no
    succeeded job holds it)."""
    if protocol.draft is None:
        return None
    row = (
        session.execute(
            text(
                "SELECT subject, issuer, name FROM upload_jobs"
                " WHERE equipment = :equipment AND rev = :rev AND status = 'succeeded'"
            ),
            {"equipment": protocol.equipment, "rev": protocol.draft.rev},
        )
        .mappings()
        .first()
    )
    return None if row is None else audit.actor_of_row(row)


class PinnedBehind(Conflict):
    """The Protocol is pinned to an older revision of the Protocol Draft than the latest."""

    code = "pinned_behind"


class StaleDraftRead(Conflict):
    """The caller read another revision of the Protocol Draft than the latest."""

    code = "stale_draft"


class UploaderApproves(Conflict):
    """The Approver uploaded the revision of the Protocol Draft the Protocol is pinned to."""

    code = "uploader_approves"


def conflict_code(e: Exception) -> str | None:
    """The stable code of a refusal about the Protocol Draft (its revision, or who uploaded
    it), for the API to send alongside its words; ``None`` for any other conflict."""
    return e.code if isinstance(e, PinnedBehind | StaleDraftRead | UploaderApproves) else None


def check_latest(session: Session, protocol: AssembledProtocol, expected: int | None) -> int | None:
    """What a signature on a Protocol started from the draft needs. Returns the latest draft
    revision the Equipment has read now (``None`` for a Protocol not started from the draft,
    which ignores ``expected``).

    ``Refused`` without ``expected`` (the latest revision the caller read). ``Conflict`` when
    the Protocol is pinned to an older revision than the latest one (ADR 0012, amended 27
    November 2026): it never re-syncs, so it is withdrawn and started again from the latest
    revision, whatever the caller read. ``Conflict`` too when the caller read another revision
    than the latest (the page is stale: reload before signing)."""
    if protocol.draft is None:
        return None
    # The lock the revision writer holds (an import registering the draft): a revision being
    # written is read once it is committed, never missed.
    lock_equipment(session, protocol.equipment)
    latest = latest_revision(session, protocol)
    reading = upload_revision_being_read(session, protocol)
    if expected is None:
        raise Refused(
            f"Protocol {protocol.id} was started from a Protocol Draft: name the latest draft"
            " revision you read (expected_latest_draft_rev)"
        )
    if reading is not None and (latest is None or reading > latest):
        raise PinnedBehind(
            f"Protocol {protocol.id} is pinned to revision {protocol.draft.rev} of the Protocol"
            f" Draft, but revision {reading} is being read: it is not signed. Wait for it, then"
            " withdraw this Protocol (or return it to Draft and withdraw it) and start a new"
            " Protocol from the latest revision"
        )
    if latest is not None and latest > protocol.draft.rev:
        raise PinnedBehind(
            f"Protocol {protocol.id} is pinned to revision {protocol.draft.rev} of the Protocol"
            f" Draft, but revision {latest} has arrived: it is not signed. Withdraw it (or"
            " return it to Draft and withdraw it), then start a new Protocol from the latest"
            " revision"
        )
    if latest != expected:
        raise StaleDraftRead(
            f"a newer revision of the Protocol Draft arrived (revision {latest}, you read"
            f" {expected}): reload before signing"
        )
    return latest


def _requirements(session: Session, run_id: str) -> set[str]:
    return set(
        session.execute(
            select(RUN_PROPOSALS.c.requirement)
            .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
            .where(RUN_PROPOSALS.c.run_id == run_id, PROPOSALS.c.kind == "coverage")
        ).scalars()
    )


def _mapping_audit(m: Mapping) -> dict[str, Any]:
    return {
        "mapping_id": m.id,
        "protocol_id": m.protocol_id,
        "step": m.step,
        "version": m.version,
        "requirement": m.requirement,
    }


def map_step(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    step: str,
    requirement: str,
) -> Mapping:
    """Maps a draft Test Step the traceability table maps to none or several requirements, or
    that the citation check dropped, to exactly one requirement of the Protocol's run. The
    Protocol must be in Draft status and started from the draft."""
    protocol = lifecycle.locked(
        session,
        protocol_id,
        "draft",
        "a draft Test Step is mapped only while the Protocol is in Draft status",
    )
    if protocol.draft is None:
        raise Conflict(f"Protocol {protocol_id} was not started from a Protocol Draft")
    found = draft_step_payloads(session, protocol.run_id).get(step)
    if found is None:
        raise NotFound(f"run {protocol.run_id} read no draft Test Step {step}")
    proposal_id, payload = found
    if len(payload.mapped_to) == 1:
        raise Conflict(
            f"{step} is traced to exactly one requirement ({payload.mapped_to[0]}) by the"
            " draft: there is nothing to map"
        )
    if requirement not in _requirements(session, protocol.run_id):
        raise NotFound(f"run {protocol.run_id} has no requirement {requirement}")
    earlier = mappings_of(session, protocol_id).get(step, ())
    if earlier and earlier[-1].requirement == requirement:
        return earlier[-1]  # the same mapping again: no new version, nothing to decide again
    if earlier:
        lifecycle.lock_requirement(session, protocol.equipment, earlier[-1].requirement)
    lifecycle.lock_requirement(session, protocol.equipment, requirement)
    from traceq.assembly import written

    if any(
        v.from_proposal_id == proposal_id
        for versions in written.versions_of(session, protocol_id).values()
        for v in versions
    ):
        raise Conflict(
            f"{step} was edited into a written Test Step of this Protocol: remove that Test"
            " Step before mapping it again"
        )
    added = _mapping(
        session.execute(
            insert(MAPPINGS)
            .values(
                protocol_id=protocol_id,
                step=step,
                version=len(earlier) + 1,
                requirement=requirement,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*MAPPINGS.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "draft step mapped",
        "protocol_draft_mapping",
        f"{protocol_id}/{step}",
        old=None if not earlier else _mapping_audit(earlier[-1]),
        new=_mapping_audit(added),
    )
    return added


def give_reason(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    proposal_id: int,
    reason: str,
) -> Reason:
    """Records why the row of an accepted finding is submitted as it is. The finding must be a
    finding of the Protocol Draft of the Protocol's run, accepted on its content."""
    protocol = lifecycle.locked(
        session,
        protocol_id,
        "draft",
        "a reason is given only while the Protocol is in Draft status",
    )
    if protocol.draft is None:
        raise Conflict(f"Protocol {protocol_id} was not started from a Protocol Draft")
    reason = reason.strip()
    if not reason:
        raise Refused("a reason for an accepted finding must be written")
    stood = next(
        (
            s
            for s in decisions.standings(session, protocol.run_id) or []
            if s.proposal_id == proposal_id and s.kind == "draft"
        ),
        None,
    )
    if stood is None:
        raise NotFound(f"run {protocol.run_id} holds no draft finding {proposal_id}")
    if stood.state != "decided" or stood.decisions[0].decision != "accepted":
        raise Conflict(f"finding {proposal_id} is not accepted: it needs no reason")
    earlier = reasons_of(session, protocol_id).get(proposal_id, ())
    added = _reason(
        session.execute(
            insert(REASONS)
            .values(
                protocol_id=protocol_id,
                proposal_id=proposal_id,
                version=len(earlier) + 1,
                reason=reason,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*REASONS.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "finding reason recorded",
        "protocol_finding_reason",
        f"{protocol_id}/{proposal_id}",
        old=None if not earlier else {"version": earlier[-1].version, "reason": earlier[-1].reason},
        new={
            "reason_id": added.id,
            "protocol_id": protocol_id,
            "proposal_id": proposal_id,
            "version": added.version,
            "reason": added.reason,
        },
        reason=reason,
    )
    return added


def draft_pinned(protocol: AssembledProtocol) -> bool:
    """Whether the Protocol was started from the site's Protocol Draft."""
    return protocol.draft is not None
