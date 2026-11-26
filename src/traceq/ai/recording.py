"""Record and replay of LLM calls (spec #29, "Recording, replay and cost").

A call is keyed by document hash + pipeline version + prompt hash, plus the model and the
request text, so two requests on the same document never share a recording. A request asked
again carries a sample index, which enters the key only when it is not 0: the first answer
keeps the key it always had. A recording
holds the request, the response, the tokens and the model. Without a live adapter every
call must already be recorded; with one, only the calls not yet recorded are sent, after the
budget has authorised them.

A recorder writes to one store, ``store``, and also reads the stores in ``reads``, which it
never writes: a Review Package run writes the package's recordings and replays the Equipment
run's (spec #196). ``replay_only()`` answers only from the stores in ``reads``, never from
``store``, into the same call log and never sends: the Equipment stages of a Review Package run
replay from the Equipment run's recordings alone, and a miss fails before anything is sent,
also when the recorder has a live adapter.
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
        reads: Sequence[Path] = (),
    ) -> None:
        if live is not None and live.model != model:
            raise ValueError(f"live adapter runs {live.model}, recorder keys {model}")
        if live is not None and budget is None:
            raise ValueError("a live run needs a budget")
        self.store = store
        self.reads = tuple(reads)
        self._model = model
        self.pipeline_version = pipeline_version
        self.live = live
        self.budget = budget
        self.calls: list[Call] = []

    @property
    def model(self) -> str:
        return self._model

    def stage(self, pipeline_version: str) -> Recorder:
        """This recorder keyed on another pipeline version: a stage with a version of its own.
        Same stores, live adapter and budget, and the same call log, so one run counts every
        call and its cost."""
        other = Recorder(
            self.store,
            self._model,
            pipeline_version,
            live=self.live,
            budget=self.budget,
            reads=self.reads,
        )
        other.calls = self.calls
        return other

    def key(self, r: Request) -> str:
        fields: dict[str, Any] = {
            "doc": r.doc_sha256,
            "pipeline": self.pipeline_version,
            "prompt": r.prompt.hash,
            "model": self._model,
            "input": r.input_hash,
        }
        if r.sample:
            fields["sample"] = r.sample
        return sha256(json.dumps(fields, sort_keys=True))

    def _path(self, r: Request) -> Path:
        return self.store / f"{self.key(r)}.json"

    def _recorded(self, r: Request, stores: Sequence[Path]) -> Response | None:
        name = f"{self.key(r)}.json"
        for store in stores:
            path = store / name
            if path.exists():
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                return Response(**data["response"])
        return None

    def replay_only(self) -> LLM:
        """This recorder without its live adapter and its written store: it answers from the
        stores it reads only, into the same call log."""
        return _ReplayOnly(self)

    def complete(self, requests: Sequence[Request], *, send: bool = True) -> list[Response]:
        """``send`` false: only the stores in ``reads`` answer, and a call not recorded there
        fails, even with a live adapter."""
        stores = (self.store, *self.reads) if send else self.reads
        found: dict[int, Response] = {}
        for i, r in enumerate(requests):
            response = self._recorded(r, stores)
            if response is not None:
                found[i] = response
        misses = [i for i in range(len(requests)) if i not in found]
        if misses and (not send or self.live is None or self.budget is None):
            where = ", ".join(str(s) for s in stores) or "no store"
            hint = "run live to record them" if send else "replay only: they are never sent"
            raise MissingRecording(
                f"{len(misses)} of {len(requests)} '{requests[misses[0]].prompt.name}' calls"
                f" are not recorded in {where} for {self._model}; {hint}"
            )
        sent: dict[int, Response] = {}
        if misses and send and self.live is not None and self.budget is not None:
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
        record: dict[str, Any] = {
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
        if r.sample:
            record["sample"] = r.sample
        text = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self._path(r).write_text(text, encoding="utf-8", newline="\n")


class _ReplayOnly:
    """A recorder's view that answers from its stores and never sends."""

    def __init__(self, recorder: Recorder) -> None:
        self._recorder = recorder

    @property
    def model(self) -> str:
        return self._recorder.model

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        return self._recorder.complete(requests, send=False)
