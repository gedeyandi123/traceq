"""``traceq run``: analyse a released corpus into a run folder.

Usage::

    traceq run CORPUS_DIR [--equipment TAG] [--out runs] [--recordings recordings]
        [--model claude-haiku-5-5] [--llm cloud|no-llm] [--live] [--max-usd 1]
        [--no-vendor-reuse]
        [--review-package PACKAGE_DIR --package-recordings DIR [--draft-rev N]]
    traceq serve [--runs runs] [--corpus CORPUS_DIR] [--host 127.0.0.1] [--port 8000]
        [--issuer URL --database URL [--audience traceq] [--role-claim roles]]
        [--uploads DIR --upload-equipment TAG --recordings DIR --package-recordings DIR
            [--model M] [--upload-budget-usd 0]]
    traceq demo-issuer [--port 9000] [--audience traceq] [--role-claim roles]

Without ``--live`` every LLM call is replayed from ``--recordings`` and nothing is sent.
With ``--live``, calls not yet recorded go to Mode Cloud through the Batch API and are
recorded; the run refuses before sending when their estimated cost would pass
``--max-usd``. Exit code 0 on success, 2 when a recording is missing, the budget refuses,
a scan is neither cached nor readable (OCR model not installed) or the corpus is unusable.

``--review-package`` takes a released Review Package for the corpus and Equipment: the
Equipment calls replay from ``--recordings``, which is read and never written, and are never
sent, also with ``--live``; the package's calls and ingest are recorded in
``--package-recordings``. A package holds several revisions of its draft; ``--draft-rev`` picks
one (the latest by default) and exactly one document of that revision is read.

``--llm no-llm`` runs the No-LLM Baseline (#193) instead of the model: every prompt is
answered by rules over the request text, from the ingest cache in ``--recordings``, with no
LLM call and no recording. Its model is ``no-llm-v1``; it cannot be combined with ``--live``
or ``--review-package`` (exit code 2). The demo and ``traceq serve`` never use it.

``--no-vendor-reuse`` drafts a Test Step for every requirement, also those the vendor
covered, for the "could be saved by reuse" framing. Eval runs keep the default
(``vendor_reuse`` true), which scorer criterion 1 assumes.

``traceq serve`` starts the API over the run folders in ``--runs``; ``--corpus`` is the
released corpus they read, so a citation opens its page. Without ``--issuer`` and
``--database`` it is read-only and every database route answers 401; with both, a token of
that issuer opens the database routes (``--database``: a SQLAlchemy URL connecting as the
application role). It refuses to start with only one of the two.

``--uploads DIR`` (with ``--corpus``, ``--upload-equipment``, ``--recordings`` and
``--package-recordings``) turns on the browser upload of a Protocol Draft for that Equipment
and runs the one upload worker inside the server. Uploaded files and packages are kept in DIR.
``--upload-budget-usd`` is the ceiling of live spend over all uploads: with 0 (the default)
nothing is ever sent, and an upload is accepted only when every page of its draft already has a
recording as the revision it would become (the prompt names the revision). Above 0 the Mode
Cloud adapter reads a revision with no recording, within the ceiling.

``traceq demo-issuer`` starts the demo OIDC issuer on ``http://127.0.0.1:PORT`` (never
another interface): demo identities without a password, for the demo only.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from traceq.ai import LLM, BudgetExceeded, MissingRecording
from traceq.documents import OcrUnavailable

DEFAULT_MODEL = "claude-haiku-5-5"


UPLOAD_BATCH_DEADLINE_SECONDS = 1800.0
"""How long a live batch of an upload may run before it is cancelled and the job fails."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traceq")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("run", help="analyse a released corpus into a run folder")
    p.add_argument("corpus", type=Path, help="corpus directory holding manifest.json")
    p.add_argument("--equipment")
    p.add_argument("--out", type=Path, default=Path("runs"))
    p.add_argument("--recordings", type=Path, default=Path("recordings"))
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument(
        "--llm",
        choices=("cloud", "no-llm"),
        default="cloud",
        help="cloud: the model, replayed or live; no-llm: the No-LLM Baseline, rules only",
    )
    p.add_argument("--live", action="store_true", help="send unrecorded calls to the API")
    p.add_argument("--max-usd", type=float, default=1.0)
    p.add_argument(
        "--review-package",
        type=Path,
        help="released Review Package directory; the Equipment calls then only replay",
    )
    p.add_argument(
        "--package-recordings",
        type=Path,
        help="where a Review Package run records (--recordings is then only read)",
    )
    p.add_argument(
        "--draft-rev",
        type=int,
        help="the revision of the Review Package's draft to read (default: the latest)",
    )
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
    s.add_argument("--uploads", type=Path, help="directory for uploaded drafts; turns uploads on")
    s.add_argument("--upload-equipment", help="the one Equipment uploads are accepted for")
    s.add_argument("--recordings", type=Path, default=Path("recordings"))
    s.add_argument("--package-recordings", type=Path, help="recordings and ingest of drafts")
    s.add_argument("--model", default=DEFAULT_MODEL)
    s.add_argument("--upload-budget-usd", type=float, default=0.0)
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
        from traceq.uploads.runner import MAX_BUDGET_USD

        if not math.isfinite(args.upload_budget_usd) or not (
            0 <= args.upload_budget_usd <= MAX_BUDGET_USD
        ):
            print(
                f"traceq serve: --upload-budget-usd must be a finite number from 0 to"
                f" {MAX_BUDGET_USD:g}",
                file=sys.stderr,
            )
            return 2
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
        uploads = None
        if args.uploads is not None:
            if (
                args.corpus is None
                or args.upload_equipment is None
                or args.package_recordings is None
            ):
                print(
                    "traceq serve: --uploads needs --corpus, --upload-equipment and"
                    " --package-recordings",
                    file=sys.stderr,
                )
                return 2
            from traceq.uploads import UploadSettings

            def _cloud() -> LLM:
                from traceq.ai.cloud import CloudLLM

                return CloudLLM(args.model, deadline_seconds=UPLOAD_BATCH_DEADLINE_SECONDS)

            uploads = UploadSettings(
                equipment=args.upload_equipment,
                store=args.uploads,
                corpus=args.corpus,
                recordings=args.recordings,
                package_recordings=args.package_recordings,
                model=args.model,
                budget_usd=args.upload_budget_usd,
                live=_cloud if args.upload_budget_usd > 0 else None,
            )
        try:
            app = create_app(
                args.runs,
                args.corpus,
                identity=identity,
                database=args.database,
                uploads=uploads,
                run_worker=uploads is not None,
            )
        except ValueError as e:
            print(f"traceq serve: {e}", file=sys.stderr)
            return 2
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    from traceq.runs.run import run

    model = args.model
    answers = None
    if args.llm == "no-llm":
        if args.live:
            print("traceq run: --llm no-llm makes no LLM calls; drop --live", file=sys.stderr)
            return 2
        from traceq.runs.no_llm import NoLLM

        answers = NoLLM()
        model = answers.model
    live = None
    if args.live:
        from traceq.ai.cloud import CloudLLM

        live = CloudLLM(args.model)
    try:
        out = run(
            args.corpus,
            args.out,
            args.recordings,
            model,
            equipment=args.equipment,
            live=live,
            max_usd=args.max_usd,
            vendor_reuse=args.vendor_reuse,
            review_package=args.review_package,
            draft_rev=args.draft_rev,
            package_recordings=args.package_recordings,
            answers=answers,
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
