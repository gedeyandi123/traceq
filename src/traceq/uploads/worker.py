"""The one worker that takes uploads from the database queue.

Serialised: a Postgres session lock is held while a job runs, so two workers (also in two
processes) never run at once and a heavy draft read never overlaps another. A job runs in
order of upload; its run is imported as Proposals and opens its Review Round in the same
transaction that marks it ``succeeded``, so a job is never done without its round. A failed
job keeps its message and releases its reservation; a live job that failed is charged its
whole reservation, since what it spent before failing is not known.
"""

from __future__ import annotations

import logging
import threading
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, text

from traceq.ai import BudgetExceeded, MissingRecording
from traceq.db import transaction
from traceq.documents import OcrUnavailable
from traceq.proposals.api import read_run_files
from traceq.proposals.store import import_run
from traceq.rounds import register_import
from traceq.runs.api import find_run
from traceq.uploads import store
from traceq.uploads.runner import Runner

log = logging.getLogger("traceq.uploads")
FAILURE_MESSAGES: dict[type[Exception], str] = {
    MissingRecording: (
        "a page of this draft is not recorded (no model recording for this revision) and"
        " reading it live is off; the server log has the detail"
    ),
    BudgetExceeded: "reading this draft live would pass the live budget; the run stopped",
    OcrUnavailable: "a page of this draft needs OCR, which this server does not have",
    FileNotFoundError: "a file the run needs is missing; the server log has the detail",
    ValueError: "the run could not read this draft; the server log has the detail",
}
"""What the page shows of a failure, one fixed text per kind: the error's own text may hold a
server path or a validation dump, so it goes to the log only (audit S5)."""


def _message(e: Exception) -> str:
    """What the page shows of a failure: the fixed text of its kind, else only the kind's name
    (the rest goes to the log)."""
    for kind, words in FAILURE_MESSAGES.items():
        if isinstance(e, kind):
            return words
    return f"the run failed ({type(e).__name__}); the server log has the detail"


class Worker:
    def __init__(self, db: Engine, runner: Runner, blobs: Path, runs: Path) -> None:
        self._db = db
        self._runner = runner
        self._blobs = blobs
        self._runs = runs

    def run_once(self) -> store.Job | None:
        """Takes the oldest queued job and runs it to its end; ``None`` when the queue is
        empty or another worker holds the lock."""
        with self._db.connect() as lock:
            held = lock.execute(
                text("SELECT pg_try_advisory_lock(:a, :b)"),
                {"a": store.WORKER_LOCK[0], "b": store.WORKER_LOCK[1]},
            ).scalar_one()
            lock.commit()
            if not held:
                return None
            try:
                return self._take()
            finally:
                lock.execute(
                    text("SELECT pg_advisory_unlock(:a, :b)"),
                    {"a": store.WORKER_LOCK[0], "b": store.WORKER_LOCK[1]},
                )
                lock.commit()

    def _take(self) -> store.Job | None:
        with transaction(self._db) as session:
            # No other worker runs (we hold the lock): a running job was left by a dead one.
            store.interrupted(session)
            job = store.claim_next(session)
        if job is None:
            return None
        try:
            result = self._runner(job, store.blob_path(self._blobs, job.sha256))
        except Exception as e:  # a failed run must not stop the worker
            log.exception("upload job %s failed", job.id)
            self._finish(job, run_id=None, cost=job.reserved_usd, message=_message(e))
            return self._reload(job.id)
        try:
            self._finish(
                job,
                run_id=result.run_id,
                cost=store.usd(result.live_cost_usd),
                message=None,
            )
        except Exception as e:
            log.exception("upload job %s could not be imported", job.id)
            self._finish(
                job,
                run_id=None,
                cost=store.usd(result.live_cost_usd),
                message=_message(e),
            )
        return self._reload(job.id)

    def _reload(self, job_id: int) -> store.Job | None:
        with transaction(self._db) as session:
            return store.get(session, job_id)

    def _finish(
        self, job: store.Job, *, run_id: str | None, cost: Decimal, message: str | None
    ) -> None:
        with transaction(self._db) as session:
            if run_id is not None:
                folder = find_run(self._runs, run_id)
                if folder is None:
                    raise FileNotFoundError(f"the run {run_id} is not in the runs folder")
                files = read_run_files(folder)
                imported = import_run(session, job.actor, files)
                if not imported.already_imported:
                    register_import(session, job.actor, imported, files)
            store.finish(session, job, run_id=run_id, cost=cost, message=message)

    def loop(self, stop: threading.Event, interval: float = 1.0) -> None:
        """Runs jobs until ``stop`` is set, resting ``interval`` seconds when there is none."""
        while not stop.is_set():
            try:
                if self.run_once() is not None:
                    continue
            except Exception:  # the database may be briefly away; the loop goes on
                log.exception("the upload worker could not reach its queue")
            stop.wait(interval)
