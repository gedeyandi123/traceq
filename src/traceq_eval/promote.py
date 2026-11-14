"""Promote a live run into a recordings folder and, when its gates pass, a baseline (#86).

Usage::

    uv run python -m traceq_eval promote runs/<run id> --recordings recordings/haiku-r<n>
        [--baseline [PATH]] [--corpus DIR] [--world PATH] [--key answer_key]

The live run must have recorded its calls into ``--recordings`` (``traceq run --live
--recordings recordings/haiku-r<n>``). A top-up run, which sent only the calls missing from
an earlier recordings folder, is promoted the same way: the folder holds every call.

The run is replayed on the current code from ``--recordings`` (corpus: the release
manifest, by default ``<recordings>/../corpus-<dataset version>``). The replay must send
nothing and reproduce the live run: the same calls, tokens and cost, and the same
submission apart from the run id; otherwise nothing is written. The live submission is
then scored and the folder gets ``report-<tag>.json`` (the report, with the live run id)
and ``run-<tag>.json`` (the live ``run.json`` as it is). ``--baseline`` writes the baseline
(default ``baselines/<tag>.json``) only when every gate passes. The command prints the
Equipment's column of the ``recordings/README.md`` tables; it edits no README.

Exit code 0 when the run is promoted and its gates pass, 1 when a gate fails (the
recordings are still written, the baseline is not), 2 when the run cannot be promoted.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from traceq.ai import MissingRecording
from traceq.documents import OcrUnavailable
from traceq.runs.run import run
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval import ratchet
from traceq_eval.citations import PageTexts
from traceq_eval.report import with_metadata
from traceq_eval.score import score
from traceq_eval.submission import Submission

SPLITS = {"dev": "dev", "held_out": "held-out"}


class PromoteError(ValueError):
    """The run cannot be promoted: not live, or its replay does not reproduce it."""


@dataclass(frozen=True)
class Promoted:
    report: dict[str, Any]
    baseline: Path | None
    """The baseline written, ``None`` when not asked or a gate failed."""
    column: str
    """The Equipment's column of the README tables, as a two-column Markdown table."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PromoteError(f"cannot read {path}: {e}") from e


def _without_run_id(sub: dict[str, Any]) -> dict[str, Any]:
    return {**sub, "system": {k: v for k, v in sub["system"].items() if k != "run_id"}}


def _replay(live: dict[str, Any], live_sub: dict[str, Any], recordings: Path, corpus: Path) -> None:
    tag = live["corpus"]["equipment"]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            out = run(
                corpus,
                Path(tmp),
                recordings,
                live["model"],
                equipment=tag,
                vendor_reuse=live["settings"]["vendor_reuse"],
            )
        except (MissingRecording, OcrUnavailable) as e:
            raise PromoteError(f"{recordings} does not hold every call of the run: {e}") from e
    got = out.metadata
    total = live["calls"]["total"]
    expected = {"total": total, "replayed": total, "live": 0}
    if got["calls"] != expected:
        raise PromoteError(f"replay calls {got['calls']}, the live run needs {expected}")
    for field in ("tokens", "cost_usd"):
        if got[field] != live[field]:
            raise PromoteError(f"replay {field} {got[field]}, live run {live[field]}")
    replayed = out.submission.model_dump(mode="json", exclude_none=True)
    if _without_run_id(replayed) != _without_run_id(live_sub):
        raise PromoteError("the replay's submission differs from the live run's")


