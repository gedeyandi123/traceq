"""``traceq run``: analyse a released corpus into a run folder.

Usage::

    traceq run CORPUS_DIR [--equipment TAG] [--out runs] [--recordings recordings]
        [--model M] [--llm cloud|pabrik|no-llm] [--live] [--max-usd 1]
        [--max-live-calls N] [--deadline-minutes M] [--no-vendor-reuse]
        [--base-url URL] [--structured-output json_schema|tool]
        [--thinking-param both|enable_thinking|thinking_mode|none]
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

``--llm pabrik`` runs Mode Pabrik (ADR 0004, spec #442): an OpenAI-compatible chat endpoint,
by default AI Singapore's hosted API (``--base-url https://api.sea-lion.ai/v1``) and the model
``aisingapore/Qwen-SEA-LION-v4.5-27B-IT``. ``--model`` defaults per ``--llm``
(``claude-haiku-5-5`` for Mode Cloud), so a replay finds the recordings of its mode. Without
``--live`` it replays like Mode Cloud; with ``--live`` it needs ``--equipment`` and the
endpoint's key in the environment variable ``TRACEQ_PABRIK_API_KEY`` (never logged, recorded
or printed), and sends calls one at a time, each recorded as soon as it is answered.
``--structured-output`` picks how the schema is asked for (the endpoint's JSON-schema response
format with ``strict: true``, or as the fallback a forced function call); ``--thinking-param``
picks which chat-template parameter asks thinking off (``both`` by default, ``none`` for an
endpoint that refuses them; the run metadata records what was sent). A live run that fails, or
stops at a brake, resumes when the same command is run again: recorded calls replay and only
the rest is sent. ``traceq serve`` and uploads stay Mode Cloud only.

``--max-live-calls N`` refuses the live call that would pass N; ``--deadline-minutes M`` stops
live sending once M minutes have passed since the first live call. Both brake Mode Pabrik,
whose model is priced at 0, beside ``--max-usd``, and need ``--llm pabrik --live``. The
deadline is checked before every HTTP request and every back-off, so a run overruns it by at
most one HTTP request in flight (its timeout is 300 s per phase: connect, write, read). A
failed LLM call (an answer still unusable after it was asked again, an HTTP error with the
endpoint's text, a brake) exits with code 2 and its message.

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

from traceq.ai import LLM, BudgetExceeded, LLMError, MissingRecording
from traceq.ai.pabrik_settings import API_KEY_ENV as PABRIK_KEY_ENV
from traceq.ai.pabrik_settings import (
    PABRIK_BASE_URL,
    PABRIK_MODEL,
    STRUCTURED_OUTPUTS,
    THINKING_PARAMS,
)
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
    p.add_argument(
        "--model",
        help=f"default per --llm: {DEFAULT_MODEL} (cloud), {PABRIK_MODEL} (pabrik)",
    )
    p.add_argument(
        "--llm",
        choices=("cloud", "pabrik", "no-llm"),
        default="cloud",
        help="cloud: Mode Cloud, replayed or live; pabrik: Mode Pabrik, an OpenAI-compatible"
        f" endpoint, replayed or live (key in {PABRIK_KEY_ENV}); no-llm: the No-LLM Baseline,"
        " rules only",
    )
    p.add_argument("--live", action="store_true", help="send unrecorded calls to the API")
    p.add_argument("--max-usd", type=float, default=1.0)
    p.add_argument(
        "--max-live-calls",
        type=int,
        help="Mode Pabrik: refuse the live call that would pass this many (needs --live)",
    )
    p.add_argument(
        "--deadline-minutes",
        type=float,
        help="Mode Pabrik: stop live sending this many minutes after the first live call"
        " (needs --live); checked before every HTTP request and back-off, so a run overruns it"
        " by at most one HTTP request in flight (timeout 300 s per phase)",
    )
    p.add_argument(
        "--base-url",
        help=f"Mode Pabrik: the OpenAI-compatible endpoint (default {PABRIK_BASE_URL})",
    )
    p.add_argument(
        "--structured-output",
        choices=STRUCTURED_OUTPUTS,
        help="Mode Pabrik: ask for the schema as a JSON-schema response format, strict"
        " (default), or as the fallback a forced function call",
    )
    p.add_argument(
        "--thinking-param",
        choices=tuple(THINKING_PARAMS),
        help="Mode Pabrik: the chat-template parameter that asks thinking off (default both;"
        " none for an endpoint that refuses them)",
    )
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
    s.add_argument(
        "--review-package",
        type=Path,
        help="released Review Package directory for opening its Protocol Draft PDF",
    )
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
                review_package=args.review_package,
            )
        except ValueError as e:
            print(f"traceq serve: {e}", file=sys.stderr)
            return 2
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    from traceq.runs.run import run

    def refuse(message: str) -> int:
        print(f"traceq run: {message}", file=sys.stderr)
        return 2

    brakes = args.max_live_calls is not None or args.deadline_minutes is not None
    pabrik_only = brakes or any(
        v is not None for v in (args.base_url, args.structured_output, args.thinking_param)
    )
    if pabrik_only and args.llm != "pabrik":
        return refuse(
            "--base-url, --structured-output, --thinking-param, --max-live-calls and"
            " --deadline-minutes need --llm pabrik"
        )
    if brakes and not args.live:
        return refuse("--max-live-calls and --deadline-minutes brake a live run: add --live")
    if args.max_live_calls is not None and args.max_live_calls < 1:
        return refuse("--max-live-calls must be at least 1")
    if args.deadline_minutes is not None and not (
        math.isfinite(args.deadline_minutes) and args.deadline_minutes > 0
    ):
        return refuse("--deadline-minutes must be a finite number above 0")
    model = args.model or (PABRIK_MODEL if args.llm == "pabrik" else DEFAULT_MODEL)
    deadline_seconds = None if args.deadline_minutes is None else args.deadline_minutes * 60
    answers = None
    if args.llm == "no-llm":
        if args.live:
            print("traceq run: --llm no-llm makes no LLM calls; drop --live", file=sys.stderr)
            return 2
        from traceq.runs.no_llm import NoLLM

        answers = NoLLM()
        model = answers.model
    live: LLM | None = None
    if args.live and args.llm == "pabrik":
        import os

        if args.equipment is None:
            return refuse("--llm pabrik --live needs --equipment (one Equipment per live run)")
        key = os.environ.get(PABRIK_KEY_ENV, "")
        if not key:
            return refuse(f"--llm pabrik --live needs the endpoint's key in {PABRIK_KEY_ENV}")
        from traceq.ai.pabrik import PabrikLLM

        live = PabrikLLM(
            model,
            api_key=key,
            base_url=args.base_url or PABRIK_BASE_URL,
            structured_output=args.structured_output or "json_schema",
            thinking_param=args.thinking_param or "both",
            deadline_seconds=deadline_seconds,
        )
    elif args.live:
        from traceq.ai.cloud import CloudLLM

        live = CloudLLM(model)
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
            max_live_calls=args.max_live_calls,
            deadline_seconds=deadline_seconds,
        )
    except (
        MissingRecording,
        BudgetExceeded,
        LLMError,
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
