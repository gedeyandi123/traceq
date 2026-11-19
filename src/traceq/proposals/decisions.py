"""Proposal Decisions, where each Proposal of a run stands, and the decision counts (spec #105,
"Proposal Decisions", "Proposal identity").

A decision belongs to a Proposal and the content hash it was made on. Decisions are only
added; the current one is the latest for that Proposal and content. For the run a screen
shows, a Proposal is **decided** when a decision exists for its content (also one made on
another run), **changed** since it was decided when decisions exist only for other content,
and **undecided** otherwise. A decision and its Audit Trail entry are written in the session's
one transaction.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import BigInteger, Column, DateTime, MetaData, RowMapping, Table, Text, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.proposals.keys import Kind
from traceq.proposals.store import PROPOSALS, RUN_PROPOSALS, RUNS
from traceq.traceability.coverage import CoverageClass

type Verdict = Literal["accepted", "rejected", "edited"]
type State = Literal["decided", "changed", "undecided"]

KINDS: tuple[Kind, ...] = ("coverage", "check", "ai", "draft", "test_step")
ALLOWED: dict[Kind, frozenset[Verdict]] = {
    "coverage": frozenset({"accepted", "edited"}),
    "check": frozenset({"accepted", "rejected"}),
    "ai": frozenset({"accepted", "rejected"}),
    # Accepted: "real, will be fixed". It creates no task or revision (spec #196).
    "draft": frozenset({"accepted", "rejected"}),
    # Edited only together with the written Test Step it produces, by the Protocol's edit
    # route, never by ``record`` (spec #247).
    "test_step": frozenset({"accepted", "rejected"}),
}

DECISIONS = Table(
    "proposal_decisions",
    MetaData(),
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("proposal_id", BigInteger),
    Column("run_id", Text),
    Column("content_hash", Text),
    Column("decision", Text),
    Column("coverage", Text),
    Column("reason", Text),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)


class NotInRun(Exception):
    """The run is not imported, or does not hold the Proposal."""


class Refused(Exception):
    """The decision does not fit the Proposal, or a Reason for Change is missing."""


@dataclass(frozen=True)
class Decision:
    id: int
    at: datetime
    proposal_id: int
    run_id: str
    """The run on whose Proposal it was made."""
    content_hash: str
    decision: Verdict
    coverage: CoverageClass | None
    """For a Coverage row ``edited``: the class the person chose."""
    reason: str | None
    actor: audit.Actor


@dataclass(frozen=True)
class Standing:
    """Where a Proposal of a run stands."""

    proposal_id: int
    kind: Kind
    requirement: str | None
    position: int | None
    content_hash: str
    state: State
    decisions: tuple[Decision, ...]
    """For ``decided``: every decision on this content, the current one first."""
    previous: Decision | None
    """For ``changed``: the latest decision, made on other content."""
    previous_class: CoverageClass | None
    """For a ``changed`` Coverage row: the class that decision settled on, the class proposed
    on that content when accepted, the class chosen when edited."""


@dataclass(frozen=True)
class KindCounts:
    total: int
    undecided: int
    accepted: int
    edited: int
    rejected: int
    changed: int
    decided_not_proposed: int
    """Proposals of the run's Equipment with a decision that this run does not hold."""


def _decision(m: RowMapping) -> Decision:
    return Decision(
        id=m["id"],
        at=m["at"],
        proposal_id=m["proposal_id"],
        run_id=m["run_id"],
        content_hash=m["content_hash"],
        decision=cast(Verdict, m["decision"]),
        coverage=cast(CoverageClass | None, m["coverage"]),
        reason=m["reason"],
        actor=audit.Actor(subject=m["subject"], issuer=m["issuer"], name=m["name"]),
    )


def _audit_value(d: Decision) -> dict[str, Any]:
    return {
        "decision_id": d.id,
        "run_id": d.run_id,
        "content_hash": d.content_hash,
        "decision": d.decision,
        "coverage": d.coverage,
    }


def _check(kind: Kind, proposed_class: str | None, verdict: Verdict, coverage: str | None) -> None:
    if verdict not in ALLOWED[kind]:
        allowed = " or ".join(sorted(ALLOWED[kind]))
        raise Refused(f"a {kind} Proposal is {allowed}, not {verdict}")
    if verdict != "edited":
        if coverage is not None:
            raise Refused(f"{verdict} takes no class")
        if kind == "coverage" and proposed_class is None:
            raise Refused("the system proposed no class: only edited to a class is possible")
        return
    if coverage is None:
        raise Refused("edited needs the class it is changed to")
    if coverage == proposed_class:
        raise Refused(f"{coverage} is the proposed class: accept it instead")


