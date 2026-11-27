"""Browser upload of a Protocol Draft and the background worker, over HTTP with a real Postgres
and the demo issuer (spec #375, ticket S5; spec #342).

The runner is a stand-in that writes the fixture run of ``tests/test_proposals_api.py`` for
each job: what is under test is the queue, the checks, the budget, the revision numbers and
what the worker does with a run, not the pipeline (``tests/test_run.py``). Nothing here sends
an LLM call.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_proposals_api import add_run, bearer, token
from test_upload_checks import pdf

from traceq.ai import MissingRecording
from traceq.app.api import create_app
from traceq.db import engine, transaction
from traceq.identity import IdentitySettings
from traceq.uploads import RunResult, UploadSettings, Worker, store
from traceq.uploads.checks import sha256_of
from traceq.uploads.store import Job

PDF = {"content-type": "application/pdf"}


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


def test_a_reupload_of_the_same_bytes_is_the_next_revision_and_costs_nothing_live(
    client: TestClient, decider: dict[str, str], worker: Worker, fresh_database: Databases
) -> None:
    data = pdf(2, "same")
    first = upload(client, decider, data).json()
    assert Decimal(str(first["reserved_usd"])) == Decimal("0.02")
    assert worker.run_once() is not None
    again = upload(client, decider, data).json()
    assert (again["rev"], again["sha256"], again["reserved_usd"]) == (1, first["sha256"], 0)
    assert worker.run_once() is not None
    assert ledger(fresh_database) == (Decimal(0), Decimal(0))


def test_bytes_with_a_recording_reserve_nothing_even_with_no_live_budget(
    client: TestClient,
    decider: dict[str, str],
    settings: UploadSettings,
    runs: Path,
    fresh_database: Databases,
    demo_issuer: DemoIssuer,
) -> None:
    data = pdf(2, "recorded")
    (settings.package_recordings / "ingest").mkdir(parents=True)
    (settings.package_recordings / "ingest" / f"{sha256_of(data)}-docling-1.json").write_text("{}")
    identity = IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience)
    replay_only = replace(settings, budget_usd=0.0)
    c = TestClient(
        create_app(runs, identity=identity, database=fresh_database.app, uploads=replay_only)
    )
    assert upload(c, decider, data).json()["reserved_usd"] == 0
    other = upload(c, decider, pdf(2, "never read"))
    assert other.status_code == 402


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
    assert done.message == "no recording for page 1 of the draft"
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


def test_a_job_left_running_by_a_dead_worker_fails_and_frees_its_reservation(
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
    assert ledger(fresh_database)[0] == Decimal(0)


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
