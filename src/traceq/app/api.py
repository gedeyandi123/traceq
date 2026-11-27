"""The composed API application: the routers of the modules, in one FastAPI app.

Two states (spec #105). With default settings it trusts no issuer and has no database: the
read-only run-folder API, and every database route answers 401. With a trusted issuer and a
database both configured, the database routes work; it refuses to start with only one.

``python -m traceq.app.api OUT`` writes the OpenAPI schema the TypeScript client is
generated from (ADR 0003).
"""

from __future__ import annotations

import json
import math
import sys
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import URL, make_url

from traceq.assembly import written
from traceq.assembly.api import create_router as assembly_router
from traceq.db import engine
from traceq.execution.api import create_router as execution_router
from traceq.identity import IdentitySettings, Verifier
from traceq.identity.http import authenticate, require_fresh_auth
from traceq.proposals.api import create_router as proposals_router
from traceq.registry import create_router as registry_router
from traceq.rounds import create_router as rounds_router
from traceq.rounds import register_import as register_round_import
from traceq.runs.api import create_router as runs_router
from traceq.uploads import UploadSettings, Worker, package_runner
from traceq.uploads import create_router as uploads_router


def create_app(
    runs: Path,
    corpus: Path | None = None,
    *,
    identity: IdentitySettings | None = None,
    database: URL | str | None = None,
    uploads: UploadSettings | None = None,
    run_worker: bool = False,
) -> FastAPI:
    """``runs``: the directory ``traceq run`` writes run folders into. ``corpus``: the
    released corpus the runs read, for opening a cited page (none: no document route).
    ``identity``: the trusted issuer; ``database``: the database, connected as the
    application role. Both or neither. ``uploads``: where drafts may be uploaded (needs the
    database); ``run_worker``: also run the one upload worker in this process."""
    if (identity is None) != (database is None):
        raise ValueError("configure both a trusted issuer and a database, or neither")
    if uploads is not None and database is None:
        raise ValueError("uploads need the trusted issuer and the database")
    if run_worker and uploads is None:
        raise ValueError("a worker needs the upload settings")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        if not run_worker or uploads is None or db is None:
            yield
            return
        stop = threading.Event()
        worker = Worker(db, package_runner(uploads, runs), uploads.blobs, runs)
        thread = threading.Thread(target=worker.loop, args=(stop,), name="upload-worker")
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)

    app = FastAPI(
        lifespan=lifespan,
        title="TraceQ",
        version="0.1.0",
        summary="Run folders read-only; Proposals in the database, behind a token.",
    )
    app.include_router(runs_router(runs, corpus))
    verifier = None if identity is None else Verifier(identity)
    db = None if database is None else engine(make_url(database))
    principal = authenticate(verifier)
    fresh_auth = require_fresh_auth(verifier)
    app.include_router(
        proposals_router(
            runs,
            db,
            principal,
            before_accepting=written.guard_accepting,
            after_import=register_round_import,
        )
    )
    app.include_router(assembly_router(runs, db, principal, fresh_auth=fresh_auth))
    app.include_router(execution_router(db, principal, fresh_auth=fresh_auth))
    app.include_router(rounds_router(runs, db, principal))
    app.include_router(registry_router(runs, db, principal))
    app.include_router(uploads_router(db, principal, uploads))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        def _sanitize(obj: Any) -> Any:
            if isinstance(obj, float) and not math.isfinite(obj):
                return str(obj)
            if isinstance(obj, dict):
                d = cast(dict[str, Any], obj)
                return {k: _sanitize(v) for k, v in d.items()}
            if isinstance(obj, list | tuple):
                seq = cast(list[Any] | tuple[Any, ...], obj)
                return [_sanitize(v) for v in seq]
            return obj

        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(_sanitize(exc.errors()))},
        )

    return app


def openapi_schema() -> dict[str, Any]:
    """The OpenAPI schema; it does not depend on which folders are served."""
    return create_app(Path("runs")).openapi()


def write_openapi(out: Path) -> None:
    text = json.dumps(openapi_schema(), ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_openapi(Path(sys.argv[1]))
