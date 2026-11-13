"""The LLM port (ADR 0004, ADR 0008): Mode Cloud now, Mode Pabrik later.

A request asks for one JSON object that follows ``schema``. Requests go in batches, so the
Mode Cloud adapter can send them through the Batch API.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


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
