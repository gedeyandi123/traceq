"""The upload queue and its live-spend ledger, in Postgres (migration 0021).

``accept`` is the one place a job is created. In one transaction it takes the lock of the
Equipment, reserves the budget with a single conditional UPDATE (so concurrent uploads can
never reserve past the ceiling: Postgres re-checks the condition on the row the first
committed), queues the job under the revision number the caller read under that lock
(``next_rev``: after every upload and every registered draft revision of the Equipment, so two
uploads never share one) and adds the job and its Audit Trail entry. Nothing is dispatched
before the reservation holds.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

from traceq import audit

_LOCK_NS = 0x7551  # the advisory-lock namespace of upload revision numbers
WORKER_LOCK = (0x7551, 1)
"""The session lock one worker holds while it processes a job: workers are serialised."""
_SHA = re.compile(r"^[0-9a-f]{64}$")
STATUSES = ("queued", "running", "succeeded", "failed")


class BudgetRefused(Exception):
    """The live budget does not cover what the upload may cost."""


@dataclass(frozen=True)
class Job:
    id: int
    at: datetime
    equipment: str
    rev: int
    sha256: str
    size_bytes: int
    pages: int
    status: str
    reserved_usd: Decimal
    cost_usd: Decimal | None
    run_id: str | None
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    actor: audit.Actor


_COLUMNS = (
    "id, at, equipment, rev, sha256, size_bytes, pages, status, reserved_usd, cost_usd, run_id,"
    " message, started_at, finished_at, subject, issuer, name"
)


def _job(m: RowMapping) -> Job:
    return Job(
        id=int(m["id"]),
        at=m["at"],
        equipment=str(m["equipment"]),
        rev=int(m["rev"]),
        sha256=str(m["sha256"]),
        size_bytes=int(m["size_bytes"]),
        pages=int(m["pages"]),
        status=str(m["status"]),
        reserved_usd=Decimal(m["reserved_usd"]),
        cost_usd=None if m["cost_usd"] is None else Decimal(m["cost_usd"]),
        run_id=m["run_id"],
        message=m["message"],
        started_at=m["started_at"],
        finished_at=m["finished_at"],
        actor=audit.actor_of_row(m),
    )


def usd(value: float | Decimal) -> Decimal:
    """A money amount as the ledger stores it: six decimals."""
    return Decimal(str(value)).quantize(Decimal("0.000001"))


# --- Files ------------------------------------------------------------------------------


def blob_path(directory: Path, sha256: str) -> Path:
    """Where the bytes with this hash are kept: named by the hash alone."""
    if not _SHA.match(sha256):
        raise ValueError("not a SHA-256")
    return directory / f"{sha256}.pdf"


def save_blob(directory: Path, sha256: str, data: bytes) -> Path:
    """Stores ``data`` under its hash, atomically; the same bytes again change nothing."""
    path = blob_path(directory, sha256)
    if path.is_file():
        return path
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


# --- Queue ------------------------------------------------------------------------------


class DuplicateUpload(Exception):
    """These bytes were already uploaded for the Equipment."""


def lock_equipment(session: Session, equipment: str) -> None:
    """Takes the Equipment's upload lock until the transaction ends: the revision number a
    caller reads next is then the one ``accept`` assigns."""
    session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, hashtext(:equipment))"),
        {"ns": _LOCK_NS, "equipment": equipment},
    )


def already_uploaded(session: Session, equipment: str, sha256: str) -> bool:
    """Whether a queued, running or finished upload of the Equipment holds these bytes. A
    failed one does not count: its message tells the uploader to upload it again."""
    return (
        session.execute(
            text(
                "SELECT 1 FROM upload_jobs WHERE equipment = :equipment AND sha256 = :sha"
                " AND status <> 'failed' LIMIT 1"
            ),
            {"equipment": equipment, "sha": sha256},
        ).first()
        is not None
    )


def next_rev(session: Session, equipment: str, registered: int | None) -> int:
    """The revision the next upload of the Equipment gets: after every upload so far and
    after ``registered``, the highest revision of the draft that imported runs registered
    (the review rounds' ``document_versions``), whichever way it arrived."""
    queued = session.execute(
        text("SELECT MAX(rev) FROM upload_jobs WHERE equipment = :equipment"),
        {"equipment": equipment},
    ).scalar_one()
    known = [r for r in (queued, registered) if r is not None]
    return max(known) + 1 if known else 0


def accept(
    session: Session,
    actor: audit.Actor,
    *,
    equipment: str,
    rev: int,
    sha256: str,
    size_bytes: int,
    pages: int,
    estimate: Decimal,
    ceiling: Decimal,
) -> Job:
    """Reserves ``estimate`` of the ``ceiling`` and queues the job as revision ``rev`` (from
    ``next_rev``, read under ``lock_equipment``), in the caller's transaction.
    ``BudgetRefused`` when ``reserved + spent + estimate`` would pass the ceiling: the
    transaction then holds nothing."""
    lock_equipment(session, equipment)
    reserved = session.execute(
        text(
            "UPDATE upload_budget SET reserved_usd = reserved_usd + :e"
            " WHERE id = 1 AND reserved_usd + spent_usd + :e <= :ceiling RETURNING reserved_usd"
        ),
        {"e": estimate, "ceiling": ceiling},
    ).first()
    if reserved is None:
        raise BudgetRefused(
            f"the live budget of USD {ceiling} does not cover this upload (USD {estimate})"
        )
    m = (
        session.execute(
            text(
                "INSERT INTO upload_jobs (equipment, rev, sha256, size_bytes, pages,"
                " reserved_usd, subject, issuer, name)"
                " VALUES (:equipment, :rev, :sha, :size, :pages, :e, :subject, :issuer, :name)"
                f" RETURNING {_COLUMNS}"
            ),
            {
                "equipment": equipment,
                "rev": rev,
                "sha": sha256,
                "size": size_bytes,
                "pages": pages,
                "e": estimate,
                "subject": actor.subject,
                "issuer": actor.issuer,
                "name": actor.name,
            },
        )
        .mappings()
        .one()
    )
    job = _job(m)
    audit.append(
        session,
        actor,
        "draft uploaded",
        "upload_job",
        str(job.id),
        new={
            "equipment": equipment,
            "rev": job.rev,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "pages": pages,
            "reserved_usd": str(estimate),
        },
    )
    return job


def claim_next(session: Session) -> Job | None:
    """The oldest queued job, now running; ``None`` when the queue is empty."""
    m = (
        session.execute(
            text(
                "UPDATE upload_jobs SET status = 'running', started_at = clock_timestamp()"
                " WHERE id = (SELECT id FROM upload_jobs WHERE status = 'queued'"
                " ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED)"
                f" RETURNING {_COLUMNS}"
            )
        )
        .mappings()
        .first()
    )
    return None if m is None else _job(m)


def finish(
    session: Session,
    job: Job,
    *,
    run_id: str | None,
    cost: Decimal,
    message: str | None,
) -> None:
    """A running job ends: ``succeeded`` when it produced ``run_id``, else ``failed``. Its
    reservation is released and what it spent is added to the ledger, in one transaction."""
    status = "succeeded" if run_id is not None else "failed"
    done = session.execute(
        text(
            "UPDATE upload_jobs SET status = :status, run_id = :run_id, cost_usd = :cost,"
            " message = :message, finished_at = clock_timestamp()"
            " WHERE id = :id AND status = 'running' RETURNING id"
        ),
        {
            "status": status,
            "run_id": run_id,
            "cost": cost,
            "message": message,
            "id": job.id,
        },
    ).first()
    if done is None:
        raise RuntimeError(f"upload job {job.id} is not running")
    session.execute(
        text(
            "UPDATE upload_budget SET reserved_usd = reserved_usd - :reserved,"
            " spent_usd = spent_usd + :cost WHERE id = 1"
        ),
        {"reserved": job.reserved_usd, "cost": cost},
    )


def interrupted(session: Session) -> list[Job]:
    """Jobs still ``running`` while no worker holds the lock: a worker died. Each fails and
    releases its reservation, so the queue does not stay stuck; it is charged the whole
    reservation (as a failed live job is), since live calls may already have been billed."""
    rows = (
        session.execute(
            text(f"SELECT {_COLUMNS} FROM upload_jobs WHERE status = 'running' ORDER BY id")
        )
        .mappings()
        .all()
    )
    jobs = [_job(m) for m in rows]
    for job in jobs:
        finish(
            session,
            job,
            run_id=None,
            cost=job.reserved_usd,
            message="the worker stopped before this upload finished; upload it again",
        )
    return jobs


def get(session: Session, job_id: int) -> Job | None:
    m = (
        session.execute(text(f"SELECT {_COLUMNS} FROM upload_jobs WHERE id = :id"), {"id": job_id})
        .mappings()
        .first()
    )
    return None if m is None else _job(m)


def for_equipment(session: Session, equipment: str) -> list[Job]:
    """The Equipment's uploads, newest revision first."""
    rows = (
        session.execute(
            text(
                f"SELECT {_COLUMNS} FROM upload_jobs WHERE equipment = :equipment ORDER BY rev DESC"
            ),
            {"equipment": equipment},
        )
        .mappings()
        .all()
    )
    return [_job(m) for m in rows]


def budget(session: Session) -> tuple[Decimal, Decimal]:
    """``(reserved, spent)`` of the ledger."""
    m = (
        session.execute(text("SELECT reserved_usd, spent_usd FROM upload_budget WHERE id = 1"))
        .mappings()
        .one()
    )
    return Decimal(m["reserved_usd"]), Decimal(m["spent_usd"])