def record(
    session: Session,
    actor: audit.Actor,
    run_id: str,
    proposal_id: int,
    verdict: Verdict,
    coverage: CoverageClass | None,
    reason: str | None,
) -> Decision:
    """Adds a decision on the content ``run_id`` proposed, with its Audit Trail entry.

    A Reason for Change is mandatory for ``rejected`` and ``edited``, and for any decision
    that replaces an earlier one on the same content."""
    held = session.execute(
        select(PROPOSALS.c.kind, RUN_PROPOSALS.c.content_hash, RUN_PROPOSALS.c.proposed)
        .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
        .where(RUN_PROPOSALS.c.run_id == run_id, RUN_PROPOSALS.c.proposal_id == proposal_id)
    ).first()
    if held is None:
        raise NotInRun(f"run {run_id} holds no Proposal {proposal_id}")
    kind = cast(Kind, held.kind)
    content_hash: str = held.content_hash
    proposed: dict[str, Any] = held.proposed
    _check(kind, proposed.get("coverage") if kind == "coverage" else None, verdict, coverage)
    reason = (reason or "").strip() or None
    if reason is None and verdict != "accepted":
        raise Refused(f"{verdict} needs a Reason for Change")
    # Decisions on one Proposal are serialised, so "replaces an earlier one" holds.
    session.execute(select(func.pg_advisory_xact_lock(proposal_id)))
    earlier_row = (
        session.execute(
            select(DECISIONS)
            .where(
                DECISIONS.c.proposal_id == proposal_id,
                DECISIONS.c.content_hash == content_hash,
            )
            .order_by(DECISIONS.c.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    earlier = None if earlier_row is None else _decision(earlier_row)
    if earlier is not None and reason is None:
        raise Refused(
            "it replaces an earlier decision on this content: a Reason for Change is needed"
        )
    added = _decision(
        session.execute(
            insert(DECISIONS)
            .values(
                proposal_id=proposal_id,
                run_id=run_id,
                content_hash=content_hash,
                decision=verdict,
                coverage=coverage,
                reason=reason,
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
            )
            .returning(*DECISIONS.c)
        )
        .mappings()
        .one()
    )
    audit.append(
        session,
        actor,
        "decision recorded",
        "proposal",
        str(proposal_id),
        old=None if earlier is None else _audit_value(earlier),
        new=_audit_value(added),
        reason=reason,
    )
    return added


def standings(session: Session, run_id: str) -> list[Standing] | None:
    """Every Proposal of an imported run in file order with where it stands; ``None`` when the
    run is not imported."""
    if session.execute(select(RUNS.c.run_id).where(RUNS.c.run_id == run_id)).first() is None:
        return None
    held = session.execute(
        select(
            PROPOSALS.c.id,
            PROPOSALS.c.kind,
            RUN_PROPOSALS.c.requirement,
            RUN_PROPOSALS.c.position,
            RUN_PROPOSALS.c.content_hash,
        )
        .join(PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
        .where(RUN_PROPOSALS.c.run_id == run_id)
        .order_by(RUN_PROPOSALS.c.seq)
    ).all()
    made: dict[int, list[Decision]] = {}
    rows = session.execute(
        select(DECISIONS)
        .where(DECISIONS.c.proposal_id.in_([h.id for h in held]))
        .order_by(DECISIONS.c.id.desc())
    ).mappings()
    for m in rows:
        d = _decision(m)
        made.setdefault(d.proposal_id, []).append(d)
    earlier = _accepted_classes(
        session, [ds[0] for ds in made.values() if ds[0].decision == "accepted"]
    )
    out: list[Standing] = []
    for h in held:
        every = made.get(h.id, [])
        same = tuple(d for d in every if d.content_hash == h.content_hash)
        state: State = "decided" if same else "changed" if every else "undecided"
        previous = every[0] if state == "changed" else None
        previous_class = None
        if previous is not None and h.kind == "coverage":
            previous_class = (
                previous.coverage
                if previous.decision == "edited"
                else earlier.get((previous.run_id, previous.proposal_id))
            )
        out.append(
            Standing(
                proposal_id=h.id,
                kind=cast(Kind, h.kind),
                requirement=h.requirement,
                position=h.position,
                content_hash=h.content_hash,
                state=state,
                decisions=same,
                previous=previous,
                previous_class=previous_class,
            )
        )
    return out


def _accepted_classes(
    session: Session, accepted: list[Decision]
) -> dict[tuple[str, int], CoverageClass | None]:
    """The class each run proposed on the Proposals of these accepted decisions."""
    if not accepted:
        return {}
    wanted = {(d.run_id, d.proposal_id) for d in accepted}
    found = session.execute(
        select(RUN_PROPOSALS.c.run_id, RUN_PROPOSALS.c.proposal_id, RUN_PROPOSALS.c.proposed).where(
            RUN_PROPOSALS.c.proposal_id.in_({p for _, p in wanted}),
            RUN_PROPOSALS.c.run_id.in_({r for r, _ in wanted}),
        )
    ).all()
    return {
        (f.run_id, f.proposal_id): cast(CoverageClass | None, f.proposed.get("coverage"))
        for f in found
        if (f.run_id, f.proposal_id) in wanted
    }


def counts(session: Session, run_id: str) -> dict[Kind, KindCounts] | None:
    """Per kind of Proposal, for an imported run; ``None`` when it is not imported."""
    stood = standings(session, run_id)
    if stood is None:
        return None
    equipment = session.execute(
        select(RUNS.c.equipment).where(RUNS.c.run_id == run_id)
    ).scalar_one()
    held = select(RUN_PROPOSALS.c.proposal_id).where(RUN_PROPOSALS.c.run_id == run_id)
    elsewhere = Counter(
        cast(Kind, k)
        for (k,) in session.execute(
            select(PROPOSALS.c.kind).where(
                PROPOSALS.c.equipment == equipment,
                PROPOSALS.c.id.not_in(held),
                PROPOSALS.c.id.in_(select(DECISIONS.c.proposal_id)),
            )
        )
    )
    out: dict[Kind, KindCounts] = {}
    for kind in KINDS:
        mine = [s for s in stood if s.kind == kind]
        current = Counter(s.decisions[0].decision for s in mine if s.state == "decided")
        out[kind] = KindCounts(
            total=len(mine),
            undecided=sum(s.state == "undecided" for s in mine),
            accepted=current["accepted"],
            edited=current["edited"],
            rejected=current["rejected"],
            changed=sum(s.state == "changed" for s in mine),
            decided_not_proposed=elsewhere[kind],
        )
    return out
