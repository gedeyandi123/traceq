"""The composed API application: the routers of the modules, in one FastAPI app.

Two states (spec #105). With default settings it trusts no issuer and has no database: the
read-only run-folder API, and every database route answers 401. With a trusted issuer and a
database both configured, the database routes work; it refuses to start with only one.

``python -m traceq.app.api OUT`` writes the OpenAPI schema the TypeScript client is
generated from (ADR 0003).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy import URL, make_url

from traceq.db import engine
from traceq.identity import IdentitySettings, Verifier
from traceq.identity.http import authenticate
from traceq.proposals.api import create_router as proposals_router
from traceq.runs.api import create_router as runs_router


def create_app(
    runs: Path,
    corpus: Path | None = None,
    *,
    identity: IdentitySettings | None = None,
    database: URL | str | None = None,
) -> FastAPI:
    """``runs``: the directory ``traceq run`` writes run folders into. ``corpus``: the
    released corpus the runs read, for opening a cited page (none: no document route).
    ``identity``: the trusted issuer; ``database``: the database, connected as the
    application role. Both or neither."""
    if (identity is None) != (database is None):
        raise ValueError("configure both a trusted issuer and a database, or neither")
    app = FastAPI(
        title="TraceQ",
        version="0.1.0",
        summary="Run folders read-only; Proposals in the database, behind a token.",
    )
    app.include_router(runs_router(runs, corpus))
    verifier = None if identity is None else Verifier(identity)
    db = None if database is None else engine(make_url(database))
    app.include_router(proposals_router(runs, db, authenticate(verifier)))
    return app


def openapi_schema() -> dict[str, Any]:
    """The OpenAPI schema; it does not depend on which folders are served."""
    return create_app(Path("runs")).openapi()


def write_openapi(out: Path) -> None:
    text = json.dumps(openapi_schema(), ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_openapi(Path(sys.argv[1]))
