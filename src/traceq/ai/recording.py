"""Record and replay of LLM calls (spec #29, "Recording, replay and cost").

A call is keyed by document hash + pipeline version + prompt hash, plus the model and the
request text, so two requests on the same document never share a recording. A recording
holds the request, the response, the tokens and the model. Without a live adapter every
call must already be recorded; with one, only the calls not yet recorded are sent, after the
budget has authorised them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traceq.ai.cost import Budget
from traceq.ai.port import LLM, Request, Response, sha256


class MissingRecording(LookupError):
    """Replay asked for a call nobody recorded."""


@dataclass(frozen=True)
class Call:
    request: Request
    response: Response
    replayed: bool


class Recorder:
    """An ``LLM`` that answers from recordings and records what ``live`` answers."""

    def __init__(
        self,
        store: Path,
        model: str,
        pipeline_version: str,
        live: LLM | None = None,
        budget: Budget | None = None,
    ) -> None:
        if live is not None and live.model != model:
            raise ValueError(f"live adapter runs {live.model}, recorder keys {model}")
        if live is not None and budget is None:
            raise ValueError("a live run needs a budget")
        self.store = store
        self._model = model
        self.pipeline_version = pipeline_version
        self.live = live
        self.budget = budget
        self.calls: list[Call] = []

    @property
    def model(self) -> str:
        return self._model

    def key(self, r: Request) -> str:
        return sha256(
            json.dumps(
                {
                    "doc": r.doc_sha256,
                    "pipeline": self.pipeline_version,
                    "prompt": r.prompt.hash,
                    "model": self._model,
                    "input": r.input_hash,
                },
                sort_keys=True,
            )
        )

    def _path(self, r: Request) -> Path:
        return self.store / f"{self.key(r)}.json"

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        found: dict[int, Response] = {}
        for i, r in enumerate(requests):
            path = self._path(r)
            if path.exists():
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                found[i] = Response(**data["response"])
        misses = [i for i in range(len(requests)) if i not in found]
        if misses and (self.live is None or self.budget is None):
            raise MissingRecording(
                f"{len(misses)} of {len(requests)} '{requests[misses[0]].prompt.name}' calls"
                f" are not recorded in {self.store} for {self._model}; run live to record them"
            )
        sent: dict[int, Response] = {}
        if misses and self.live is not None and self.budget is not None:
            batch = [requests[i] for i in misses]
            self.budget.authorise(self._model, batch)
            answers = self.live.complete(batch)
            self.budget.charge(answers)
            for i, a in zip(misses, answers, strict=True):
                sent[i] = a
                self._save(requests[i], a)
        out: list[Response] = []
        for i, r in enumerate(requests):
            response = found.get(i) or sent[i]
            self.calls.append(Call(r, response, replayed=i in found))
            out.append(response)
        return out

    def _save(self, r: Request, a: Response) -> None:
        self.store.mkdir(parents=True, exist_ok=True)
        record = {
            "key": self.key(r),
            "doc_sha256": r.doc_sha256,
            "pipeline_version": self.pipeline_version,
            "prompt": r.prompt.name,
            "prompt_hash": r.prompt.hash,
            "model": self._model,
            "request": {
                "system": r.prompt.system,
                "user": r.user,
                "schema": r.prompt.schema,
                "max_tokens": r.prompt.max_tokens,
            },
            "response": {
                "text": a.text,
                "model": a.model,
                "input_tokens": a.input_tokens,
                "output_tokens": a.output_tokens,
            },
        }
        text = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self._path(r).write_text(text, encoding="utf-8", newline="\n")
