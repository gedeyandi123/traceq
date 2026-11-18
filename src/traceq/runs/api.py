"""The read-only API over run folders (spec #29): what the UI shows, nothing it may not.

A run folder is read through a named list of files, ``SERVED``: ``run.json``,
``matrix.json``, ``findings.json``, ``completeness.json`` and, for a Review Package run,
``protocol_draft.json`` (served with its decisions by the database routes). Nothing else in
it is ever opened, so a scorer report written beside them stays private. From ``run.json`` only the
summary fields and the dropped claims are served, never per-item scores. A cited page
opens from the released corpus, and only for a document the run read, with the bytes it
read.

There is no upload and no database: every route is a GET. The database routes over the same
runs are in ``traceq.proposals``.

``create_router`` returns the routes; the ``app`` module composes them into the application
(``python -m traceq.app.api OUT`` writes the OpenAPI schema, ADR 0003).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from traceq.documents import Corpus
from traceq.runs.completeness import COMPLETENESS_FILE
from traceq.runs.protocol_draft import DRAFT_FILE
from traceq.runs.schemas import Completeness, DroppedClaim, Findings, Matrix, RunSummary

RUN_FILE = "run.json"
MATRIX_FILE = "matrix.json"
FINDINGS_FILE = "findings.json"
SERVED = (RUN_FILE, MATRIX_FILE, FINDINGS_FILE, COMPLETENESS_FILE, DRAFT_FILE)
"""The only files of a run folder the API opens."""
_RUN_ID = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_-]{0,63}$")
_MEDIA = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def read_served(path: Path) -> Any:
    """A file of a run folder, only if it is one of ``SERVED``."""
    if path.name not in SERVED:
        raise ValueError(f"{path.name} is not a file the API serves")
    return json.loads(path.read_text(encoding="utf-8"))


def find_run(runs: Path, run_id: str) -> Path | None:
    """The folder of run ``run_id`` in ``runs``; ``None`` for an id that is not a run's."""
    path = runs / run_id
    return path if _RUN_ID.match(run_id) and (path / RUN_FILE).is_file() else None


def create_router(runs: Path, corpus: Path | None = None) -> APIRouter:
    """``runs``: the directory ``traceq run`` writes run folders into. ``corpus``: the
    released corpus the runs read, for opening a cited page (none: no document route)."""
    router = APIRouter()

    def folder(run_id: str) -> Path:
        path = find_run(runs, run_id)
        if path is None:
            raise HTTPException(404, f"no run {run_id}")
        return path

    def summary(path: Path) -> RunSummary:
        meta: dict[str, Any] = read_served(path / RUN_FILE)
        return RunSummary(
            run_id=str(meta["run_id"]),
            created=str(meta["created"]),
            equipment=str(meta["corpus"]["equipment"]),
            model=str(meta["model"]),
            mode=meta["mode"],
            pipeline_version=str(meta["pipeline_version"]),
        )

    @router.get("/runs", operation_id="listRuns")
    def list_runs() -> list[RunSummary]:
        """Every run folder, newest first."""
        found = (
            [
                summary(p)
                for p in runs.iterdir()
                if _RUN_ID.match(p.name) and (p / RUN_FILE).is_file()
            ]
            if runs.is_dir()
            else []
        )
        return sorted(found, key=lambda r: r.created, reverse=True)

    @router.get("/runs/{run_id}", operation_id="getRun")
    def get_run(run_id: str) -> RunSummary:
        return summary(folder(run_id))

    @router.get("/runs/{run_id}/matrix", operation_id="getMatrix")
    def get_matrix(run_id: str) -> Matrix:
        """The traceability matrix: Coverage class and reason, and cited Evidence."""
        return Matrix.model_validate(read_served(folder(run_id) / MATRIX_FILE))

    @router.get("/runs/{run_id}/findings", operation_id="getFindings")
    def get_findings(run_id: str) -> Findings:
        """The Pre-review: Check Findings, AI Findings kept apart, and missing documents."""
        return Findings.model_validate(read_served(folder(run_id) / FINDINGS_FILE))

    @router.get("/runs/{run_id}/dropped", operation_id="getDropped")
    def get_dropped(run_id: str) -> list[DroppedClaim]:
        """The claims the citation check dropped, each with its subject and reason."""
        meta: dict[str, Any] = read_served(folder(run_id) / RUN_FILE)
        return [
            DroppedClaim(claim=str(d["claim"]), id=str(d["id"]), reason=str(d["reason"]))
            for d in meta.get("dropped", [])
        ]

    @router.get("/runs/{run_id}/completeness", operation_id="getCompleteness")
    def get_completeness(run_id: str) -> Completeness:
        """The URS completeness check; not found for a run written before it existed."""
        path = folder(run_id) / COMPLETENESS_FILE
        if not path.is_file():
            raise HTTPException(404, f"the completeness check did not run for {run_id}")
        return Completeness.model_validate(read_served(path))

    @router.get(
        "/runs/{run_id}/documents/{doc_id}/{rev}",
        operation_id="getDocument",
        response_class=Response,
        responses={200: {"content": {m: {} for m in _MEDIA.values()}}},
    )
    def get_document(run_id: str, doc_id: str, rev: int) -> Response:
        """A document the run read, as released: a citation links here with ``#page=N``."""
        meta: dict[str, Any] = read_served(folder(run_id) / RUN_FILE)
        read = {
            (str(d["doc_id"]), int(d["rev"])): str(d["sha256"]) for d in meta["corpus"]["documents"]
        }
        if corpus is None or (doc_id, rev) not in read:
            raise HTTPException(404, f"{doc_id} rev {rev} is not a document of this run")
        doc = Corpus.load(corpus, str(meta["corpus"]["equipment"])).find(doc_id, rev)
        if doc is None or doc.sha256 != read[(doc_id, rev)] or not doc.path.is_file():
            raise HTTPException(404, f"{doc_id} rev {rev} is not in the served corpus")
        data = doc.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != doc.sha256:
            raise HTTPException(404, f"{doc_id} rev {rev}: bytes do not match the manifest")
        media = _MEDIA.get(doc.path.suffix.lower(), "application/octet-stream")
        disposition = f'inline; filename="{doc.path.name}"'
        return Response(data, media_type=media, headers={"Content-Disposition": disposition})

    return router
