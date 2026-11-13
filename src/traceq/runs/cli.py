"""``traceq run``: analyse a released corpus into a run folder.

Usage::

    traceq run CORPUS_DIR [--equipment TAG] [--out runs] [--recordings recordings]
        [--model claude-haiku-5-5] [--live] [--max-usd 1]

Without ``--live`` every LLM call is replayed from ``--recordings`` and nothing is sent.
With ``--live``, calls not yet recorded go to Mode Cloud through the Batch API and are
recorded; the run refuses before sending when their estimated cost would pass
``--max-usd``. Exit code 0 on success, 2 when a recording is missing, the budget refuses,
a scan is neither cached nor readable (OCR model not installed) or the corpus is unusable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from traceq.ai import BudgetExceeded, MissingRecording
from traceq.documents import OcrUnavailable

DEFAULT_MODEL = "claude-haiku-5-5"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traceq")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("run", help="analyse a released corpus into a run folder")
    p.add_argument("corpus", type=Path, help="corpus directory holding manifest.json")
    p.add_argument("--equipment")
    p.add_argument("--out", type=Path, default=Path("runs"))
    p.add_argument("--recordings", type=Path, default=Path("recordings"))
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--live", action="store_true", help="send unrecorded calls to the API")
    p.add_argument("--max-usd", type=float, default=1.0)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from traceq.runs.run import run

    live = None
    if args.live:
        from traceq.ai.cloud import CloudLLM

        live = CloudLLM(args.model)
    try:
        out = run(
            args.corpus,
            args.out,
            args.recordings,
            args.model,
            equipment=args.equipment,
            live=live,
            max_usd=args.max_usd,
        )
    except (
        MissingRecording,
        BudgetExceeded,
        OcrUnavailable,
        FileNotFoundError,
        ValueError,
    ) as e:
        print(f"traceq run: {e}", file=sys.stderr)
        return 2
    m = out.metadata
    print(
        f"{out.folder}: {len(out.submission.requirements)} requirements,"
        f" {m['calls']['total']} calls ({m['calls']['live']} live),"
        f" cost ${m['cost_usd']}, dropped {len(m['dropped'])} claims"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
