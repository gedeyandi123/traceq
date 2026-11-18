"""One run: a released corpus in, a run folder out.

``<out>/<run id>/submission.json`` is what the scorer grades; ``matrix.json`` is the
traceability matrix with each Coverage reason and its Evidence; ``findings.json`` holds the
Pre-review Check Findings and, apart from them, the AI Findings pending review, the VMP's
required documents and those missing, and the site rules read from the SOP, each with its
citation; ``drafts.json`` holds the drafted IQ/OQ Test
Steps as AI Findings pending review; ``run.json`` is the run
metadata: the run settings, model, prompt hashes, tokens, cost in USD, which calls were
replayed, which claims the citation check dropped, the wall-clock duration with the time spent
waiting for live calls apart (0 for a replayed run), and per document read its ingest engine,
seconds per page and peak RAM; ``completeness.json`` is the URS completeness check (printed
requirement numbers that did not become a requirement, and URS text no requirement
quotes). Ingest output is cached in ``<recordings>/ingest`` beside the LLM recordings, so
a replay reads no document whose ingest is cached. Every scan is read by OCR before any LLM
call, so a run that cannot read one fails before it spends. A live run sends
only calls that are not yet recorded, and refuses before sending when their estimate would
pass ``max_usd``.

A run may take a released Review Package beside the corpus (spec #196). The Equipment
Pre-review then runs unchanged and replay-only, also in a live run: every call comes from
``recordings``, which is read and never written, and a call missing there fails the run
before anything is sent. Then the package's Protocol Draft is read (``traceq.review.draft``),
one call per page, with the draft prompt, whose hash enters the run's prompt set only in such
a run. The package's own recordings and ingest cache go to ``package_recordings``.
The draft rules (``traceq.review.draft_rules``) then decide its Check Findings.
``protocol_draft.json`` holds the draft's rows (Test Step, AC as read with its citation, the
URS limit of each traced requirement with its citation, the comparison or why it was not
compared, the comparators available), its traceability rows and its findings;
``submission.json`` names the package and carries the draft's Test Step rows and, after the
Equipment findings, the draft's findings; ``run.json`` names the package, its version, its
corpus release and the Equipment recordings replayed, and counts the draft's calls, tokens,
cost and Test Steps not compared (the run's totals include them). Without a package a run is
as above.

``vendor_reuse`` (default true) decides whether a ``covered_by_vendor`` requirement also
gets a drafted Test Step. Eval runs keep it true: scorer criterion 1 counts a step for a
``covered_by_vendor`` requirement as a failure (spec #29, "Vendor reuse framing").
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traceq.ai import LLM, Budget, PriceTable, Recorder
from traceq.ai.port import Request, Response, sha256
from traceq.documents import Corpus, IngestCache, Ingested, ReviewPackage
from traceq.protocols import PROMPTS as DRAFT_PROMPTS
from traceq.protocols import draft
from traceq.review import PROMPTS as REVIEW_PROMPTS
from traceq.review import review
from traceq.review.draft import DRAFT_PROMPT, DraftReading, DraftRow, draft_rows, read_draft
from traceq.review.draft_rules import DraftFinding, draft_findings
from traceq.runs.completeness import COMPLETENESS_FILE, completeness
from traceq.runs.drafts import drafts
from traceq.runs.findings import findings
from traceq.runs.matrix import matrix
from traceq.runs.protocol_draft import (
    DRAFT_FILE,
    draft_findings_out,
    draft_steps,
    protocol_draft,
)
from traceq.runs.submission import Submission, SystemInfo, build
from traceq.traceability import PIPELINE_VERSION, PROMPTS, Traceability, trace

SYSTEM_NAME = "traceq"
INGEST_DIR = "ingest"

Clock = Callable[[], float]
"""Seconds on a monotonic clock."""


@dataclass(frozen=True)
class RunOutput:
    folder: Path
    submission: Submission
    metadata: dict[str, Any]


class _Timed:
    """The live adapter, adding up the seconds spent waiting for it."""

    def __init__(self, live: LLM, clock: Clock) -> None:
        self._live = live
        self._clock = clock
        self.seconds = 0.0

    @property
    def model(self) -> str:
        return self._live.model

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        start = self._clock()
        try:
            return self._live.complete(requests)
        finally:
            self.seconds += self._clock() - start


@dataclass(frozen=True)
class _Draft:
    reading: DraftReading
    rows: list[DraftRow]
    findings: list[DraftFinding]
    ingested: Ingested


def _read_package(
    package: ReviewPackage, corpus: Corpus, traced: Traceability, llm: LLM, store: Path
) -> _Draft:
    """Read the package's Protocol Draft from a corpus of its own, after the Equipment
    stages: the draft never enters them. Its ingest goes to the package store."""
    if len(package.documents) != 1:
        raise ValueError(
            f"Review Package {package.package} holds {len(package.documents)} documents;"
            " one Protocol Draft is expected"
        )
    drafts = Corpus(
        root=package.root,
        equipment=corpus.equipment,
        documents=package.documents,
        cache=IngestCache(store / INGEST_DIR),
    )
    doc = package.documents[0]
    ingested = drafts.ingest(doc)
    reading = read_draft(doc, ingested.pages, llm)
    urs = corpus.current("urs")
    language = urs[0].language if urs else "en"
    rows = draft_rows(reading, traced, language)
    return _Draft(reading, rows, draft_findings(reading, rows), ingested)


def _write_json(path: Path, data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def run(
    corpus_dir: Path,
    out_dir: Path,
    recordings: Path,
    model: str,
    *,
    equipment: str | None = None,
    live: LLM | None = None,
    max_usd: float = 1.0,
    prices: PriceTable | None = None,
    now: dt.datetime | None = None,
    vendor_reuse: bool = True,
    clock: Clock = time.perf_counter,
    review_package: Path | None = None,
    package_recordings: Path | None = None,
) -> RunOutput:
    """``now``: the start time the run id and ``created`` carry. ``clock``: what the run's
    duration is measured with. ``review_package``: a released Review Package directory for
    this corpus and Equipment; its recordings and ingest cache go to ``package_recordings``,
    while ``recordings`` is only read and the Equipment stages only replay."""
    start = clock()
    prices = prices or PriceTable.load()
    now = now or dt.datetime.now(dt.UTC)
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    package: ReviewPackage | None = None
    store, reads = recordings, tuple[Path, ...]()
    if review_package is not None:
        if package_recordings is None or package_recordings.resolve() == recordings.resolve():
            raise ValueError(
                "a Review Package run needs package recordings apart from the Equipment"
                f" recordings {recordings}, which it only reads"
            )
        package = ReviewPackage.load(review_package)
        store, reads = package_recordings, (recordings,)
    corpus = Corpus.load(
        corpus_dir,
        equipment,
        cache=store / INGEST_DIR,
        cache_reads=tuple(r / INGEST_DIR for r in reads),
    )
    if package is not None:
        package.check_fits(corpus_dir, corpus.equipment)
    scans = [(d, corpus.read(d)) for d in corpus.documents if d.format == "scan"]
    budget = Budget(max_usd, prices) if live is not None else None
    timed = _Timed(live, clock) if live is not None else None
    llm = Recorder(store, model, PIPELINE_VERSION, live=timed, budget=budget, reads=reads)
    # In a Review Package run the Equipment Pre-review replays the Equipment run unchanged:
    # a call it lacks fails the run instead of being sent (spec #196).
    equipment_llm = llm.replay_only() if package is not None else llm

    traced = trace(corpus, equipment_llm)
    reviewed = review(corpus, equipment_llm, traced)
    drafted = draft(corpus, equipment_llm, traced, vendor_reuse=vendor_reuse)
    equipment_calls = len(llm.calls)
    on_draft = None if package is None else _read_package(package, corpus, traced, llm, store)

    prompt_hashes = {p.name: p.hash for p in (*PROMPTS, *REVIEW_PROMPTS, *DRAFT_PROMPTS)}
    if package is not None:
        # Only in a Review Package run, so an Equipment run's ``system.prompt`` is unchanged.
        prompt_hashes[DRAFT_PROMPT.name] = DRAFT_PROMPT.hash
    system = SystemInfo(
        name=SYSTEM_NAME,
        model=model,
        prompt=sha256(json.dumps(prompt_hashes, sort_keys=True))[:12],
        run_id=run_id,
    )
    submission = build(corpus.equipment, system, traced, reviewed, drafted, scans)
    if package is not None and on_draft is not None:
        submission = submission.model_copy(
            update={
                "review_package": package.package,
                "draft_steps": draft_steps(on_draft.rows),
                "findings": (*submission.findings, *draft_findings_out(on_draft.findings)),
            }
        )

    responses = [c.response for c in llm.calls]
    try:
        cost: float | None = round(prices.response_cost_usd(responses), 6)
    except KeyError:
        cost = None
    read = {c.request.doc_sha256 for c in llm.calls} | {d.sha256 for d, _ in corpus.ingested()}
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "created": now.isoformat(),
        "system": SYSTEM_NAME,
        "pipeline_version": PIPELINE_VERSION,
        "mode": "live" if live is not None else "replay",
        "settings": {"vendor_reuse": vendor_reuse},
        "model": model,
        "prompts": prompt_hashes,
        "corpus": {
            "equipment": corpus.equipment,
            "documents": [
                {"doc_id": d.doc_id, "rev": d.rev, "sha256": d.sha256}
                for d in corpus.documents
                if d.sha256 in read
            ],
        },
        "calls": {
            "total": len(llm.calls),
            "replayed": sum(c.replayed for c in llm.calls),
            "live": sum(not c.replayed for c in llm.calls),
        },
        "tokens": {
            "input": sum(r.input_tokens for r in responses),
            "output": sum(r.output_tokens for r in responses),
        },
        "cost_usd": cost,
        "live_cost_usd": round(budget.spent_usd, 6) if budget else 0.0,
        "max_usd": max_usd if live is not None else None,
        "price_table": {"batch_discount": prices.batch_discount},
        "dropped": [
            {"claim": d.claim, "id": d.id, "reason": d.reason}
            for d in (
                *traced.dropped,
                *reviewed.dropped,
                *drafted.dropped,
                *(on_draft.reading.dropped if on_draft else ()),
            )
        ],
        "ingest": [
            {
                "doc_id": d.doc_id,
                "rev": d.rev,
                "format": d.format,
                "engine": i.engine,
                "version": i.version,
                "cached": i.cached,
                "pages": len(i.pages),
                "seconds_per_page": list(i.seconds_per_page),
                "load_seconds": i.load_seconds,
                "peak_ram_bytes": i.peak_ram_bytes,
            }
            for d, i in corpus.ingested()
        ],
        "duration": {
            "total_seconds": round(clock() - start, 3),
            "live_seconds": round(timed.seconds, 3) if timed else 0.0,
        },
        "not_read": [
            {"doc_id": d.doc_id, "rev": d.rev, "format": d.format}
            for d in dict.fromkeys((*traced.vendor.not_read, *reviewed.not_read))
        ],
    }
    if package is not None and on_draft is not None:
        draft_calls = llm.calls[equipment_calls:]
        draft_responses = [c.response for c in draft_calls]
        try:
            draft_cost: float | None = round(prices.response_cost_usd(draft_responses), 6)
        except KeyError:
            draft_cost = None
        doc, i = on_draft.reading.doc, on_draft.ingested
        metadata["review_package"] = {
            "package": package.package,
            "version": package.version,
            "corpus": {"release": package.corpus_release, "version": package.corpus_version},
            "equipment_recordings": recordings.resolve().name,
            "document": {"doc_id": doc.doc_id, "rev": doc.rev, "sha256": doc.sha256},
            "calls": {
                "total": len(draft_calls),
                "replayed": sum(c.replayed for c in draft_calls),
                "live": sum(not c.replayed for c in draft_calls),
            },
            "tokens": {
                "input": sum(r.input_tokens for r in draft_responses),
                "output": sum(r.output_tokens for r in draft_responses),
            },
            "cost_usd": draft_cost,
            "test_steps": len(on_draft.rows),
            "trace_rows": len(on_draft.reading.rows),
            "not_compared": sum(r.not_compared is not None for r in on_draft.rows),
            "ingest": {
                "engine": i.engine,
                "version": i.version,
                "cached": i.cached,
                "pages": len(i.pages),
                "seconds_per_page": list(i.seconds_per_page),
                "peak_ram_bytes": i.peak_ram_bytes,
            },
        }

    folder = out_dir / run_id
    folder.mkdir(parents=True)
    _write_json(folder / "submission.json", submission.model_dump(mode="json", exclude_none=True))
    _write_json(folder / "matrix.json", matrix(traced).model_dump(mode="json"))
    _write_json(
        folder / "findings.json",
        findings(
            reviewed, model=model, prompt=prompt_hashes["ai_review"], created=metadata["created"]
        ).model_dump(mode="json"),
    )
    _write_json(
        folder / "drafts.json",
        drafts(drafted, model=model, prompt=prompt_hashes["draft"], created=metadata["created"]),
    )
    _write_json(folder / COMPLETENESS_FILE, completeness(traced).model_dump(mode="json"))
    if package is not None and on_draft is not None:
        _write_json(
            folder / DRAFT_FILE,
            protocol_draft(
                package.package, on_draft.reading, on_draft.rows, on_draft.findings
            ).model_dump(mode="json"),
        )
    _write_json(folder / "run.json", metadata)
    return RunOutput(folder, submission, metadata)
