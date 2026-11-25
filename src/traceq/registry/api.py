"""Equipment Registry route: merges disk runs with DB lifecycle state (Step 7, #326).

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.engine import Engine

from traceq.assembly import lifecycle as assembly_lifecycle
from traceq.assembly.lifecycle import EVENTS as PROTOCOL_EVENTS
from traceq.assembly.lifecycle import PROTOCOLS
from traceq.db import transaction
from traceq.execution import lifecycle as execution_lifecycle
from traceq.execution.lifecycle import EVENTS as EXECUTION_EVENTS
from traceq.execution.lifecycle import EXECUTIONS
from traceq.execution.results import DEVIATION_EVENTS, DEVIATIONS
from traceq.identity import Principal
from traceq.reports import QualificationReportSnapshot, TechnicalConclusion
from traceq.rounds.store import REPORT_EXPORTS, REVIEW_ROUND_EVENTS, REVIEW_ROUNDS, RoundStatus
from traceq.runs.api import RunSummary, scan_runs


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LatestRoundSummary(_Model):
    id: int
    round_number: int
    run_id: str
    status: RoundStatus
    at: datetime


class LatestProtocolSummary(_Model):
    id: int
    run_id: str
    status: assembly_lifecycle.Status
    at: datetime


class LatestExecutionSummary(_Model):
    id: int
    protocol_id: int
    run_id: str
    status: execution_lifecycle.Status
    open_deviations: int
    at: datetime


class LatestQualificationReportSummary(_Model):
    id: int
    execution_id: int
    run_id: str
    revision_number: int
    technical_conclusion: TechnicalConclusion
    next_requalification_date: date | None
    pdf_sha256: str
    at: datetime


class EquipmentSummary(_Model):
    """One Equipment's merged disk + DB lifecycle summary."""

    equipment: str
    run_count: int
    latest_run: RunSummary | None = None
    latest_round: LatestRoundSummary | None = None
    latest_protocol: LatestProtocolSummary | None = None
    latest_execution: LatestExecutionSummary | None = None
    latest_qualification_report: LatestQualificationReportSummary | None = None


