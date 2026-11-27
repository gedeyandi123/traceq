"""The routes for uploading a Protocol Draft from the browser and following its run.

Upload and polling need the deciding role and an Equipment in the scope of the upload settings
(one Equipment). The body is the PDF itself (``Content-Type: application/pdf``), so there is
no file name to trust: it is counted while read against the size cap, checked for the PDF
signature and the page cap, hashed, and stored under its hash. The budget is reserved in the
same transaction that queues the job, and a refusal queues nothing. The worker
(``traceq.uploads.worker``) does the rest; a client polls ``getDraftUpload``.

Mode Cloud sends text to an external provider (ADR 0001): only synthetic data is allowed. The
upload page says so; so does ``DraftUploads.cloud_notice`` for any client.

No ``from __future__ import annotations``: FastAPI reads the annotations naming the
per-application dependency (``principal``), a local name, at definition time.
"""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine

from traceq.audit import Actor
from traceq.db import transaction
from traceq.db.ranges import BIGINT_MAX
from traceq.identity import Principal
from traceq.rounds import latest_draft_revision
from traceq.uploads import checks, store
from traceq.uploads.runner import UploadSettings, draft_doc_id, has_draft_recording

CLOUD_NOTICE = (
    "Mode Cloud sends the text of the document to an external model provider. Upload only"
    " synthetic data (ADR 0001): never a real plant document."
)


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UploadJobView(_Model):
    id: int
    equipment: str
    rev: int
    """The draft revision number the upload was given, assigned under a lock per Equipment."""
    sha256: str
    size_bytes: int
    pages: int
    status: JobStatus
    reserved_usd: float
    """The live budget held for it; 0 when this revision of its bytes is recorded and it
    replays."""
    cost_usd: float | None
    run_id: str | None
    """The run it produced, once ``succeeded``."""
    message: str | None
    """Why it ``failed``."""
    at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    name: str
    """Who uploaded it, as shown at the time."""


class DraftUploads(_Model):
    equipment: str
    max_bytes: int
    max_pages: int
    live_budget_usd: float
    live_remaining_usd: float
    cloud_notice: str
    jobs: list[UploadJobView]
    """The Equipment's uploads, newest revision first."""


def _view(j: store.Job) -> UploadJobView:
    return UploadJobView(
        id=j.id,
        equipment=j.equipment,
        rev=j.rev,
        sha256=j.sha256,
        size_bytes=j.size_bytes,
        pages=j.pages,
        status=cast(JobStatus, j.status),
        reserved_usd=float(j.reserved_usd),
        cost_usd=None if j.cost_usd is None else float(j.cost_usd),
        run_id=j.run_id,
        message=j.message,
        at=j.at,
        started_at=j.started_at,
        finished_at=j.finished_at,
        name=j.actor.name,
    )


