"""Mode Pabrik adapter (ADR 0004, spec #442): any OpenAI-compatible chat-completions endpoint.

The default is AI Singapore's hosted API serving Qwen-SEA-LION v4.5 27B; a self-hosted vLLM
server needs only another base URL. The prompt, its system text and its schema are the ones
Mode Cloud sends. Structured output is asked for in one of two ways, behind one switch: the
endpoint's JSON-schema response format (``json_schema``) or a forced function call whose
parameters are the prompt's schema (``tool``). Thinking is asked off and the temperature is 0
(greedy); what was sent is reported by ``describe()``, and a ``<think>`` block or a reasoning
field in an answer shows the endpoint ignored it.

Requests go one at a time (``OneAtATime``), paced under the provider's limit of 10 requests a
minute. HTTP 429, 5xx, a timeout or a failed connection is tried again after a bounded
back-off; any other HTTP error fails the call. An answer is unusable when it did not stop
normally (e.g. ``length``), is empty, lacks the forced function call, is not JSON, breaks the
prompt's schema or carries no token usage. A leading ``<think>...</think>`` block or one code
fence around the answer is stripped before parsing, and counted. An unusable answer is asked
again at most ``FORMAT_RETRIES`` times under the same request, so the recording key never
changes; still unusable, the call fails with ``LLMError``.

The key is sent only in the ``Authorization`` header: it is never logged, recorded, described
or put in an error text. Never called in CI.
"""

from __future__ import annotations

import contextlib
import email.utils
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, cast

import httpx
from jsonschema.validators import validator_for

from traceq.ai.port import LLMError, Request, Response, Sent

PABRIK_BASE_URL = "https://api.sea-lion.ai/v1"
PABRIK_MODEL = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
API_KEY_ENV = "TRACEQ_PABRIK_API_KEY"
"""The environment variable holding the endpoint's key."""

FORMAT_RETRIES = 2
"""How many times an unusable answer is asked again."""

THINKING_OFF: Mapping[str, Any] = {
    # Both chat-template conventions: Qwen3's ``enable_thinking`` and the SEA-LION reasoning
    # models' ``thinking_mode``. A template reads the one it knows.
    "chat_template_kwargs": {"enable_thinking": False, "thinking_mode": "off"},
}

StructuredOutput = Literal["json_schema", "tool"]

_THINK = re.compile(r"\A\s*<think>.*?</think>\s*", re.DOTALL)
_FENCE = re.compile(r"\A\s*```[A-Za-z]*[ \t]*\r?\n(.*?)\r?\n?```\s*\Z", re.DOTALL)


class _Unusable(Exception):
    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


