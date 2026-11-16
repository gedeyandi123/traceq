"""The database routes over runs: importing a run as Proposals and reading them (spec #105).

Every route needs a valid bearer token; importing needs the deciding role, so the Audit Trail
names who imported which run. Without a database (default settings) the routes answer 401.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import Engine

from traceq.audit import Actor
from traceq.db import transaction
from traceq.identity import Principal
from traceq.proposals.store import RunFiles, import_run, run_proposals
from traceq.runs.api import FINDINGS_FILE, MATRIX_FILE, RUN_FILE, find_run, read_served
from traceq.runs.schemas import Findings, Matrix


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImportedRun(_Model):
    """A run imported as Proposals."""

    run_id: str
    equipment: str
    proposals: int
    """How many Proposals the run holds."""
    already_imported: bool
    """True when the run was imported before: nothing changed."""


class Proposal(_Model):
    """A Proposal of a run, and where it stands in the run's files."""

    id: int
    """Its identity across runs: the same subject gets the same id in every run."""
    kind: Literal["coverage", "check", "ai"]
    """A Coverage row, or the layer of a finding (Check Finding, AI Finding)."""
    requirement: str | None
    """For a Coverage row: the requirement id in ``matrix.json``."""
    position: int | None
    """For a finding: its position in its layer's list in ``findings.json``, from 0."""
    content_hash: str
    """What this run proposed about it, hashed as the content a decision rests on."""
    state: Literal["undecided"]


def create_router(runs: Path, db: Engine | None, principal: Callable[..., Principal]) -> APIRouter:
    """``db``: the database as the application role; none with default settings, when
    ``principal`` refuses every request."""
    router = APIRouter()

    def database() -> Engine:
        if db is None:  # unreachable: without a database no token is accepted
            raise HTTPException(401, "no database is configured")
        return db

    @router.post("/runs/{run_id}/import", operation_id="importRun")
    def import_(run_id: str, who: Annotated[Principal, Depends(principal)]) -> ImportedRun:
        """Imports a run folder as Proposals, in one transaction. Importing a run already
        imported changes nothing. Needs the deciding role."""
        if not who.may_decide:
            raise HTTPException(403, "importing a run needs the deciding role")
        folder = find_run(runs, run_id)
        if folder is None:
            raise HTTPException(404, f"no run {run_id}")
        try:
            meta: dict[str, Any] = read_served(folder / RUN_FILE)
            files = RunFiles(
                meta=meta,
                matrix=Matrix.model_validate(read_served(folder / MATRIX_FILE)),
                findings=Findings.model_validate(read_served(folder / FINDINGS_FILE)),
            )
        except (OSError, ValueError, ValidationError) as e:
            raise HTTPException(422, f"{run_id} is not a run folder that can be imported") from e
        if meta.get("run_id") != run_id:
            raise HTTPException(422, f"the run folder {run_id} names another run id")
        actor = Actor(subject=who.subject, issuer=who.issuer, name=who.name)
        with transaction(database()) as session:
            done = import_run(session, actor, files)
        return ImportedRun(
            run_id=done.run_id,
            equipment=done.equipment,
            proposals=done.proposals,
            already_imported=done.already_imported,
        )

    @router.get("/runs/{run_id}/proposals", operation_id="listProposals")
    def list_proposals(
        run_id: str, who: Annotated[Principal, Depends(principal)]
    ) -> list[Proposal]:
        """The Proposals of an imported run, in the order of its files, with their state."""
        with transaction(database()) as session:
            stored = run_proposals(session, run_id)
        if stored is None:
            raise HTTPException(404, f"run {run_id} is not imported")
        return [
            Proposal(
                id=p.id,
                kind=p.kind,
                requirement=p.requirement,
                position=p.position,
                content_hash=p.content_hash,
                state="undecided",
            )
            for p in stored
        ]

    return router
