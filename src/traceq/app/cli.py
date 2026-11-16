"""``traceq run``: analyse a released corpus into a run folder.

Usage::

    traceq run CORPUS_DIR [--equipment TAG] [--out runs] [--recordings recordings]
        [--model claude-haiku-5-5] [--live] [--max-usd 1] [--no-vendor-reuse]
    traceq serve [--runs runs] [--corpus CORPUS_DIR] [--host 127.0.0.1] [--port 8000]
    traceq demo-issuer [--port 9000] [--audience traceq] [--role-claim roles]

Without ``--live`` every LLM call is replayed from ``--recordings`` and nothing is sent.
With ``--live``, calls not yet recorded go to Mode Cloud through the Batch API and are
recorded; the run refuses before sending when their estimated cost would pass
``--max-usd``. Exit code 0 on success, 2 when a recording is missing, the budget refuses,
a scan is neither cached nor readable (OCR model not installed) or the corpus is unusable.

``--no-vendor-reuse`` drafts a Test Step for every requirement, also those the vendor
covered, for the "could be saved by reuse" framing. Eval runs keep the default
(``vendor_reuse`` true), which scorer criterion 1 assumes.

``traceq serve`` starts the read-only API over the run folders in ``--runs``; ``--corpus``
is the released corpus they read, so a citation opens its page.

``traceq demo-issuer`` starts the demo OIDC issuer on ``http://127.0.0.1:PORT`` (never
another interface): demo identities without a password, for the demo only.
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
    p.add_argument(
        "--no-vendor-reuse",
        dest="vendor_reuse",
        action="store_false",
        help="draft a Test Step for every requirement, also those the vendor covered",
    )
    s = commands.add_parser("serve", help="serve run folders read-only")
    s.add_argument("--runs", type=Path, default=Path("runs"))
    s.add_argument("--corpus", type=Path, help="released corpus directory holding manifest.json")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    i = commands.add_parser(
        "demo-issuer", help="start the demo OIDC issuer (demo identities, local machine only)"
    )
    i.add_argument("--port", type=int, default=9000)
    i.add_argument("--audience", default="traceq")
    i.add_argument("--role-claim", default="roles")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.command == "demo-issuer":
        import uvicorn

        from traceq.identity.issuer import create_issuer

        url = f"http://127.0.0.1:{args.port}"
        app = create_issuer(url, audience=args.audience, role_claim=args.role_claim)
        uvicorn.run(app, host="127.0.0.1", port=args.port)
        return 0

    if args.command == "serve":
        import uvicorn

        from traceq.app.api import create_app

        uvicorn.run(create_app(args.runs, args.corpus), host=args.host, port=args.port)
        return 0

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
            vendor_reuse=args.vendor_reuse,
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
