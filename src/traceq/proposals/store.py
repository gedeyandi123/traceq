"""Importing a run folder as Proposals (spec #105).

An import is one transaction: the run's provenance, every Proposal, and the Audit Trail entry
naming who imported it, or none of them. Importing a run already imported changes nothing.
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
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.proposals.keys import proposals_of
from traceq.runs.schemas import Findings, Matrix, ProtocolDraft

_META = MetaData()
RUNS = Table(
    "imported_runs",
    _META,
    Column("run_id", Text, primary_key=True),
    Column("equipment", Text),
    Column("created", DateTime(timezone=True)),
    Column("model", Text),
    Column("mode", Text),
    Column("pipeline_version", Text),
    Column("prompts", JSONB),
    Column("documents", JSONB),
)
PROPOSALS = Table(
    "proposals",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("kind", Text),
    Column("equipment", Text),
    Column("subject", JSONB),
    Column("subject_hash", Text),
    Column("ordinal", Integer),
)
RUN_PROPOSALS = Table(
    "run_proposals",
    _META,
    Column("run_id", Text, primary_key=True),
    Column("proposal_id", BigInteger, primary_key=True),
    Column("seq", Integer),
    Column("requirement", Text),
    Column("position", Integer),
    Column("content_hash", Text),
    Column("proposed", JSONB),
)


@dataclass(frozen=True)
class RunFiles:
    """What an import reads of a run folder: ``run.json`` as written, the matrix and the
    findings, and for a Review Package run its Protocol Draft."""

    meta: dict[str, Any]
    matrix: Matrix
    findings: Findings
    draft: ProtocolDraft | None = None


@dataclass(frozen=True)
class Imported:
    run_id: str
    equipment: str
    proposals: int
    already_imported: bool


def _count(session: Session, run_id: str) -> int:
    q = select(func.count()).select_from(RUN_PROPOSALS).where(RUN_PROPOSALS.c.run_id == run_id)
    return session.execute(q).scalar_one()


def import_run(session: Session, actor: audit.Actor, run: RunFiles) -> Imported:
    """Adds the run and its Proposals in the session's transaction."""
    meta = run.meta
    run_id = str(meta["run_id"])
    equipment = str(meta["corpus"]["equipment"])
    provenance: dict[str, Any] = {
        "equipment": equipment,
        "created": str(meta["created"]),
        "model": str(meta["model"]),
        "mode": str(meta["mode"]),
        "pipeline_version": str(meta["pipeline_version"]),
        "prompts": meta["prompts"],
        "documents": meta["corpus"]["documents"],
    }
    added = session.execute(
        insert(RUNS)
        .values(
            run_id=run_id,
            **{**provenance, "created": datetime.fromisoformat(provenance["created"])},
        )
        .on_conflict_do_nothing(index_elements=["run_id"])
        .returning(RUNS.c.run_id)
    ).first()
    if added is None:
        return Imported(run_id, equipment, _count(session, run_id), already_imported=True)

    proposed = proposals_of(equipment, run.matrix, run.findings, run.draft)
    if proposed:
        session.execute(
            insert(PROPOSALS)
            .values(
                [
                    {
                        "kind": p.kind,
                        "equipment": equipment,
                        "subject": p.subject,
                        "subject_hash": p.subject_hash,
                        "ordinal": p.ordinal,
                    }
                    for p in proposed
                ]
            )
            .on_conflict_do_nothing(index_elements=["subject_hash", "ordinal"])
        )
        ids = {
            (h, o): i
            for i, h, o in session.execute(
                select(PROPOSALS.c.id, PROPOSALS.c.subject_hash, PROPOSALS.c.ordinal).where(
                    PROPOSALS.c.subject_hash.in_({p.subject_hash for p in proposed})
                )
            )
        }
        session.execute(
            insert(RUN_PROPOSALS).values(
                [
                    {
                        "run_id": run_id,
                        "proposal_id": ids[(p.subject_hash, p.ordinal)],
                        "seq": seq,
                        "requirement": p.requirement,
                        "position": p.position,
                        "content_hash": p.content_hash,
                        "proposed": p.proposed,
                    }
                    for seq, p in enumerate(proposed)
                ]
            )
        )
    audit.append(
        session,
        actor,
        "run imported",
        "run",
        run_id,
        new={**provenance, "proposals": len(proposed)},
    )
    return Imported(run_id, equipment, len(proposed), already_imported=False)
