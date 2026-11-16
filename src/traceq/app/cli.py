"""``traceq run``: analyse a released corpus into a run folder.

Usage::

    traceq run CORPUS_DIR [--equipment TAG] [--out runs] [--recordings recordings]
        [--model claude-haiku-5-5] [--live] [--max-usd 1] [--no-vendor-reuse]
    traceq serve [--runs runs] [--corpus CORPUS_DIR] [--host 127.0.0.1] [--port 8000]
        [--issuer URL --database URL [--audience traceq] [--role-claim roles]]
    traceq demo-issuer [--port 9000] [--audience traceq] [--role-claim roles]
    traceq demo CORPUS_DIR --equipment TAG [--recordings recordings/haiku-r7] [--runs runs-demo]

Without ``--live`` every LLM call is replayed from ``--recordings`` and nothing is sent.
With ``--live``, calls not yet recorded go to Mode Cloud through the Batch API and are
recorded; the run refuses before sending when their estimated cost would pass
``--max-usd``. Exit code 0 on success, 2 when a recording is missing, the budget refuses,
a scan is neither cached nor readable (OCR model not installed) or the corpus is unusable.

``--no-vendor-reuse`` drafts a Test Step for every requirement, also those the vendor
covered, for the "could be saved by reuse" framing. Eval runs keep the default
(``vendor_reuse`` true), which scorer criterion 1 assumes.

``traceq serve`` starts the API over the run folders in ``--runs``; ``--corpus`` is the
released corpus they read, so a citation opens its page. Without ``--issuer`` and
``--database`` it is read-only and every database route answers 401; with both, a token of
that issuer opens the database routes (``--database``: a SQLAlchemy URL connecting as the
application role). It refuses to start with only one of the two.

``traceq demo-issuer`` starts the demo OIDC issuer on ``http://127.0.0.1:PORT`` (never
another interface): demo identities without a password, for the demo only.

``traceq demo CORPUS_DIR --equipment TAG`` brings the demo to a known state and, run
again, resets it: Postgres (Docker Compose), the database recreated and migrated, the
committed recordings of the dev Equipment replayed (no LLM call), the demo issuer and the API
started, the run imported as a persona. ``CORPUS_DIR`` is the extracted corpus release 0.1.0;
without it the command refuses.
It stays in the foreground until Ctrl-C, which stops the issuer and the API (Postgres stays).
"""

from __future__ import annotations

import argparse
import sys
import time
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
    s.add_argument("--issuer", help="trusted OIDC issuer URL, as its tokens name it")
    s.add_argument("--audience", default="traceq", help="what a token must be issued for")
    s.add_argument("--role-claim", default="roles", help="the claim holding the roles")
    s.add_argument("--database", help="database URL, connecting as the application role")
    i = commands.add_parser(
        "demo-issuer", help="start the demo OIDC issuer (demo identities, local machine only)"
    )
    i.add_argument("--port", type=int, default=9000)
    i.add_argument("--audience", default="traceq")
    i.add_argument("--role-claim", default="roles")
    d = commands.add_parser("demo", help="set up (or reset) the demo: database, run, issuer, API")
    d.add_argument("corpus", type=Path, help="the extracted corpus release 0.1.0")
    d.add_argument("--equipment", required=True, help="the dev Equipment to replay and import")
    d.add_argument("--recordings", type=Path, default=Path("recordings/haiku-r7"))
    d.add_argument("--runs", type=Path, default=Path("runs-demo"))
    d.add_argument("--issuer-port", type=int, default=9000)
    d.add_argument("--api-port", type=int, default=8000)
    d.add_argument(
        "--no-compose", action="store_true", help="Postgres already runs; skip Docker Compose"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.command == "demo-issuer":
        import uvicorn

        from traceq.identity.issuer import create_issuer

        url = f"http://127.0.0.1:{args.port}"
        app = create_issuer(url, audience=args.audience, role_claim=args.role_claim)
        uvicorn.run(app, host="127.0.0.1", port=args.port)
        return 0

    if args.command == "demo":
        return _demo(args)

    if args.command == "serve":
        import uvicorn

        from traceq.app.api import create_app
        from traceq.identity import IdentitySettings

        identity = (
            None
            if args.issuer is None
            else IdentitySettings(
                issuer=args.issuer, audience=args.audience, role_claim=args.role_claim
            )
        )
        try:
            app = create_app(args.runs, args.corpus, identity=identity, database=args.database)
        except ValueError as e:
            print(f"traceq serve: {e}", file=sys.stderr)
            return 2
        uvicorn.run(app, host=args.host, port=args.port)
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


def _demo(args: argparse.Namespace) -> int:
    from traceq.app.demo import DemoError, DemoSettings, bring_up

    settings = DemoSettings(
        corpus=args.corpus,
        equipment=args.equipment,
        recordings=args.recordings,
        runs=args.runs,
        issuer_port=args.issuer_port,
        api_port=args.api_port,
        compose=not args.no_compose,
    )
    try:
        demo = bring_up(settings, log=lambda msg: print(f"traceq demo: {msg}", flush=True))
    except DemoError as e:
        print(f"traceq demo: {e}", file=sys.stderr)
        return 2
    print(
        f"traceq demo: ready. Postgres 127.0.0.1:5432, issuer {demo.issuer_url}, API"
        f" {demo.api_url} (run {demo.run_id} imported). Start the web UI with"
        " `cd web && npm run dev`. Ctrl-C stops the issuer and the API.",
        flush=True,
    )
    try:
        while demo.api.poll() is None and demo.issuer.poll() is None:
            time.sleep(0.5)
        print("traceq demo: a process stopped; stopping the demo", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        demo.stop()


if __name__ == "__main__":
    sys.exit(main())