def column(report: dict[str, Any], live: dict[str, Any]) -> str:
    """The Equipment's column of the ``recordings/README.md`` tables, with k/n."""
    head, req = report["headline"], report["requirements"]

    def kn(metric: str) -> str:
        return f"{head[metric]['k']}/{head[metric]['n']}"

    coverage = sum(i["coverage_ok"] for i in req["items"])
    gates = report["gates"]
    failed = [f"`{n}`: {g['count']}" for n, g in gates.items() if n != "passed" and not g["passed"]]
    calls, tokens = live["calls"], live["tokens"]
    rows = [
        ("run id", live["run_id"]),
        ("coverage", f"{coverage}/{req['metrics']['requirements']}"),
        ("value", kn("requirements.value_accuracy")),
        ("defect recall", kn("defects.recall")),
        ("probes fabricated", kn("probes.fabrication_rate")),
        ("fabrication", kn("fabrication.rate")),
        ("gates", "PASS" if gates["passed"] else f"FAIL ({', '.join(failed)})"),
        ("calls (live)", f"{calls['total']} ({calls['live']})"),
        ("tokens in/out", f"{tokens['input']}/{tokens['output']}"),
        ("cost USD (live)", f"{live['cost_usd']:.6f} ({live['live_cost_usd']:.6f})"),
    ]
    split = SPLITS.get(report["split"], report["split"])
    lines = [f"| | {report['equipment']} ({split}) |", "|---|---|"]
    return "\n".join([*lines, *(f"| {name} | {value} |" for name, value in rows)])


def promote(
    run_dir: Path,
    recordings: Path,
    *,
    corpus: Path | None = None,
    world: Path | None = None,
    key: Path = Path("answer_key"),
    baseline: Path | None = None,
) -> Promoted:
    """Replay and check the live run in ``run_dir``, then write it into ``recordings``."""
    live: dict[str, Any] = _json(run_dir / "run.json")
    live_sub: dict[str, Any] = _json(run_dir / "submission.json")
    if live.get("mode") != "live":
        raise PromoteError(f"{run_dir} is a {live.get('mode')} run, not a live one")
    if live_sub["system"]["run_id"] != live["run_id"]:
        raise PromoteError("submission.json and run.json name different runs")
    tag: str = live["corpus"]["equipment"]
    corpus = corpus or recordings.parent / f"corpus-{version('traceq-dataset')}"
    world = world or Path("world") / f"{tag.lower().replace('-', '')}.yaml"

    _replay(live, live_sub, recordings, corpus)

    try:
        sub = Submission.model_validate(live_sub)
    except ValidationError as e:
        raise PromoteError(f"invalid submission: {e}") from e
    eq = load(world)
    pages = build_corpus(eq)
    key_dir = key / eq.tag
    report = with_metadata(score(sub, load_key(key_dir), PageTexts(pages)), sub, pages, key_dir)

    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (recordings / f"report-{tag}.json").write_text(text, encoding="utf-8", newline="\n")
    shutil.copyfile(run_dir / "run.json", recordings / f"run-{tag}.json")
    written = None
    if baseline and report["gates"]["passed"]:
        ratchet.dump(ratchet.from_report(report), baseline)
        written = baseline
    return Promoted(report, written, column(report, live))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="traceq_eval promote")
    parser.add_argument("run", type=Path, help="the live run folder, runs/<run id>")
    parser.add_argument("--recordings", type=Path, required=True)
    parser.add_argument(
        "--baseline",
        type=Path,
        nargs="?",
        const=Path(),
        help="write the baseline when the gates pass (default baselines/<tag>.json)",
    )
    parser.add_argument("--corpus", type=Path, help="release manifest directory")
    parser.add_argument("--world", type=Path, help="default world/<tag>.yaml")
    parser.add_argument("--key", type=Path, default=Path("answer_key"))
    args = parser.parse_args(argv)

    baseline: Path | None = args.baseline
    try:
        if baseline == Path():
            tag = _json(args.run / "run.json")["corpus"]["equipment"]
            baseline = Path("baselines") / f"{tag}.json"
        got = promote(
            args.run,
            args.recordings,
            corpus=args.corpus,
            world=args.world,
            key=args.key,
            baseline=baseline,
        )
    except PromoteError as e:
        print(f"not promoted: {e}", file=sys.stderr)
        return 2
    tag = got.report["equipment"]
    passed = got.report["gates"]["passed"]
    print(
        f"gates {'PASS' if passed else 'FAIL'}; report-{tag}.json and run-{tag}.json in "
        f"{args.recordings}"
    )
    if got.baseline:
        print(f"baseline in {got.baseline}")
    elif baseline:
        print("no baseline written: a run that fails a gate cannot be one", file=sys.stderr)
    print()
    print(got.column)
    return 0 if passed else 1
