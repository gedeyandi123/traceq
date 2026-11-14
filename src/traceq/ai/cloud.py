"""Mode Cloud adapter (ADR 0004): Claude through the Message Batches API.

Every request asks for structured output against its prompt's JSON schema. A batch is
polled until it ends; any request that did not succeed with a complete answer fails the
whole call, so nothing half-answered reaches the pipeline. Never called in CI.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Literal

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request as BatchRequest

from traceq.ai.port import LLMError, Request, Response

Effort = Literal["low", "medium", "high"]


class CloudLLM:
    def __init__(
        self,
        model: str,
        client: anthropic.Anthropic | None = None,
        effort: Effort = "low",
        poll_seconds: float = 30.0,
    ) -> None:
        self._model = model
        self.client = client or anthropic.Anthropic()
        self.effort: Effort = effort
        self.poll_seconds = poll_seconds

    @property
    def model(self) -> str:
        return self._model

    def _params(self, r: Request) -> MessageCreateParamsNonStreaming:
        return {
            "model": self._model,
            "max_tokens": r.prompt.max_tokens,
            "system": r.prompt.system,
            "messages": [{"role": "user", "content": r.user}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": dict(r.prompt.schema)},
            },
        }

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        if not requests:
            return []
        batch = self.client.messages.batches.create(
            requests=[
                BatchRequest(custom_id=str(i), params=self._params(r))
                for i, r in enumerate(requests)
            ]
        )
        while batch.processing_status != "ended":
            time.sleep(self.poll_seconds)
            batch = self.client.messages.batches.retrieve(batch.id)
        answers: dict[int, Response] = {}
        for item in self.client.messages.batches.results(batch.id):
            result = item.result
            if result.type != "succeeded":
                raise LLMError(f"batch {batch.id} request {item.custom_id}: {result.type}")
            msg = result.message
            if msg.stop_reason != "end_turn":
                raise LLMError(f"batch {batch.id} request {item.custom_id}: {msg.stop_reason}")
            text = next((b.text for b in msg.content if b.type == "text"), None)
            if text is None:
                raise LLMError(f"batch {batch.id} request {item.custom_id}: no text")
            answers[int(item.custom_id)] = Response(
                text=text,
                model=msg.model,
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
            )
        missing = [i for i in range(len(requests)) if i not in answers]
        if missing:
            raise LLMError(f"batch {batch.id}: no result for requests {missing}")
        return [answers[i] for i in range(len(requests))]
