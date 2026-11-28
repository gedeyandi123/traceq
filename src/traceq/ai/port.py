"""The LLM port (ADR 0004, ADR 0008): Mode Cloud and Mode Pabrik.

A request asks for one JSON object that follows ``schema``. Requests go in batches, so the
Mode Cloud adapter can send them through the Batch API; an adapter that sends one request at
a time (Mode Pabrik) says so by being ``OneAtATime``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, eq=False)
class Prompt:
    """A prompt template: its system text and the schema of the answer."""

    name: str
    system: str
    schema: Mapping[str, Any]
    max_tokens: int

    @property
    def hash(self) -> str:
        return sha256(json.dumps([self.system, self.schema, self.max_tokens], sort_keys=True))


@dataclass(frozen=True, eq=False)
class Request:
    prompt: Prompt
    user: str
    doc_sha256: str
    """Hash of the document the request reads: part of the recording key."""
    sample: int = 0
    """Which answer to the same request this is. The answer varies, so a request may be
    asked again (#88); each sample after the first has its own recording."""

    @property
    def input_hash(self) -> str:
        return sha256(json.dumps([self.prompt.hash, self.user], sort_keys=True))


@dataclass(frozen=True)
class Response:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class LLMError(RuntimeError):
    """The model gave no usable answer (refusal, truncation, failed request)."""


class LLM(Protocol):
    @property
    def model(self) -> str: ...

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        """One response per request, in request order."""
        ...


@dataclass(frozen=True)
class Sent:
    """One request answered on its own, with how the answer was got."""

    response: Response
    attempts: int
    """How many times the request was asked: an unusable answer is asked again."""
    latency_s: float
    """Seconds spent waiting for the endpoint over all attempts, pacing and back-off apart."""
    stripped: tuple[str, ...] = ()
    """What was stripped from the answer used before parsing (``think``, ``fence``)."""
    unusable: tuple[str, ...] = ()
    """The kind of each unusable answer before the one used, in order."""


@runtime_checkable
class OneAtATime(LLM, Protocol):
    """An LLM that sends one request at a time (no batch). A recorder then charges and saves
    each answer before the next request goes, so a failure loses at most the call in flight."""

    def send(self, request: Request) -> Sent: ...


@runtime_checkable
class Described(Protocol):
    """An adapter that reports how it ran, for the run metadata (never a secret)."""

    def describe(self) -> dict[str, Any]: ...
