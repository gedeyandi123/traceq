"""Browser upload of a Protocol Draft and the background worker, over HTTP with a real Postgres
and the demo issuer (spec #375, ticket S5; spec #342).

The runner is a stand-in that writes the fixture run of ``tests/test_proposals_api.py`` for
each job: what is under test is the queue, the checks, the budget, the revision numbers and
what the worker does with a run, not the pipeline (``tests/test_run.py``). Nothing here sends
an LLM call.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_proposals_api import add_run, bearer, token
from test_upload_checks import pdf

from traceq import audit
from traceq import db as traceq_db
from traceq.ai import MissingRecording, Recorder
from traceq.app.api import create_app
from traceq.audit import Actor
from traceq.db import engine, locks, transaction
from traceq.documents import VERSIONS, CorpusDocument, Page
from traceq.documents.cache import IngestCache, Ingested
from traceq.identity import IdentitySettings
from traceq.review.draft import DRAFT_STAGE_VERSION, draft_edition, draft_requests
from traceq.uploads import RunResult, UploadSettings, Worker, store
from traceq.uploads.checks import sha256_of
from traceq.uploads.runner import draft_doc_id, has_draft_recording, package_runner
from traceq.uploads.store import Job
from traceq.uploads.worker import FAILURE_MESSAGES

PDF = {"content-type": "application/pdf"}
RECORDINGS = Path(__file__).resolve().parents[1] / "recordings"


class Fake:
    """The runner: one fixture run per job, or the error a test asks for."""

    def __init__(self, runs: Path) -> None:
        self.runs = runs
        self.seen: list[Job] = []
        self.error: Exception | None = None
        self.live_cost = 0.0

    def __call__(self, job: Job, path: Path) -> RunResult:
        self.seen.append(job)
        assert path.read_bytes() and sha256_of(path.read_bytes()) == job.sha256
        if self.error is not None:
            raise self.error
        run_id = f"20261127T09{job.id:02d}00Z-up{job.id:04d}"
        add_run(self.runs, run_id)
        return RunResult(run_id, self.live_cost)


def _never_called() -> Any:
    raise AssertionError("the runner of these tests never reads live")


def record_draft(settings: UploadSettings, data: bytes, pages: int, rev: int) -> None:
    """What a live read of ``data`` uploaded as revision ``rev`` leaves behind: its ingest and
    one recording per page, named by the key the run looks up (the draft stage recorder)."""
    sha = sha256_of(data)
    texts = [Page(n, f"page {n} text") for n in range(1, pages + 1)]
    IngestCache(settings.package_recordings / "ingest").put(
        Ingested(sha, VERSIONS["born_digital"], "test", tuple(texts), (0.0,) * pages, 0.0, None)
    )
    recorder = Recorder(settings.package_recordings, settings.model, DRAFT_STAGE_VERSION)
    doc = CorpusDocument(
        draft_doc_id(settings.equipment), rev, "oq_protocol", "born_digital", "id", Path(), sha
    )
    settings.package_recordings.mkdir(parents=True, exist_ok=True)
    for request in draft_requests(doc, texts, draft_edition(settings.package_version)):
        (settings.package_recordings / f"{recorder.key(request)}.json").write_text("{}")


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    return path


@pytest.fixture
def settings(tmp_path: Path) -> UploadSettings:
    return UploadSettings(
        equipment="TP-201",
        store=tmp_path / "uploads",
        corpus=tmp_path / "corpus",
        recordings=tmp_path / "recordings",
        package_recordings=tmp_path / "package-recordings",
        model="m",
        budget_usd=0.05,
        max_bytes=50_000,
        max_pages=3,
        estimate_per_page_usd=0.01,
        live=_never_called,
    )


@pytest.fixture
def client(
    runs: Path, settings: UploadSettings, demo_issuer: DemoIssuer, fresh_database: Databases
) -> TestClient:
    identity = IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience)
    return TestClient(
        create_app(runs, identity=identity, database=fresh_database.app, uploads=settings)
    )


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def worker(fresh_database: Databases, runs: Path, settings: UploadSettings) -> Worker:
    return Worker(engine(fresh_database.app), Fake(runs), settings.blobs, runs)


def upload(
    client: TestClient, headers: dict[str, str], data: bytes, equipment: str = "TP-201"
) -> Any:
    return client.post(f"/equipment/{equipment}/drafts", content=data, headers={**headers, **PDF})


def ledger(dbs: Databases) -> tuple[Decimal, Decimal]:
    with transaction(engine(dbs.app)) as session:
        return store.budget(session)


# --- The flow ---------------------------------------------------------------------------


def test_an_upload_is_queued_run_by_the_worker_and_opens_its_review_round(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    fresh_database: Databases,
    settings: UploadSettings,
) -> None:
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    first, second = pdf(1, "rev 0"), pdf(2, "rev 1")

    r = upload(client, decider, first)
    assert r.status_code == 202, r.text
    job = r.json()
    assert (job["rev"], job["status"], job["pages"]) == (0, "queued", 1)
    assert job["sha256"] == sha256_of(first)
    assert (settings.blobs / f"{job['sha256']}.pdf").read_bytes() == first
    assert list(settings.blobs.iterdir()) == [settings.blobs / f"{job['sha256']}.pdf"]

    done = worker.run_once()
    assert done is not None and done.status == "succeeded"
    polled = client.get(f"/uploads/{job['id']}", headers=decider).json()
    assert polled["status"] == "succeeded" and polled["run_id"] == done.run_id
    rounds = client.get(f"/runs/{done.run_id}/rounds", headers=decider).json()
    assert [x["round_number"] for x in rounds["rounds"]] == [1]

    assert upload(client, decider, second).json()["rev"] == 1
    again = worker.run_once()
    assert again is not None and again.run_id != done.run_id
    rounds = client.get(f"/runs/{again.run_id}/rounds", headers=decider).json()
    assert [x["round_number"] for x in rounds["rounds"]] == [1, 2]
    assert rounds["diff"] is not None

    assert worker.run_once() is None  # the queue is empty
    listed = client.get("/equipment/TP-201/drafts", headers=decider).json()
    assert [j["rev"] for j in listed["jobs"]] == [1, 0]
    assert (listed["max_bytes"], listed["max_pages"]) == (50_000, 3)
    assert "synthetic" in listed["cloud_notice"] and "external" in listed["cloud_notice"]
    assert [j.rev for j in fake.seen] == [0, 1]


def test_a_run_the_worker_imports_names_its_uploader_as_the_registrant(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    """The worker imports as the uploader, so every document version its run registers first
    names the uploader (migration 0024, ADR 0012 amended 28 November 2026)."""
    assert upload(client, decider, pdf(1, "registrant")).status_code == 202
    done = worker.run_once()
    assert done is not None and done.status == "succeeded"
    with transaction(engine(fresh_database.app)) as session:
        uploader = session.execute(
            text("SELECT subject, issuer, name FROM upload_jobs WHERE id = :id"), {"id": done.id}
        ).one()
        registrants = session.execute(
            text(
                "SELECT subject, issuer, name FROM document_versions WHERE first_seen_run_id = :run"
            ),
            {"run": done.run_id},
        ).all()
    assert registrants and {tuple(r) for r in registrants} == {tuple(uploader)}


def test_bytes_uploaded_before_for_the_equipment_are_refused_and_queue_nothing(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    data = pdf(2, "same")
    assert upload(client, decider, data).status_code == 202
    again = upload(client, decider, data)
    assert again.status_code == 409 and "already uploaded" in again.json()["detail"]
    assert worker.run_once() is not None  # finished, and still refused
    assert upload(client, decider, data).status_code == 409
    listed = client.get("/equipment/TP-201/drafts", headers=decider).json()
    assert [j["rev"] for j in listed["jobs"]] == [0]
    assert ledger(fresh_database) == (Decimal(0), Decimal(0))


def test_bytes_whose_upload_failed_may_be_uploaded_again(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
) -> None:
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    fake.error = MissingRecording("gone")
    data = pdf(1, "retry")
    assert upload(client, decider, data).status_code == 202
    assert worker.run_once() is not None
    again = upload(client, decider, data)
    # The failed revision was the highest: it is given again (audit C1).
    assert (again.status_code, again.json()["rev"]) == (202, 0)
    listed = client.get("/equipment/TP-201/drafts", headers=decider).json()["jobs"]
    assert [(j["rev"], j["status"]) for j in listed] == [(0, "queued"), (0, "failed")]


def test_a_failed_revision_recorded_for_replay_can_be_uploaded_again_in_replay(
    decider: dict[str, str],
    settings: UploadSettings,
    runs: Path,
    fresh_database: Databases,
    demo_issuer: DemoIssuer,
) -> None:
    """The recordings exist only for the revision the bytes were given: replay could never
    retry a failed upload if the retry got the next number (audit C1)."""
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    data = pdf(2, "recorded, fails once")
    record_draft(settings, data, pages=2, rev=0)
    c = replay_only_client(runs, settings, fresh_database, demo_issuer)
    assert upload(c, decider, data).status_code == 202
    fake.error = OSError("the disk was full")
    assert worker.run_once() is not None
    again = upload(c, decider, data)
    assert (again.status_code, again.json()["rev"]) == (202, 0), again.text
    fake.error = None
    done = worker.run_once()
    assert done is not None and (done.rev, done.status) == (0, "succeeded")


def test_a_failed_revision_below_a_live_one_is_not_given_again(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
) -> None:
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    assert upload(client, decider, pdf(1, "a")).json()["rev"] == 0
    assert upload(client, decider, pdf(1, "b")).json()["rev"] == 1
    fake.error = MissingRecording("gone")
    assert worker.run_once() is not None  # rev 0 fails; rev 1 is still queued
    assert upload(client, decider, pdf(1, "c")).json()["rev"] == 2
    fake.error = None
    assert worker.run_once() is not None  # rev 1 succeeds
    fake.error = MissingRecording("gone")
    assert worker.run_once() is not None  # rev 2 fails: the highest, given again
    assert upload(client, decider, pdf(1, "d")).json()["rev"] == 2


def test_two_live_jobs_never_share_a_revision_but_a_failed_one_may(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    upload(client, decider, pdf(1, "first"))

    def queue(sha: str) -> None:
        with transaction(engine(fresh_database.app)) as session:
            store.accept(
                session,
                Actor(subject="s", issuer="i", name="Ayu"),
                equipment="TP-201",
                rev=0,
                sha256=sha * 64,
                size_bytes=1,
                pages=1,
                estimate=Decimal(0),
                ceiling=Decimal(1),
            )

    with pytest.raises(Exception, match="upload_jobs_live_rev"):
        queue("a")
    with transaction(engine(fresh_database.app)) as session:
        session.execute(
            text(
                "UPDATE upload_jobs SET status = 'running' WHERE status = 'queued';"
                " UPDATE upload_jobs SET status = 'failed', cost_usd = 0,"
                " finished_at = clock_timestamp() WHERE status = 'running'"
            )
        )
    queue("a")
    with pytest.raises(Exception, match="upload_jobs_live_rev"):
        queue("b")


def test_the_revision_continues_after_the_draft_revisions_the_rounds_registered(
    client: TestClient, decider: dict[str, str], fresh_database: Databases
) -> None:
    with transaction(engine(fresh_database.app)) as session:
        session.execute(
            text(
                "INSERT INTO imported_runs (run_id, equipment, created, model, mode,"
                " pipeline_version, prompts, documents) VALUES ('r', 'TP-201', now(), 'm',"
                " 'replay', 'p', '{}', '[]')"
            )
        )
        for rev in (0, 1, 4):
            session.execute(
                text(
                    "INSERT INTO document_versions (equipment, doc_id, rev, doc_type, source,"
                    " sha256, first_seen_run_id) VALUES ('TP-201', :doc, :rev, 'protocol_draft',"
                    " 'review_package_draft', :sha, 'r')"
                ),
                {"doc": draft_doc_id("TP-201"), "rev": rev, "sha": f"{rev:064x}"},
            )
    assert upload(client, decider, pdf(1, "after the registered")).json()["rev"] == 5
    assert upload(client, decider, pdf(1, "and one more")).json()["rev"] == 6


def replay_only_client(
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
    demo_issuer: DemoIssuer,
) -> TestClient:
    identity = IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience)
    replay_only = replace(settings, budget_usd=0.0, live=None)
    return TestClient(
        create_app(runs, identity=identity, database=fresh_database.app, uploads=replay_only)
    )


def test_bytes_recorded_as_the_revision_they_get_reserve_nothing_even_with_no_budget(
    decider: dict[str, str],
    settings: UploadSettings,
    runs: Path,
    fresh_database: Databases,
    demo_issuer: DemoIssuer,
) -> None:
    data = pdf(2, "recorded")
    record_draft(settings, data, pages=2, rev=0)
    c = replay_only_client(runs, settings, fresh_database, demo_issuer)
    assert upload(c, decider, data).json()["reserved_usd"] == 0
    other = upload(c, decider, pdf(2, "never read"))
    assert other.status_code == 402 and "no model recording" in other.json()["detail"]


def test_bytes_recorded_as_another_revision_are_refused_up_front_in_replay(
    client: TestClient,
    decider: dict[str, str],
    settings: UploadSettings,
    runs: Path,
    fresh_database: Databases,
    demo_issuer: DemoIssuer,
) -> None:
    """The prompt names the revision, so a recording of rev 1 does not serve an upload that
    becomes rev 0: its replay would fail (``MissingRecording``) after a 202."""
    data = pdf(2, "recorded as rev 1")
    record_draft(settings, data, pages=2, rev=1)
    c = replay_only_client(runs, settings, fresh_database, demo_issuer)
    refused = upload(c, decider, data)
    assert refused.status_code == 402 and "revision 0" in refused.json()["detail"]
    assert client.get("/equipment/TP-201/drafts", headers=decider).json()["jobs"] == []
    # With a live budget it is read live, and reserves its estimate.
    assert upload(client, decider, data).json()["reserved_usd"] == 0.02


def test_an_ingest_file_without_a_model_recording_reserves_like_a_live_run(
    client: TestClient,
    decider: dict[str, str],
    settings: UploadSettings,
    runs: Path,
    fresh_database: Databases,
    demo_issuer: DemoIssuer,
) -> None:
    data = pdf(2, "parsed only")
    record_draft(settings, data, pages=2, rev=0)
    for f in settings.package_recordings.glob("*.json"):
        f.unlink()  # the ingest stays, the model recordings go
    c = replay_only_client(runs, settings, fresh_database, demo_issuer)
    assert upload(c, decider, data).status_code == 402
    assert upload(client, decider, data).json()["reserved_usd"] == 0.02


def test_the_upload_worker_thread_does_not_block_process_exit(
    runs: Path, settings: UploadSettings, demo_issuer: DemoIssuer, fresh_database: Databases
) -> None:
    identity = IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience)
    app = create_app(
        runs, identity=identity, database=fresh_database.app, uploads=settings, run_worker=True
    )
    with TestClient(app):
        threads = [t for t in threading.enumerate() if t.name == "upload-worker"]
        assert len(threads) == 1 and threads[0].daemon


# --- Who and what ----------------------------------------------------------------------


def test_upload_and_polling_need_the_deciding_role_and_the_equipment_in_scope(
    client: TestClient, decider: dict[str, str], demo_issuer: DemoIssuer
) -> None:
    other = bearer(token(demo_issuer, decider=False))
    data = pdf(1)
    assert client.post("/equipment/TP-201/drafts", content=data, headers=PDF).status_code == 401
    assert upload(client, other, data).status_code == 403
    assert upload(client, decider, data, "TP-999").status_code == 403
    assert client.get("/equipment/TP-999/drafts", headers=decider).status_code == 403
    job = upload(client, decider, data).json()
    assert client.get(f"/uploads/{job['id']}", headers=other).status_code == 403
    assert client.get("/equipment/TP-201/drafts", headers=other).status_code == 403
    assert client.get("/uploads/999999", headers=decider).status_code == 404
    assert client.get(f"/uploads/{job['id']}").status_code == 401


def test_uploads_answer_404_when_they_are_not_configured(
    runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases, decider: dict[str, str]
) -> None:
    identity = IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience)
    c = TestClient(create_app(runs, identity=identity, database=fresh_database.app))
    assert upload(c, decider, pdf(1)).status_code == 404


@pytest.mark.parametrize(
    ("make", "status"),
    [
        (lambda: b"", 422),
        (lambda: b"<html>not a pdf</html>", 422),
        (lambda: b"%PDF-1.7\n" + b"x" * 100, 422),
        (lambda: pdf(4), 422),  # over the page cap of 3
        (lambda: pdf(1) + b"\x00" * 60_000, 413),  # over the size cap
    ],
)
def test_a_file_that_is_not_a_pdf_or_passes_a_cap_is_refused_and_queues_nothing(
    client: TestClient,
    decider: dict[str, str],
    fresh_database: Databases,
    make: Callable[[], bytes],
    status: int,
) -> None:
    r = upload(client, decider, make())
    assert r.status_code == status, r.text
    assert client.get("/equipment/TP-201/drafts", headers=decider).json()["jobs"] == []
    assert ledger(fresh_database) == (Decimal(0), Decimal(0))


def test_a_body_that_is_not_sent_as_a_pdf_is_refused(
    client: TestClient, decider: dict[str, str]
) -> None:
    r = client.post("/equipment/TP-201/drafts", content=pdf(1), headers=decider)
    assert r.status_code == 415
    form = {"file": ("draft.pdf", pdf(1), "application/pdf")}
    assert client.post("/equipment/TP-201/drafts", files=form, headers=decider).status_code == 415


def test_a_chunked_body_over_the_cap_is_refused_without_a_length(
    client: TestClient, decider: dict[str, str]
) -> None:
    def body() -> Any:
        for _ in range(20):
            yield b"%PDF-" + b"x" * 5_000

    r = client.post("/equipment/TP-201/drafts", content=body(), headers={**decider, **PDF})
    assert r.status_code == 413


# --- Budget and revision numbers --------------------------------------------------------


def test_concurrent_uploads_never_reserve_past_the_budget(
    client: TestClient, decider: dict[str, str], fresh_database: Databases
) -> None:
    # Ceiling 0.05 and 0.01 a page: five one-page uploads fit, whatever the interleaving.
    files = [pdf(1, f"upload {i}") for i in range(14)]
    with ThreadPoolExecutor(max_workers=14) as pool:
        results = list(pool.map(lambda d: upload(client, decider, d), files))
    codes = sorted(r.status_code for r in results)
    assert codes == [202] * 5 + [402] * 9
    reserved, spent = ledger(fresh_database)
    assert (reserved, spent) == (Decimal("0.05"), Decimal(0))
    revs = sorted(r.json()["rev"] for r in results if r.status_code == 202)
    assert revs == [0, 1, 2, 3, 4]
    with transaction(engine(fresh_database.app)) as session:
        held = session.execute(text("SELECT sum(reserved_usd) FROM upload_jobs")).scalar_one()
    assert held == reserved


def test_concurrent_uploads_get_distinct_consecutive_revision_numbers(
    client: TestClient, decider: dict[str, str]
) -> None:
    data = pdf(1, "same bytes")
    assert upload(client, decider, data).status_code == 202
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: upload(client, decider, pdf(1, f"r{i}")), range(4)))
    revs = sorted(r.json()["rev"] for r in results if r.status_code == 202)
    assert revs == list(range(1, 1 + len(revs)))


def test_a_failed_job_releases_its_reservation_and_charges_a_live_one_in_full(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
) -> None:
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    fake.error = MissingRecording("no recording for page 1 of the draft")
    upload(client, decider, pdf(2, "will fail"))
    assert ledger(fresh_database) == (Decimal("0.02"), Decimal(0))
    done = worker.run_once()
    assert done is not None and done.status == "failed"
    assert done.message == FAILURE_MESSAGES[MissingRecording]
    assert ledger(fresh_database) == (Decimal(0), Decimal("0.02"))
    assert done.run_id is None


def test_a_failure_the_worker_did_not_expect_shows_only_its_kind(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
) -> None:
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    fake.error = RuntimeError("C:/secret/path/token=abc")
    job = upload(client, decider, pdf(1, "boom")).json()
    assert worker.run_once() is not None
    polled = client.get(f"/uploads/{job['id']}", headers=decider).json()
    assert polled["status"] == "failed"
    assert "secret" not in polled["message"] and "RuntimeError" in polled["message"]
    # The worker goes on to the next job.
    fake.error = None
    upload(client, decider, pdf(1, "after"))
    after = worker.run_once()
    assert after is not None and after.status == "succeeded"


def test_the_worker_records_the_cost_of_a_live_run_and_frees_the_rest(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
) -> None:
    fake = Fake(runs)
    fake.live_cost = 0.0018
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    upload(client, decider, pdf(2, "live"))
    done = worker.run_once()
    assert done is not None and done.cost_usd == Decimal("0.001800")
    assert ledger(fresh_database) == (Decimal(0), Decimal("0.0018"))
    listed = client.get("/equipment/TP-201/drafts", headers=decider).json()
    assert listed["live_remaining_usd"] == pytest.approx(0.05 - 0.0018)


# --- One serialised worker --------------------------------------------------------------


def test_only_one_worker_runs_at_a_time(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    upload(client, decider, pdf(1, "queued"))
    with engine(fresh_database.app).connect() as other:
        other.execute(
            text("SELECT pg_advisory_lock(:a, :b)"),
            {"a": store.WORKER_LOCK[0], "b": store.WORKER_LOCK[1]},
        )
        assert worker.run_once() is None  # another worker holds the lock: this one waits
        other.execute(
            text("SELECT pg_advisory_unlock(:a, :b)"),
            {"a": store.WORKER_LOCK[0], "b": store.WORKER_LOCK[1]},
        )
        other.commit()
    done = worker.run_once()
    assert done is not None and done.status == "succeeded"


def test_a_job_left_running_by_a_dead_worker_fails_and_is_charged_its_reservation(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    job = upload(client, decider, pdf(2, "orphan")).json()
    with transaction(engine(fresh_database.app)) as session:
        assert store.claim_next(session) is not None  # taken, never finished
    assert ledger(fresh_database) == (Decimal("0.02"), Decimal(0))
    upload(client, decider, pdf(1, "next"))
    done = worker.run_once()
    assert done is not None and done.rev == 1 and done.status == "succeeded"
    orphan = client.get(f"/uploads/{job['id']}", headers=decider).json()
    assert orphan["status"] == "failed" and "upload it again" in orphan["message"]
    assert orphan["cost_usd"] == 0.02  # live calls may have been billed: charged in full
    assert ledger(fresh_database) == (Decimal(0), Decimal("0.02"))


def test_a_job_never_moves_backward_or_changes_what_it_holds(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    job = upload(client, decider, pdf(1, "fixed")).json()
    assert worker.run_once() is not None
    with (
        pytest.raises(Exception, match="does not move"),
        transaction(engine(fresh_database.app)) as session,
    ):
        session.execute(
            text("UPDATE upload_jobs SET status = 'queued' WHERE id = :id"), {"id": job["id"]}
        )
    with (
        pytest.raises(Exception, match="does not change"),
        transaction(engine(fresh_database.app)) as session,
    ):
        session.execute(
            text("UPDATE upload_jobs SET sha256 = repeat('a', 64) WHERE id = :id"),
            {"id": job["id"]},
        )


# --- The real runner, replayed -----------------------------------------------------------


def test_the_real_runner_replays_the_recorded_revision_and_a_wrong_revision_is_foreseen(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    tmp_path: Path,
    fresh_database: Databases,
) -> None:
    """``write_package`` -> ``run`` (replay, the recordings of the 0.2.0 package) -> import,
    with no fake runner: the check ``has_draft_recording`` agrees with what the run finds."""
    package = json.loads(
        (RECORDINGS / "TP-201-OQ-draft-0.2.0" / "manifest.json").read_text("utf-8")
    )
    rev0 = next(d for d in package["documents"] if d["rev"] == 0)
    sha = rev0["sha256"]
    real = UploadSettings(
        equipment="TP-201",
        store=tmp_path / "uploads-real",
        corpus=RECORDINGS / "corpus-0.1.1",
        recordings=RECORDINGS / "haiku-r10",
        package_recordings=RECORDINGS / "haiku-oq-draft-r8",
        model="claude-haiku-5-5",
    )
    assert has_draft_recording(real, sha, 0)
    assert not has_draft_recording(real, sha, 1)  # the revision is in the prompt
    # The recorded ingest answers the run, so the bytes themselves are never read.
    store.save_blob(real.blobs, sha, b"%PDF-1.7 placeholder, the ingest is cached")
    worker = Worker(engine(fresh_database.app), package_runner(real, runs), real.blobs, runs)

    def queue(rev: int) -> None:
        with transaction(engine(fresh_database.app)) as session:
            store.accept(
                session,
                Actor(subject="s", issuer="i", name="Ayu"),
                equipment="TP-201",
                rev=rev,
                sha256=sha,
                size_bytes=int(rev0["bytes"]),
                pages=int(rev0["pages"]),
                estimate=Decimal(0),
                ceiling=Decimal(0),
            )

    queue(rev=0)
    done = worker.run_once()
    assert done is not None and done.status == "succeeded", done and done.message
    assert done.cost_usd == 0 and done.run_id is not None
    rounds = client.get(f"/runs/{done.run_id}/rounds", headers=decider).json()
    assert [x["round_number"] for x in rounds["rounds"]] == [1]

    queue(rev=1)  # what the old check let through as a 202
    failed = worker.run_once()
    assert failed is not None and failed.status == "failed"
    assert failed.message is not None and "not recorded" in failed.message


# --- Ledger integrity, validated settings, the worker in the Audit Trail (ticket #393) ----


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -0.01, 1e30, 1001.0])
def test_a_budget_that_is_not_a_sane_amount_is_refused_at_startup(
    settings: UploadSettings, bad: float
) -> None:
    with pytest.raises(ValueError, match="budget_usd"):
        replace(settings, budget_usd=bad)


@pytest.mark.parametrize("field", ["estimate_per_page_usd", "max_bytes", "max_pages"])
def test_the_other_limits_of_the_settings_are_validated_too(
    settings: UploadSettings, field: str
) -> None:
    for bad in (float("nan"), -1, 0):
        with pytest.raises(ValueError, match=field):
            replace(settings, **{field: bad})


def test_a_budget_of_zero_stays_valid(settings: UploadSettings) -> None:
    assert replace(settings, budget_usd=0.0, live=None).budget_usd == 0.0


def test_the_end_of_a_job_and_its_cost_are_in_the_audit_trail_by_the_worker(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
) -> None:
    fake = Fake(runs)
    fake.live_cost = 0.0018
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    ok = upload(client, decider, pdf(2, "ends well")).json()
    done = worker.run_once()
    assert done is not None and done.status == "succeeded"
    fake.error = MissingRecording("no recording for page 1 of the draft")
    bad = upload(client, decider, pdf(1, "ends badly")).json()
    failed = worker.run_once()
    assert failed is not None and failed.status == "failed"

    with transaction(engine(fresh_database.app)) as session:
        ended = [
            e
            for e in audit.entries(session)
            if e.record_type == "upload_job" and e.action.startswith("draft upload ")
        ]
    by_id = {e.record_id: e for e in ended}
    good, wrong = by_id[str(ok["id"])], by_id[str(bad["id"])]
    assert good.action == "draft upload succeeded" and wrong.action == "draft upload failed"
    for entry in (good, wrong):
        assert entry.actor == store.WORKER_ACTOR  # the worker, not the uploader
    assert isinstance(good.new_value, dict) and isinstance(wrong.new_value, dict)
    assert good.new_value["cost_usd"] == "0.001800" and good.new_value["run_id"] == done.run_id
    assert wrong.new_value["cost_usd"] == "0.010000"
    assert "recording" in str(wrong.new_value["message"])


def test_an_interrupted_job_is_in_the_audit_trail_as_the_worker(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    job = upload(client, decider, pdf(2, "orphan")).json()
    with transaction(engine(fresh_database.app)) as session:
        assert store.claim_next(session) is not None
    assert worker.run_once() is None  # no queued job left: only the interruption is recorded
    with transaction(engine(fresh_database.app)) as session:
        mine = [
            e
            for e in audit.entries(session)
            if e.record_type == "upload_job" and e.record_id == str(job["id"])
        ]
    assert [e.action for e in mine] == ["draft uploaded", "draft upload interrupted"]
    assert mine[1].actor == store.WORKER_ACTOR


def test_a_finished_job_keeps_its_run_cost_and_message(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    job = upload(client, decider, pdf(1, "final")).json()
    assert worker.run_once() is not None
    for column, value in (
        ("run_id", "'other'"),
        ("cost_usd", "5"),
        ("message", "'rewritten'"),
        ("finished_at", "now()"),
    ):
        with (
            pytest.raises(Exception, match="finished upload job"),
            transaction(engine(fresh_database.app)) as session,
        ):
            session.execute(
                text(f"UPDATE upload_jobs SET {column} = {value} WHERE id = :id"),
                {"id": job["id"]},
            )


def test_a_job_cannot_be_marked_finished_without_its_cost_and_time(
    client: TestClient, decider: dict[str, str], fresh_database: Databases
) -> None:
    job = upload(client, decider, pdf(1, "half")).json()
    with transaction(engine(fresh_database.app)) as session:
        assert store.claim_next(session) is not None
    with (
        pytest.raises(Exception, match="upload_jobs_finished_complete"),
        transaction(engine(fresh_database.app)) as session,
    ):
        session.execute(
            text("UPDATE upload_jobs SET status = 'failed' WHERE id = :id"), {"id": job["id"]}
        )


def test_the_spent_ledger_never_goes_down_and_its_id_is_not_updatable(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    upload(client, decider, pdf(1, "spend"))
    assert worker.run_once() is not None
    with (
        pytest.raises(Exception, match="spent"),
        transaction(engine(fresh_database.app)) as session,
    ):
        session.execute(text("UPDATE upload_budget SET spent_usd = spent_usd - 0.01 WHERE id = 1"))
    with (
        pytest.raises(Exception, match="permission denied"),
        transaction(engine(fresh_database.app)) as session,
    ):
        session.execute(text("UPDATE upload_budget SET id = 2 WHERE id = 1"))


def test_a_job_id_beyond_the_database_range_is_a_client_error_not_a_500(
    client: TestClient, decider: dict[str, str]
) -> None:
    assert client.get(f"/uploads/{2**63}", headers=decider).status_code == 422
    assert client.get(f"/uploads/{2**63 - 1}", headers=decider).status_code == 404


def test_the_list_of_uploads_is_limited_to_the_newest(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    for n in range(3):
        upload(client, decider, pdf(1, f"v{n}"))
        assert worker.run_once() is not None
    with transaction(engine(fresh_database.app)) as session:
        assert [j.rev for j in store.for_equipment(session, "TP-201", limit=2)] == [2, 1]


def test_migration_0022_goes_down_and_up_again_with_its_guards_restored(
    fresh_database: Databases,
) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(traceq_db.__file__).parent / "migrations"))
    cfg.attributes["url"] = fresh_database.owner
    command.downgrade(cfg, "0021")
    with transaction(engine(fresh_database.owner)) as session:
        triggers = session.execute(
            text("SELECT tgname FROM pg_trigger WHERE tgname LIKE 'upload_%'")
        ).scalars()
        assert "upload_budget_spent_only_up" not in set(triggers)
    command.upgrade(cfg, "head")
    with transaction(engine(fresh_database.owner)) as session:
        names = set(
            session.execute(
                text("SELECT tgname FROM pg_trigger WHERE tgname LIKE 'upload_%'")
            ).scalars()
        )
        assert {"upload_budget_spent_only_up", "upload_jobs_finished_immutable"} <= names


# --- Audit fixes of 28 November (spec #375, ticket #393) ----------------------------------


@pytest.mark.parametrize(
    "error",
    [
        MissingRecording("C:/srv/recordings/abc.json is not recorded"),
        FileNotFoundError("C:/srv/runs/x/manifest.json"),
        ValueError("1 validation error for Manifest\ndocuments.0.path\n  C:/srv/secret"),
        OSError("C:/srv/secret: disk full"),
    ],
)
def test_a_failed_job_shows_a_fixed_message_per_kind_never_the_error_text(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
    error: Exception,
) -> None:
    """A server path or a validation dump stays in the log (audit S5)."""
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    fake.error = error
    job = upload(client, decider, pdf(1, f"fails with {type(error).__name__}")).json()
    assert worker.run_once() is not None
    polled = client.get(f"/uploads/{job['id']}", headers=decider).json()
    assert polled["status"] == "failed"
    assert "srv" not in polled["message"] and "C:/" not in polled["message"]
    assert polled["message"] in set(FAILURE_MESSAGES.values()) or "server log" in polled["message"]


def test_the_worker_lock_has_a_namespace_of_its_own() -> None:
    """Not the namespace of the per-Equipment upload lock (an Equipment whose hash is 1 would
    hold the worker lock), nor one of the transaction lock namespaces (audit C14)."""
    ns = store.WORKER_LOCK[0]
    assert ns != store.UPLOAD_REV_LOCK_NS
    assert ns not in {1, 2, 3, 4, 5, 6, locks.EQUIPMENT_LOCK_NS}


def test_the_uploads_sharing_a_revision_are_listed_newest_first(
    client: TestClient,
    decider: dict[str, str],
    runs: Path,
    settings: UploadSettings,
    fresh_database: Databases,
) -> None:
    fake = Fake(runs)
    worker = Worker(engine(fresh_database.app), fake, settings.blobs, runs)
    fake.error = MissingRecording("gone")
    first = upload(client, decider, pdf(1, "one")).json()
    assert worker.run_once() is not None
    second = upload(client, decider, pdf(1, "two")).json()
    listed = client.get("/equipment/TP-201/drafts", headers=decider).json()["jobs"]
    assert [j["id"] for j in listed] == [second["id"], first["id"]]


def _alembic(fresh_database: Databases) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(traceq_db.__file__).parent / "migrations"))
    cfg.attributes["url"] = fresh_database.owner
    return cfg


def _upload_job_constraints(fresh_database: Databases) -> set[str]:
    with transaction(engine(fresh_database.owner)) as session:
        return set(
            session.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'upload_jobs'::regclass"
                    " UNION SELECT indexname FROM pg_indexes WHERE tablename = 'upload_jobs'"
                )
            ).scalars()
        )


def test_migration_0023_goes_down_and_up_again(fresh_database: Databases) -> None:
    cfg = _alembic(fresh_database)
    names = _upload_job_constraints(fresh_database)
    assert "upload_jobs_live_rev" in names and "upload_jobs_equipment_rev_key" not in names
    command.downgrade(cfg, "0022")
    names = _upload_job_constraints(fresh_database)
    assert "upload_jobs_equipment_rev_key" in names and "upload_jobs_live_rev" not in names
    command.upgrade(cfg, "head")
    assert "upload_jobs_live_rev" in _upload_job_constraints(fresh_database)


def test_migration_0023_does_not_go_down_while_a_revision_is_shared(
    fresh_database: Databases,
) -> None:
    """Going down needs the old unique revision again: refused, and nothing is deleted."""
    with transaction(engine(fresh_database.owner)) as session:
        for sha, status in (("a", "failed"), ("b", "queued")):
            session.execute(
                text(
                    "INSERT INTO upload_jobs (equipment, rev, sha256, size_bytes, pages, status,"
                    " reserved_usd, cost_usd, finished_at, subject, issuer, name) VALUES"
                    " ('TP-201', 0, :sha, 1, 1, :status, 0,"
                    " CASE WHEN :status = 'failed' THEN 0 END,"
                    " CASE WHEN :status = 'failed' THEN now() END, 's', 'i', 'n')"
                ),
                {"sha": sha * 64, "status": status},
            )
    with pytest.raises(Exception, match="share a revision"):
        command.downgrade(_alembic(fresh_database), "0022")
    with transaction(engine(fresh_database.owner)) as session:
        assert session.execute(text("SELECT count(*) FROM upload_jobs")).scalar_one() == 2
