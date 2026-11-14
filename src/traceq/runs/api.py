"""The read-only API over run folders (spec #29): what the UI shows, nothing it may not.

A run folder is read through exactly three files, ``run.json``, ``matrix.json`` and
``findings.json``; nothing else in it is ever opened, so a scorer report written beside
them stays private. From ``run.json`` only the summary fields are served, never per-item
scores. A cited page opens from the released corpus, and only for a document the run read,
with the bytes it read.

There is no upload and no database: every route is a GET.

``python -m traceq.runs.api OUT`` writes the OpenAPI schema the TypeScript client is
generated from (ADR 0003).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from traceq.documents import Corpus
from traceq.runs.schemas import Findings, Matrix, RunSummary

RUN_FILE = "run.json"
MATRIX_FILE = "matrix.json"
FINDINGS_FILE = "findings.json"
_RUN_ID = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_-]{0,63}$")
_MEDIA = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def create_app(runs: Path, corpus: Path | None = None) -> FastAPI:
    """``runs``: the directory ``traceq run`` writes run folders into. ``corpus``: the
    released corpus the runs read, for opening a cited page (none: no document route)."""
    app = FastAPI(title="TraceQ", version="0.1.0", summary="Read-only API over run folders.")

    def folder(run_id: str) -> Path:
        path = runs / run_id
        if not _RUN_ID.match(run_id) or not (path / RUN_FILE).is_file():
            raise HTTPException(404, f"no run {run_id}")
        return path

    def summary(path: Path) -> RunSummary:
        meta: dict[str, Any] = _read(path / RUN_FILE)
        return RunSummary(
            run_id=str(meta["run_id"]),
            created=str(meta["created"]),
            equipment=str(meta["corpus"]["equipment"]),
            model=str(meta["model"]),
            mode=meta["mode"],
            pipeline_version=str(meta["pipeline_version"]),
        )

    @app.get("/runs", operation_id="listRuns")
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

    @app.get("/runs/{run_id}", operation_id="getRun")
    def get_run(run_id: str) -> RunSummary:
        return summary(folder(run_id))

    @app.get("/runs/{run_id}/matrix", operation_id="getMatrix")
    def get_matrix(run_id: str) -> Matrix:
        """The traceability matrix: Coverage class and reason, and cited Evidence."""
        return Matrix.model_validate(_read(folder(run_id) / MATRIX_FILE))

    @app.get("/runs/{run_id}/findings", operation_id="getFindings")
    def get_findings(run_id: str) -> Findings:
        """The Pre-review: Check Findings, AI Findings kept apart, and missing documents."""
        return Findings.model_validate(_read(folder(run_id) / FINDINGS_FILE))

    @app.get(
        "/runs/{run_id}/documents/{doc_id}/{rev}",
        operation_id="getDocument",
        response_class=Response,
        responses={200: {"content": {m: {} for m in _MEDIA.values()}}},
    )
    def get_document(run_id: str, doc_id: str, rev: int) -> Response:
        """A document the run read, as released: a citation links here with ``#page=N``."""
        meta: dict[str, Any] = _read(folder(run_id) / RUN_FILE)
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

    return app


def openapi_schema() -> dict[str, Any]:
    """The OpenAPI schema; it does not depend on which folders are served."""
    return create_app(Path("runs")).openapi()


def write_openapi(out: Path) -> None:
    text = json.dumps(openapi_schema(), ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_openapi(Path(sys.argv[1]))
