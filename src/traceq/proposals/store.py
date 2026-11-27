"""Importing a run folder as Proposals (spec #105).

An import is one transaction: the run's provenance, every Proposal, and the Audit Trail entry
naming who imported it, or none of them. Importing a run already imported changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

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
from traceq.runs.schemas import Completeness, DraftedTestSteps, Findings, Matrix, ProtocolDraft

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
    Column("completeness", JSONB),
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
    findings, for a Review Package run its Protocol Draft, and the drafted Test Steps when the
    folder holds ``drafts.json``."""

    meta: dict[str, Any]
    matrix: Matrix
    findings: Findings
    draft: ProtocolDraft | None = None
    drafted: DraftedTestSteps | None = None
    completeness: Completeness | None = None


@dataclass(frozen=True)
class Imported:
    run_id: str
    equipment: str
    proposals: int
    already_imported: bool


def _count(session: Session, run_id: str) -> int:
    q = select(func.count()).select_from(RUN_PROPOSALS).where(RUN_PROPOSALS.c.run_id == run_id)
    return session.execute(q).scalar_one()


def draft_document(run: RunFiles) -> dict[str, Any] | None:
    """The Protocol Draft a Review Package run read, as ``{doc_id, rev, sha256}``: the run's
    own record of it, else the document its ``protocol_draft.json`` names."""
    package: Any = run.meta.get("review_package")
    named: Any = None
    if isinstance(package, dict):
        named = cast(dict[str, Any], package).get("document")
    if isinstance(named, dict):
        found = cast(dict[str, Any], named)
        doc_id, rev, sha = found.get("doc_id"), found.get("rev"), found.get("sha256")
        if doc_id is not None and rev is not None and sha is not None:
            return {"doc_id": str(doc_id), "rev": int(rev), "sha256": str(sha)}
    if run.draft is not None:
        d = run.draft.document
        return {"doc_id": d.doc_id, "rev": d.rev, "sha256": d.sha256}
    return None


def import_run(session: Session, actor: audit.Actor, run: RunFiles) -> Imported:
    """Adds the run and its Proposals in the session's transaction. The run's documents are the
    corpus documents it read and, for a Review Package run, its Protocol Draft: re-uploading a
    revision is a run that holds that revision again, not one that removed it."""
    meta = run.meta
    run_id = str(meta["run_id"])
    equipment = str(meta["corpus"]["equipment"])
    drafted = draft_document(run)
    documents: list[Any] = list(meta["corpus"]["documents"])
    if drafted is not None and not any(
        d.get("doc_id") == drafted["doc_id"] and d.get("rev") == drafted["rev"] for d in documents
    ):
        documents.append(drafted)
    provenance: dict[str, Any] = {
        "equipment": equipment,
        "created": str(meta["created"]),
        "model": str(meta["model"]),
        "mode": str(meta["mode"]),
        "pipeline_version": str(meta["pipeline_version"]),
        "prompts": meta["prompts"],
        "documents": documents,
    }
    completeness_json = (
        None if run.completeness is None else run.completeness.model_dump(mode="json")
    )
    added = session.execute(
        insert(RUNS)
        .values(
            run_id=run_id,
            **{
                **provenance,
                "created": datetime.fromisoformat(provenance["created"]),
                "completeness": completeness_json,
            },
        )
        .on_conflict_do_nothing(index_elements=["run_id"])
        .returning(RUNS.c.run_id)
    ).first()
    if added is None:
        return Imported(run_id, equipment, _count(session, run_id), already_imported=True)

    proposed = proposals_of(equipment, run.matrix, run.findings, run.draft, run.drafted)
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
