"""One run: a released corpus in, a run folder out.

``<out>/<run id>/submission.json`` is what the scorer grades; ``matrix.json`` is the
traceability matrix with each Coverage reason and its Evidence; ``findings.json`` holds the
Pre-review Check Findings, the VMP's required documents and those missing, and the site rules
read from the SOP, each with its citation; ``drafts.json`` holds the drafted IQ/OQ Test
Steps as AI Findings pending review; ``run.json`` is the run
metadata: the run settings, model, prompt hashes, tokens, cost in USD, which calls were
replayed, which claims the citation check dropped, and per document read its ingest engine,
seconds per page and peak RAM. Ingest output is cached in ``<recordings>/ingest`` beside the LLM
recordings, so a replay reads no document whose ingest is cached. Every scan is read by OCR
before any LLM call, so a run that cannot read one fails before it spends. A live run sends
only calls that are not yet recorded, and refuses before sending when their estimate would
pass ``max_usd``.

``vendor_reuse`` (default true) decides whether a ``covered_by_vendor`` requirement also
gets a drafted Test Step. Eval runs keep it true: scorer criterion 1 counts a step for a
``covered_by_vendor`` requirement as a failure (spec #29, "Vendor reuse framing").
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traceq.ai import LLM, Budget, PriceTable, Recorder
from traceq.ai.port import sha256
from traceq.documents import Corpus
from traceq.protocols import PROMPTS as DRAFT_PROMPTS
from traceq.protocols import draft
from traceq.review import PROMPTS as REVIEW_PROMPTS
from traceq.review import review
from traceq.runs.drafts import drafts
from traceq.runs.findings import findings
from traceq.runs.matrix import matrix
from traceq.runs.submission import Submission, SystemInfo, build
from traceq.traceability import PIPELINE_VERSION, PROMPTS, trace

SYSTEM_NAME = "traceq"
INGEST_DIR = "ingest"


@dataclass(frozen=True)
class RunOutput:
    folder: Path
    submission: Submission
    metadata: dict[str, Any]


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
) -> RunOutput:
    prices = prices or PriceTable.load()
    now = now or dt.datetime.now(dt.UTC)
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    corpus = Corpus.load(corpus_dir, equipment, cache=recordings / INGEST_DIR)
    scans = [(d, corpus.read(d)) for d in corpus.documents if d.format == "scan"]
    budget = Budget(max_usd, prices) if live is not None else None
    llm = Recorder(recordings, model, PIPELINE_VERSION, live=live, budget=budget)

    traced = trace(corpus, llm)
    reviewed = review(corpus, llm, traced)
    drafted = draft(corpus, llm, traced, vendor_reuse=vendor_reuse)

    prompt_hashes = {p.name: p.hash for p in (*PROMPTS, *REVIEW_PROMPTS, *DRAFT_PROMPTS)}
    system = SystemInfo(
        name=SYSTEM_NAME,
        model=model,
        prompt=sha256(json.dumps(prompt_hashes, sort_keys=True))[:12],
        run_id=run_id,
    )
    submission = build(corpus.equipment, system, traced, reviewed, drafted, scans)

    responses = [c.response for c in llm.calls]
    try:
        cost: float | None = round(prices.response_cost_usd(responses), 6)
    except KeyError:
        cost = None
    read = {(c.request.doc_sha256) for c in llm.calls}
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
            for d in (*traced.dropped, *reviewed.dropped, *drafted.dropped)
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
        "not_read": [
            {"doc_id": d.doc_id, "rev": d.rev, "format": d.format}
            for d in dict.fromkeys((*traced.vendor.not_read, *reviewed.not_read))
        ],
    }

    folder = out_dir / run_id
    folder.mkdir(parents=True)
    _write_json(folder / "submission.json", submission.model_dump(mode="json", exclude_none=True))
    _write_json(folder / "matrix.json", matrix(traced).model_dump(mode="json"))
    _write_json(folder / "findings.json", findings(reviewed))
    _write_json(
        folder / "drafts.json",
        drafts(drafted, model=model, prompt=prompt_hashes["draft"], created=metadata["created"]),
    )
    _write_json(folder / "run.json", metadata)
    return RunOutput(folder, submission, metadata)