def _obj(value: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _list(value: Any) -> list[Any] | None:
    return cast(list[Any], value) if isinstance(value, list) else None


class PabrikLLM:
    def __init__(
        self,
        model: str = PABRIK_MODEL,
        *,
        api_key: str,
        base_url: str = PABRIK_BASE_URL,
        structured_output: StructuredOutput = "json_schema",
        thinking_off: Mapping[str, Any] | None = THINKING_OFF,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 300.0,
        min_interval_s: float = 6.5,
        transport_retries: int = 4,
        backoff_s: float = 10.0,
        max_backoff_s: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """``min_interval_s``: the least time between the starts of two requests (6.5 s keeps
        under 10 a minute). ``transport_retries``: how many times a request that met HTTP 429,
        5xx, a timeout or a failed connection is sent again before the call fails."""
        if not api_key:
            raise ValueError(f"Mode Pabrik needs the endpoint's key in {API_KEY_ENV}")
        self._model = model
        self._key = api_key
        self.base_url = base_url
        self.structured_output: StructuredOutput = structured_output
        self.thinking_off = dict(thinking_off) if thinking_off is not None else None
        self.timeout_s = timeout_s
        self.min_interval_s = min_interval_s
        self.transport_retries = transport_retries
        self.backoff_s = backoff_s
        self.max_backoff_s = max_backoff_s
        self._sleep = sleep
        self._clock = clock
        self._client = httpx.Client(
            base_url=base_url,
            transport=transport,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._last_start: float | None = None
        self._served: Counter[str] = Counter()
        self._stripped: Counter[str] = Counter({"think": 0, "fence": 0})
        self._unusable: Counter[str] = Counter()
        self._reasoning = 0
        self._http_requests = 0
        self._transport_retries = 0

    @property
    def model(self) -> str:
        return self._model

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        return [self.send(r).response for r in requests]

    def send(self, request: Request) -> Sent:
        name = request.prompt.name
        body = self._body(request)
        latency = 0.0
        problems: list[str] = []
        attempts = FORMAT_RETRIES + 1
        for attempt in range(1, attempts + 1):
            answer, seconds = self._post(name, body)
            latency += seconds
            try:
                text, input_tokens, output_tokens = self._usable(request, answer)
            except _Unusable as e:
                self._unusable[e.kind] += 1
                problems.append(str(e))
                continue
            return Sent(
                Response(text, self._model, input_tokens, output_tokens),
                attempts=attempt,
                latency_s=round(latency, 3),
            )
        raise LLMError(
            self._scrub(
                f"'{name}': no usable answer after {attempts} attempts ({'; '.join(problems)})"
            )
        )

    def describe(self) -> dict[str, Any]:
        """How the run asked and what came back, for the run metadata. Never the key."""
        return {
            "adapter": "pabrik",
            "base_url": self.base_url,
            "model": self._model,
            "structured_output": self.structured_output,
            "parameters": {"temperature": 0, "thinking_off": self.thinking_off},
            "served_models": dict(self._served),
            "stripped": dict(self._stripped),
            "reasoning_returned": self._reasoning,
            "unusable": dict(self._unusable),
            "http_requests": self._http_requests,
            "transport_retries": self._transport_retries,
        }

    def _body(self, r: Request) -> dict[str, Any]:
        schema = dict(r.prompt.schema)
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": r.prompt.system},
                {"role": "user", "content": r.user},
            ],
            "max_tokens": r.prompt.max_tokens,
            "temperature": 0,
            **(self.thinking_off or {}),
        }
        if self.structured_output == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": r.prompt.name, "schema": schema, "strict": True},
            }
        else:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": r.prompt.name,
                        "description": "Give the answer as the arguments of this function.",
                        "parameters": schema,
                    },
                }
            ]
            body["tool_choice"] = {"type": "function", "function": {"name": r.prompt.name}}
        return body

    def _pace(self) -> None:
        if self._last_start is not None:
            wait = self._last_start + self.min_interval_s - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_start = self._clock()

    def _backoff(self, retry: int, response: httpx.Response | None) -> float:
        delay = min(self.max_backoff_s, self.backoff_s * 2**retry)
        after = response.headers.get("retry-after") if response is not None else None
        if after is not None:
            try:
                delay = float(after)
            except ValueError:
                # An unreadable Retry-After leaves the doubling back-off.
                with contextlib.suppress(TypeError, ValueError):
                    delay = email.utils.parsedate_to_datetime(after).timestamp() - time.time()
            delay = min(self.max_backoff_s, max(0.0, delay))
        return delay

    def _post(self, name: str, body: dict[str, Any]) -> tuple[Any, float]:
        """The endpoint's answer to one request, as parsed JSON (``None`` when the body is no
        JSON), and the seconds spent waiting for it."""
        seconds = 0.0
        tries = self.transport_retries + 1
        retry = 0
        while True:
            self._pace()
            self._http_requests += 1
            start = self._clock()
            response: httpx.Response | None = None
            try:
                response = self._client.post("chat/completions", json=body)
                problem = f"HTTP {response.status_code}"
            except httpx.TimeoutException:
                problem = f"timed out after {self.timeout_s:g} s"
            except httpx.TransportError as e:
                problem = f"connection failed ({type(e).__name__})"
            finally:
                seconds += self._clock() - start
            if response is not None:
                code = response.status_code
                if code == 200:
                    try:
                        return response.json(), seconds
                    except ValueError:
                        return None, seconds
                if code != 429 and code < 500:
                    text = response.text[:300]
                    raise LLMError(
                        self._scrub(f"'{name}': HTTP {code} from {self.base_url}: {text}")
                    )
            if retry + 1 >= tries:
                raise LLMError(self._scrub(f"'{name}': {problem} after {tries} tries"))
            self._transport_retries += 1
            self._sleep(self._backoff(retry, response))
            retry += 1

    def _usable(self, r: Request, answer: Any) -> tuple[str, int, int]:
        body = _obj(answer)
        if body is None:
            raise _Unusable("not a JSON object")
        choices = _list(body.get("choices"))
        choice = _obj(choices[0]) if choices else None
        if choice is None:
            raise _Unusable("no choice")
        message = _obj(choice.get("message")) or {}
        finish = choice.get("finish_reason")
        normal = {"stop"} if self.structured_output == "json_schema" else {"stop", "tool_calls"}
        if finish not in normal:
            raise _Unusable("finish reason", repr(finish))
        if message.get("reasoning_content") or message.get("reasoning"):
            self._reasoning += 1
        text: Any
        if self.structured_output == "tool":
            calls = _list(message.get("tool_calls"))
            call = _obj(calls[0]) if calls else None
            function = _obj(call.get("function")) if call else None
            if function is None:
                raise _Unusable("no tool call")
            text = function.get("arguments")
            if isinstance(text, dict):
                text = json.dumps(text, ensure_ascii=False)
        else:
            text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise _Unusable("empty content")
        text = self._strip(text)
        try:
            value = json.loads(text)
        except ValueError:
            raise _Unusable("invalid JSON") from None
        schema = dict(r.prompt.schema)
        error = next(iter(validator_for(schema)(schema).iter_errors(value)), None)
        if error is not None:
            raise _Unusable("schema violation", error.message[:160])
        usage = _obj(body.get("usage"))
        tokens = (usage or {}).get("prompt_tokens"), (usage or {}).get("completion_tokens")
        if not all(isinstance(t, int) for t in tokens):
            raise _Unusable("no usage")
        served = body.get("model")
        self._served[served if isinstance(served, str) else "(none)"] += 1
        return text, cast(int, tokens[0]), cast(int, tokens[1])

    def _strip(self, text: str) -> str:
        think = _THINK.match(text)
        if think is not None:
            self._stripped["think"] += 1
            text = text[think.end() :]
        fence = _FENCE.match(text)
        if fence is not None:
            self._stripped["fence"] += 1
            text = fence.group(1)
        return text

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "***")
