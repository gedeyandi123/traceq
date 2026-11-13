"""The eval screen's read-only API (spec #29): harness code, aggregates only.

Scoring is a harness step: ``python -m traceq_eval ... --out runs/<run id>`` writes
``report.json`` beside the run's files. This API reads that report and the run's cost from
``run.json`` and serves, per scored run, each rate with k/n and its split (dev TP-201,
held-out otherwise), the gate verdict and the cost. It never serves report items (per-item
expected values) or baseline contents; the system's API (``traceq.runs.api``) serves no
score at all.

Usage::

    uv run python -m traceq_eval.screen serve [--runs runs] [--host 127.0.0.1] [--port 8001]
    uv run python -m traceq_eval.screen openapi OUT
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

REPORT_FILE = "report.json"
RUN_FILE = "run.json"
DEV = frozenset({"TP-201"})
"""Equipment prompts are developed on; every other Equipment is held out."""
_RUN_ID = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_-]{0,63}$")


class Rate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric: str
    k: int
    n: int
    rate: float | None
    """k / n, none when n is 0."""
    better: Literal["higher", "lower"]


class EvalSummary(BaseModel):
    """One scored run, as aggregates."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str
    equipment: str
    split: Literal["dev", "held_out"]
    scorer_version: str
    gates_passed: bool
    rates: list[Rate]
    model: str | None
    mode: Literal["replay", "live"] | None
    cost_usd: float | None
    """From the run's metadata; none when the run folder has no ``run.json``."""


def _rate(metric: str, k: int, n: int, better: Literal["higher", "lower"] = "higher") -> Rate:
    return Rate(metric=metric, k=k, n=n, rate=round(k / n, 4) if n else None, better=better)


def summarise(run_id: str, report: dict[str, Any], run: dict[str, Any] | None) -> EvalSummary:
    """Aggregate a scorer report (``traceq_eval.score``) and the run's metadata."""
    reqs = report["requirements"]["items"]
    cites = report["citations"]
    defects = report["defects"]["items"]
    fab = report["fabrication"]
    probes = report["probes"]["metrics"]
    ocr = report["ocr"]["items"]
    equipment = str(report["equipment"])
    return EvalSummary(
        run_id=run_id,
        equipment=equipment,
        split="dev" if equipment in DEV else "held_out",
        scorer_version=str(report["scorer_version"]),
        gates_passed=bool(report["gates"]["passed"]),
        rates=[
            _rate("extraction_accuracy", sum(bool(i["value_ok"]) for i in reqs), len(reqs)),
            _rate("citation_groundedness", int(cites["by_status"]["verified"]), cites["total"]),
            _rate("defect_recall", sum(bool(d["found_by"]) for d in defects), len(defects)),
            _rate("fabrication_rate", fab["fabricated"], fab["claims"], "lower"),
            _rate("probe_fabrication_rate", probes["fabricated"], probes["probes"], "lower"),
            _rate("ocr_exact_match", sum(bool(i["exact"]) for i in ocr), len(ocr)),
            _rate("ocr_entry_recall", sum(i["matched_by"] is not None for i in ocr), len(ocr)),
            _rate("ocr_cer", sum(i["edits"] for i in ocr), sum(i["chars"] for i in ocr), "lower"),
        ],
        model=None if run is None else str(run["model"]),
        mode=None if run is None else run["mode"],
        cost_usd=None if run is None else float(run["cost_usd"]),
    )


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def create_app(runs: Path) -> FastAPI:
    """``runs``: the run folders, a scored one holding ``report.json``."""
    app = FastAPI(
        title="TraceQ eval", version="0.1.0", summary="Read-only aggregates of scored runs."
    )

    def scored(run_id: str) -> Path | None:
        path = runs / run_id
        return path if _RUN_ID.match(run_id) and (path / REPORT_FILE).is_file() else None

    def summary(path: Path) -> EvalSummary:
        run = _read(path / RUN_FILE) if (path / RUN_FILE).is_file() else None
        return summarise(path.name, _read(path / REPORT_FILE), run)

    @app.get("/evals", operation_id="listEvals")
    def list_evals() -> list[EvalSummary]:
        """Every scored run, newest run id first."""
        found = [p for p in (runs.iterdir() if runs.is_dir() else ()) if scored(p.name)]
        return [summary(p) for p in sorted(found, key=lambda p: p.name, reverse=True)]

    @app.get("/evals/{run_id}", operation_id="getEval")
    def get_eval(run_id: str) -> EvalSummary:
        path = scored(run_id)
        if path is None:
            raise HTTPException(404, f"no scored run {run_id}")
        return summary(path)

    return app


def openapi_schema() -> dict[str, Any]:
    return create_app(Path("runs")).openapi()


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(create_app(args.runs), host=args.host, port=args.port)


def _openapi(args: argparse.Namespace) -> None:
    text = json.dumps(openapi_schema(), ensure_ascii=False, indent=2) + "\n"
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="traceq_eval.screen")
    commands = parser.add_subparsers(dest="command", required=True)
    s = commands.add_parser("serve", help="serve aggregates of scored runs read-only")
    s.add_argument("--runs", type=Path, default=Path("runs"))
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8001)
    s.set_defaults(func=_serve)
    o = commands.add_parser("openapi", help="write the OpenAPI schema")
    o.add_argument("out", type=Path)
    o.set_defaults(func=_openapi)
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], None] = args.func
    func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
