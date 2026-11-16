"""The composed API application: the routers of the modules, in one FastAPI app.

``python -m traceq.app.api OUT`` writes the OpenAPI schema the TypeScript client is
generated from (ADR 0003).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from traceq.runs.api import create_router as runs_router


def create_app(runs: Path, corpus: Path | None = None) -> FastAPI:
    """``runs``: the directory ``traceq run`` writes run folders into. ``corpus``: the
    released corpus the runs read, for opening a cited page (none: no document route)."""
    app = FastAPI(title="TraceQ", version="0.1.0", summary="Read-only API over run folders.")
    app.include_router(runs_router(runs, corpus))
    return app


def openapi_schema() -> dict[str, Any]:
    """The OpenAPI schema; it does not depend on which folders are served."""
    return create_app(Path("runs")).openapi()


def write_openapi(out: Path) -> None:
    text = json.dumps(openapi_schema(), ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_openapi(Path(sys.argv[1]))