def create_router(
    db: Engine | None,
    principal: Callable[..., Principal],
    settings: UploadSettings | None,
) -> APIRouter:
    """``settings``: none when uploads are not configured; the routes then answer 404."""
    router = APIRouter()

    def database() -> Engine:
        if db is None:
            raise HTTPException(401, "no database is configured")
        return db

    def scoped(who: Principal, equipment: str | None) -> UploadSettings:
        if not who.may_decide:
            raise HTTPException(403, "uploading a draft needs the deciding role")
        if settings is None:
            raise HTTPException(404, "uploads are not enabled")
        if equipment is not None and equipment != settings.equipment:
            raise HTTPException(403, f"uploads are not enabled for {equipment}")
        return settings

    def reserve(
        conf: UploadSettings, actor: Actor, data: bytes, checked: checks.Checked, equipment: str
    ) -> store.Job:
        ceiling = store.usd(conf.budget_usd)
        with transaction(database()) as session:
            store.lock_equipment(session, equipment)
            if store.already_uploaded(session, equipment, checked.sha256):
                raise store.DuplicateUpload(
                    "these bytes were already uploaded for this Equipment; a revision needs"
                    " a changed file"
                )
            rev = store.next_rev(
                session,
                equipment,
                latest_draft_revision(session, equipment, draft_doc_id(equipment)),
            )
            replays = has_draft_recording(conf, checked.sha256, rev)
            if not replays and (conf.live is None or conf.budget_usd <= 0):
                raise store.BudgetRefused(
                    f"no model recording exists for these bytes as revision {rev}, and reading"
                    " them live is off (the live budget is 0)"
                )
            estimate = (
                Decimal(0) if replays else store.usd(checked.pages * conf.estimate_per_page_usd)
            )
            job = store.accept(
                session,
                actor,
                equipment=equipment,
                rev=rev,
                sha256=checked.sha256,
                size_bytes=checked.size_bytes,
                pages=checked.pages,
                estimate=estimate,
                ceiling=ceiling,
            )
            store.save_blob(conf.blobs, checked.sha256, data)
        return job

    @router.get("/equipment/{equipment}/drafts", operation_id="listDraftUploads")
    def list_uploads(equipment: str, who: Annotated[Principal, Depends(principal)]) -> DraftUploads:
        """The Equipment's uploaded drafts and the limits an upload must keep."""
        conf = scoped(who, equipment)
        with transaction(database()) as session:
            jobs = store.for_equipment(session, equipment)
            reserved, spent = store.budget(session)
        ceiling = store.usd(conf.budget_usd)
        return DraftUploads(
            equipment=equipment,
            max_bytes=conf.max_bytes,
            max_pages=conf.max_pages,
            live_budget_usd=float(ceiling),
            live_remaining_usd=float(max(ceiling - reserved - spent, Decimal(0))),
            cloud_notice=CLOUD_NOTICE,
            jobs=[_view(j) for j in jobs],
        )

    @router.post(
        "/equipment/{equipment}/drafts",
        operation_id="uploadDraft",
        status_code=202,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    async def upload(
        equipment: str, request: Request, who: Annotated[Principal, Depends(principal)]
    ) -> UploadJobView:
        """Queues a Protocol Draft PDF as the Equipment's next revision. The body is the PDF.
        Refused when it is not a PDF (415, 422), passes the size or page cap (413, 422), holds
        bytes already uploaded for the Equipment (409), or has no recording as the revision it
        would be and the live budget does not cover reading it live (402)."""
        conf = scoped(who, equipment)
        if (
            request.headers.get("content-type", "").split(";")[0].strip().lower()
            != "application/pdf"
        ):
            raise HTTPException(415, "send the PDF as the body, as application/pdf")
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > conf.max_bytes:
            raise HTTPException(413, "the file passes the size cap")
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > conf.max_bytes:
                raise HTTPException(413, "the file passes the size cap")
            chunks.append(chunk)
        data = b"".join(chunks)
        actor = Actor(subject=who.subject, issuer=who.issuer, name=who.name)

        def accept() -> store.Job:
            checked = checks.check_pdf(data, max_bytes=conf.max_bytes, max_pages=conf.max_pages)
            return reserve(conf, actor, data, checked, equipment)

        try:
            job = await run_in_threadpool(accept)
        except checks.TooLarge as e:
            raise HTTPException(413, str(e)) from e
        except checks.Refused as e:
            raise HTTPException(422, str(e)) from e
        except store.DuplicateUpload as e:
            raise HTTPException(409, str(e)) from e
        except store.BudgetRefused as e:
            raise HTTPException(402, str(e)) from e
        return _view(job)

    @router.get("/uploads/{job_id}", operation_id="getDraftUpload")
    def get_upload(
        job_id: Annotated[int, Path(ge=1, le=BIGINT_MAX)],
        who: Annotated[Principal, Depends(principal)],
    ) -> UploadJobView:
        """Where an upload stands: ``queued``, ``running``, ``succeeded`` (with its run) or
        ``failed`` (with why)."""
        scoped(who, None)
        with transaction(database()) as session:
            job = store.get(session, job_id)
        if job is None or settings is None or job.equipment != settings.equipment:
            raise HTTPException(404, f"no upload {job_id}")
        return _view(job)

    return router