def create_router(runs: Path, db: Engine | None, principal: Callable[..., Principal]) -> APIRouter:
    router = APIRouter()

    def database() -> Engine:
        if db is None:
            raise HTTPException(401, "no database is configured")
        return db

    @router.get("/equipment", operation_id="listEquipment")
    def list_equipment(
        who: Annotated[Principal, Depends(principal)],
    ) -> list[EquipmentSummary]:
        """Lists every Equipment known from disk runs or database records, with latest round,
        protocol, execution, and qualification report summaries."""
        disk_runs = scan_runs(runs)
        runs_by_eq: dict[str, list[RunSummary]] = {}
        for r in disk_runs:
            runs_by_eq.setdefault(r.equipment, []).append(r)

        latest_round_by_eq: dict[str, LatestRoundSummary] = {}
        latest_proto_by_eq: dict[str, LatestProtocolSummary] = {}
        latest_exec_by_eq: dict[str, LatestExecutionSummary] = {}
        latest_qual_by_eq: dict[str, LatestQualificationReportSummary] = {}

        with transaction(database()) as session:
            # 1. Review rounds
            round_rows = (
                session.execute(
                    select(
                        REVIEW_ROUNDS.c.id,
                        REVIEW_ROUNDS.c.equipment,
                        REVIEW_ROUNDS.c.round_number,
                        REVIEW_ROUNDS.c.run_id,
                        REVIEW_ROUNDS.c.at,
                    ).order_by(REVIEW_ROUNDS.c.round_number.desc(), REVIEW_ROUNDS.c.id.desc())
                )
                .mappings()
                .all()
            )
            round_ids_seen: dict[str, int] = {}
            for rr in round_rows:
                eq = str(rr["equipment"])
                if eq in latest_round_by_eq:
                    continue
                rid = int(rr["id"])
                round_ids_seen[eq] = rid
                ev = (
                    session.execute(
                        select(REVIEW_ROUND_EVENTS.c.event, REVIEW_ROUND_EVENTS.c.at)
                        .where(REVIEW_ROUND_EVENTS.c.round_id == rid)
                        .order_by(REVIEW_ROUND_EVENTS.c.id.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                status: RoundStatus = "open"
                ev_at: datetime = rr["at"]
                if ev is not None:
                    ev_kind = str(ev["event"])
                    if ev_kind == "returned_for_revision":
                        status = "returned_for_revision"
                    elif ev_kind == "ready_for_protocol":
                        status = "ready_for_protocol"
                    ev_at = ev["at"]
                latest_round_by_eq[eq] = LatestRoundSummary(
                    id=rid,
                    round_number=int(rr["round_number"]),
                    run_id=str(rr["run_id"]),
                    status=status,
                    at=ev_at,
                )

            # 2. Protocols
            proto_rows = (
                session.execute(
                    select(PROTOCOLS.c.id, PROTOCOLS.c.equipment, PROTOCOLS.c.run_id).order_by(
                        PROTOCOLS.c.id.desc()
                    )
                )
                .mappings()
                .all()
            )
            proto_meta_by_id: dict[int, tuple[str, str]] = {}
            for pr in proto_rows:
                pid = int(pr["id"])
                eq = str(pr["equipment"])
                run_id = str(pr["run_id"])
                proto_meta_by_id[pid] = (eq, run_id)
                if eq in latest_proto_by_eq:
                    continue
                ev = (
                    session.execute(
                        select(PROTOCOL_EVENTS.c.event, PROTOCOL_EVENTS.c.at)
                        .where(PROTOCOL_EVENTS.c.protocol_id == pid)
                        .order_by(PROTOCOL_EVENTS.c.id.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if ev is None:
                    continue
                p_status = assembly_lifecycle.STATUS_AFTER[ev["event"]]
                latest_proto_by_eq[eq] = LatestProtocolSummary(
                    id=pid,
                    run_id=run_id,
                    status=p_status,
                    at=ev["at"],
                )

            # 3. Executions
            exec_rows = (
                session.execute(
                    select(EXECUTIONS.c.id, EXECUTIONS.c.protocol_id).order_by(
                        EXECUTIONS.c.id.desc()
                    )
                )
                .mappings()
                .all()
            )
            exec_meta_by_id: dict[int, tuple[str, int, str]] = {}
            for er in exec_rows:
                eid = int(er["id"])
                pid = int(er["protocol_id"])
                if pid not in proto_meta_by_id:
                    continue
                eq, run_id = proto_meta_by_id[pid]
                exec_meta_by_id[eid] = (eq, pid, run_id)
                if eq in latest_exec_by_eq:
                    continue
                ev = (
                    session.execute(
                        select(EXECUTION_EVENTS.c.event, EXECUTION_EVENTS.c.at)
                        .where(EXECUTION_EVENTS.c.execution_id == eid)
                        .order_by(EXECUTION_EVENTS.c.id.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if ev is None:
                    continue
                e_status = execution_lifecycle.STATUS_AFTER[ev["event"]]
                dev_ids = list(
                    session.execute(
                        select(DEVIATIONS.c.id).where(DEVIATIONS.c.execution_id == eid)
                    ).scalars()
                )
                open_devs = 0
                for did in dev_ids:
                    latest_dev_ev = session.execute(
                        select(DEVIATION_EVENTS.c.event)
                        .where(DEVIATION_EVENTS.c.deviation_id == did)
                        .order_by(DEVIATION_EVENTS.c.id.desc())
                        .limit(1)
                    ).scalar_one_or_none()
                    if latest_dev_ev != "closed":
                        open_devs += 1
                latest_exec_by_eq[eq] = LatestExecutionSummary(
                    id=eid,
                    protocol_id=pid,
                    run_id=run_id,
                    status=e_status,
                    open_deviations=open_devs,
                    at=ev["at"],
                )

            # 4. Qualification reports
            qual_rows = (
                session.execute(
                    select(
                        REPORT_EXPORTS.c.id,
                        REPORT_EXPORTS.c.execution_id,
                        REPORT_EXPORTS.c.snapshot_json,
                        REPORT_EXPORTS.c.pdf_sha256,
                        REPORT_EXPORTS.c.at,
                    )
                    .where(REPORT_EXPORTS.c.report_kind == "qualification")
                    .order_by(REPORT_EXPORTS.c.id.desc())
                )
                .mappings()
                .all()
            )
            for qr in qual_rows:
                eid = int(qr["execution_id"])
                if eid not in exec_meta_by_id:
                    continue
                eq, _pid, run_id = exec_meta_by_id[eid]
                if eq in latest_qual_by_eq:
                    continue
                snap = QualificationReportSnapshot.model_validate(qr["snapshot_json"])
                latest_qual_by_eq[eq] = LatestQualificationReportSummary(
                    id=int(qr["id"]),
                    execution_id=eid,
                    run_id=run_id,
                    revision_number=snap.revision_number,
                    technical_conclusion=snap.technical_conclusion,
                    next_requalification_date=snap.next_requalification_date,
                    pdf_sha256=str(qr["pdf_sha256"]),
                    at=qr["at"],
                )

        all_eq = sorted(
            set(runs_by_eq)
            | set(latest_round_by_eq)
            | set(latest_proto_by_eq)
            | set(latest_exec_by_eq)
            | set(latest_qual_by_eq)
        )
        return [
            EquipmentSummary(
                equipment=eq,
                run_count=len(runs_by_eq.get(eq, ())),
                latest_run=runs_by_eq[eq][0] if runs_by_eq.get(eq) else None,
                latest_round=latest_round_by_eq.get(eq),
                latest_protocol=latest_proto_by_eq.get(eq),
                latest_execution=latest_exec_by_eq.get(eq),
                latest_qualification_report=latest_qual_by_eq.get(eq),
            )
            for eq in all_eq
        ]

    return router
