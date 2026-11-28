"""Mode Pabrik adapter (spec #442, T1): an OpenAI-compatible chat endpoint behind the LLM port.

Every test talks to a fake endpoint through ``httpx.MockTransport``: no socket, no network.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from traceq.ai import (
    Budget,
    BudgetExceeded,
    Call,
    LLMError,
    PriceTable,
    Prompt,
    Recorder,
    Request,
    Response,
)
from traceq.ai.cost import Price
from traceq.ai.pabrik import API_KEY_ENV, PABRIK_MODEL, PabrikLLM
from traceq.app import cli
from traceq.runs import run as run_module
from traceq.runs.run import RunOutput

KEY = "fake-fake-fake-fake"  # a stand-in, never a real key
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["value"],
    "properties": {"value": {"type": "integer"}},
}
PROMPT = Prompt("extract", "You extract one value.", SCHEMA, max_tokens=500)
REQUEST = Request(PROMPT, "The value is 7.", "doc")

Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    """A clock that moves only when the adapter sleeps or the endpoint takes time."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _completion(
    content: str | None = '{"value": 7}',
    *,
    finish: str = "stop",
    model: str = PABRIK_MODEL,
    usage: bool = True,
    tool_args: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_args is not None:
        message["tool_calls"] = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "extract", "arguments": tool_args},
            }
        ]
    body: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 120, "completion_tokens": 8}
    return body


class Endpoint:
    """A fake OpenAI-compatible endpoint answering from a script, keeping what it was sent."""

    def __init__(self, *answers: dict[str, Any] | Handler, time: FakeTime | None = None) -> None:
        self.answers = list(answers)
        self.sent: list[httpx.Request] = []
        self.started: list[float] = []
        self.time = time

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.sent]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        if self.time is not None:
            self.started.append(self.time.now)
            self.time.now += 2.0  # every request takes two seconds
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if callable(answer):
            return answer(request)
        return httpx.Response(200, json=answer)


def _llm(endpoint: Endpoint, time: FakeTime | None = None, **kwargs: Any) -> PabrikLLM:
    time = time or endpoint.time or FakeTime()
    return PabrikLLM(
        api_key=KEY,
        transport=httpx.MockTransport(endpoint),
        sleep=time.sleep,
        clock=time.clock,
        **kwargs,
    )


# --- Request shape -----------------------------------------------------------------------


def test_a_request_asks_for_the_prompts_schema_greedy_and_without_thinking() -> None:
    endpoint = Endpoint(_completion())
    (response,) = _llm(endpoint).complete([REQUEST])

    (sent,) = endpoint.sent
    assert sent.method == "POST"
    assert str(sent.url) == "https://api.sea-lion.ai/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    body = endpoint.bodies[0]
    assert body["model"] == "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
    assert body["messages"] == [
        {"role": "system", "content": "You extract one value."},
        {"role": "user", "content": "The value is 7."},
    ]
    assert body["max_tokens"] == 500
    assert body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False, "thinking_mode": "off"}
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "extract", "schema": SCHEMA, "strict": True},
    }
    assert "tools" not in body
    assert response.text == '{"value": 7}'
    assert (response.input_tokens, response.output_tokens) == (120, 8)
    assert response.model == PABRIK_MODEL


def test_the_other_mechanism_forces_a_function_call_with_the_schema_as_parameters() -> None:
    endpoint = Endpoint(_completion(None, finish="tool_calls", tool_args='{"value": 7}'))
    (response,) = _llm(endpoint, structured_output="tool").complete([REQUEST])

    body = endpoint.bodies[0]
    assert "response_format" not in body
    (tool,) = body["tools"]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "extract"
    assert tool["function"]["parameters"] == SCHEMA
    assert body["tool_choice"] == {"type": "function", "function": {"name": "extract"}}
    assert response.text == '{"value": 7}'


def test_another_base_url() -> None:
    endpoint = Endpoint(_completion())
    _llm(endpoint, base_url="http://gpu.local:8000/v1").complete([REQUEST])
    assert str(endpoint.sent[0].url) == "http://gpu.local:8000/v1/chat/completions"


@pytest.mark.parametrize(
    ("choice", "sent"),
    [
        ("both", {"enable_thinking": False, "thinking_mode": "off"}),
        ("enable_thinking", {"enable_thinking": False}),
        ("thinking_mode", {"thinking_mode": "off"}),
        ("none", None),
    ],
)
def test_the_thinking_parameter_is_chosen_and_described(
    choice: str, sent: dict[str, Any] | None
) -> None:
    endpoint = Endpoint(_completion())
    llm = _llm(endpoint, thinking_param=choice)
    llm.complete([REQUEST])
    assert endpoint.bodies[0].get("chat_template_kwargs") == sent
    assert llm.describe()["parameters"] == {
        "temperature": 0,
        "thinking_param": choice,
        "chat_template_kwargs": sent,
    }


def test_a_refused_parameter_fails_with_the_endpoints_text() -> None:
    refusal = {"error": {"message": "Unknown parameter: chat_template_kwargs.thinking_mode"}}
    endpoint = Endpoint(lambda _: httpx.Response(400, json=refusal))
    with pytest.raises(LLMError, match=r"HTTP 400 .*Unknown parameter: chat_template_kwargs"):
        _llm(endpoint).send(REQUEST)


def test_the_answer_carries_the_configured_model_whatever_the_endpoint_names() -> None:
    endpoint = Endpoint(_completion(model="qwen-sealion-v4.5-27b-it-2611"))
    llm = _llm(endpoint)
    (response,) = llm.complete([REQUEST])
    assert response.model == PABRIK_MODEL
    assert llm.describe()["served_models"] == {"qwen-sealion-v4.5-27b-it-2611": 1}


def test_requests_are_sent_one_at_a_time_in_order() -> None:
    endpoint = Endpoint(_completion('{"value": 1}'), _completion('{"value": 2}'))
    second = Request(PROMPT, "The value is 2.", "doc")
    answers = _llm(endpoint).complete([REQUEST, second])
    assert [a.text for a in answers] == ['{"value": 1}', '{"value": 2}']
    assert [b["messages"][1]["content"] for b in endpoint.bodies] == [
        "The value is 7.",
        "The value is 2.",
    ]


def test_an_adapter_needs_a_key() -> None:
    with pytest.raises(ValueError, match="key"):
        PabrikLLM(api_key="")


# --- The format rule ---------------------------------------------------------------------

UNUSABLE: dict[str, dict[str, Any]] = {
    "truncated": _completion('{"value": ', finish="length"),
    "empty": _completion(""),
    "no content": _completion(None),
    "not JSON": _completion("The value is 7."),
    "schema violation": _completion('{"value": "seven"}'),
    "no usage": _completion(usage=False),
    "usage not counted": {
        **_completion(),
        "usage": {"prompt_tokens": True, "completion_tokens": 8},
    },
}


@pytest.mark.parametrize("kind", UNUSABLE)
def test_an_unusable_answer_is_asked_again(kind: str) -> None:
    endpoint = Endpoint(UNUSABLE[kind], _completion())
    sent = _llm(endpoint).send(REQUEST)
    assert sent.response.text == '{"value": 7}'
    assert sent.attempts == 2
    assert len(endpoint.sent) == 2
    assert endpoint.bodies[0] == endpoint.bodies[1]  # the same request, asked again


def test_a_forced_function_call_that_is_missing_is_unusable() -> None:
    endpoint = Endpoint(
        _completion('{"value": 7}', finish="stop"),
        _completion(None, finish="tool_calls", tool_args='{"value": 7}'),
    )
    llm = _llm(endpoint, structured_output="tool")
    assert llm.send(REQUEST).attempts == 2
    assert llm.describe()["unusable"] == {"no tool call": 1}


def test_an_answer_unusable_three_times_fails_naming_the_prompt_and_the_attempts() -> None:
    endpoint = Endpoint(_completion('{"value": "seven"}'))
    llm = _llm(endpoint)
    with pytest.raises(LLMError, match=r"'extract': no usable answer after 3 attempts"):
        llm.send(REQUEST)
    assert len(endpoint.sent) == 3
    assert llm.describe()["unusable"] == {"schema violation": 3}


def test_a_leading_think_block_and_a_code_fence_are_stripped_and_counted() -> None:
    endpoint = Endpoint(
        _completion('<think>\nThe page says 7.\n</think>\n\n{"value": 7}'),
        _completion('```json\n{"value": 8}\n```'),
    )
    llm = _llm(endpoint)
    second = Request(PROMPT, "The value is 8.", "doc")
    assert [a.text for a in llm.complete([REQUEST, second])] == ['{"value": 7}', '{"value": 8}']
    assert llm.describe()["stripped"] == {"think": 1, "fence": 1}


# --- Pacing, back-off and timeout --------------------------------------------------------


def test_requests_are_paced_under_ten_a_minute() -> None:
    time = FakeTime()
    endpoint = Endpoint(_completion(), time=time)
    _llm(endpoint).complete([REQUEST] * 3)
    gaps = [b - a for a, b in zip(endpoint.started, endpoint.started[1:], strict=False)]
    assert gaps == [6.5, 6.5]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_rate_limit_or_server_error_is_tried_again_after_a_back_off(status: int) -> None:
    time = FakeTime()
    endpoint = Endpoint(
        lambda _: httpx.Response(status, headers={"retry-after": "20"}, json={"error": "busy"}),
        _completion(),
        time=time,
    )
    llm = _llm(endpoint)
    sent = llm.send(REQUEST)
    assert sent.attempts == 1  # a transport retry is not another answer
    assert sent.latency_s == 4.0  # two requests of two seconds; the back-off is apart
    assert endpoint.started[1] - endpoint.started[0] == 22.0  # 2 s request + 20 s Retry-After
    assert llm.describe()["transport_retries"] == 1


def test_back_off_is_bounded_and_then_the_call_fails() -> None:
    time = FakeTime()
    endpoint = Endpoint(lambda _: httpx.Response(429, json={"error": "slow down"}), time=time)
    llm = _llm(endpoint, transport_retries=3)
    with pytest.raises(LLMError, match=r"'extract': HTTP 429 after 4 tries"):
        llm.send(REQUEST)
    assert len(endpoint.sent) == 4
    assert time.sleeps == [10.0, 20.0, 40.0]  # doubling back-off, at most 60 s


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("read timed out", request=request)


def test_a_timeout_is_tried_again() -> None:
    endpoint = Endpoint(_timeout, _completion())
    assert _llm(endpoint).send(REQUEST).response.text == '{"value": 7}'
    assert len(endpoint.sent) == 2


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.DecodingError])
def test_a_failed_request_is_tried_again(error: type[httpx.RequestError]) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error("failed", request=request)

    endpoint = Endpoint(fail, _completion())
    assert _llm(endpoint).send(REQUEST).response.text == '{"value": 7}'
    assert len(endpoint.sent) == 2


def test_a_call_that_keeps_timing_out_fails() -> None:
    endpoint = Endpoint(_timeout)
    with pytest.raises(LLMError, match=r"timed out after 30 s after 2 tries"):
        _llm(endpoint, timeout_s=30.0, transport_retries=1).send(REQUEST)


def test_a_client_error_fails_at_once_without_the_key() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        echoed = request.headers["authorization"]
        return httpx.Response(401, json={"error": f"invalid key {echoed}"})

    endpoint = Endpoint(refused)
    llm = _llm(endpoint)
    with pytest.raises(LLMError, match="HTTP 401") as raised:
        llm.send(REQUEST)
    assert len(endpoint.sent) == 1
    assert KEY not in str(raised.value)
    assert KEY not in json.dumps(llm.describe())
    assert KEY not in repr(llm)


# --- Recorded one at a time ---------------------------------------------------------------


def _budget(**kwargs: Any) -> Budget:
    return Budget(1.0, PriceTable.load(), **kwargs)


def _requests(n: int) -> list[Request]:
    return [Request(PROMPT, f"The value is {i}.", "doc") for i in range(n)]


def _answer(i: int) -> dict[str, Any]:
    return _completion(json.dumps({"value": i}))


def _records(store: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(store.glob("*.json"))]


def test_the_price_table_prices_the_trial_model_at_zero() -> None:
    table = PriceTable.load()
    assert table.cost_usd(PABRIK_MODEL, 1_000_000, 1_000_000) == 0.0
    assert table.estimate_usd(PABRIK_MODEL, _requests(3)) == 0.0
    assert _budget().authorise(PABRIK_MODEL, _requests(3)) == 0.0


def test_a_retried_call_is_recorded_once_under_its_key_with_attempts_and_latency(
    tmp_path: Path,
) -> None:
    time = FakeTime()
    endpoint = Endpoint(_completion('{"value": "seven"}'), _completion(), time=time)
    rec = Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=_budget())
    (response,) = rec.complete([REQUEST])
    assert response.text == '{"value": 7}'
    (record,) = _records(tmp_path)
    assert record["key"] == rec.key(REQUEST)
    assert "sample" not in record
    assert record["attempts"] == 2
    assert record["latency_s"] == 4.0
    assert record["model"] == PABRIK_MODEL
    assert record["response"]["model"] == PABRIK_MODEL
    assert record["unusable"] == ["schema violation"]
    assert record["stripped"] == []
    (call,) = rec.calls
    assert (call.replayed, call.attempts, call.latency_s) == (False, 2, 4.0)
    assert (call.unusable, call.stripped) == (("schema violation",), ())


def test_the_format_evidence_of_a_call_is_recorded_and_replayed(tmp_path: Path) -> None:
    """What was stripped from the answer used and why each earlier answer was unusable."""
    endpoint = Endpoint(
        _completion(usage=False),
        _completion('{"value": '),
        _completion('<think>\nseven\n</think>\n```json\n{"value": 7}\n```'),
    )
    live = Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=_budget())
    live.complete([REQUEST])
    (record,) = _records(tmp_path)
    assert record["attempts"] == 3
    assert record["unusable"] == ["no usage", "invalid JSON"]
    assert record["stripped"] == ["think", "fence"]

    replay = Recorder(tmp_path, PABRIK_MODEL, "1")
    replay.complete([REQUEST])
    (call,) = replay.calls
    assert (call.attempts, call.unusable, call.stripped) == (
        3,
        ("no usage", "invalid JSON"),
        ("think", "fence"),
    )


def test_a_fence_on_one_line_is_not_stripped_but_asked_again() -> None:
    endpoint = Endpoint(_completion('```json {"value": 7} ```'), _completion())
    sent = _llm(endpoint).send(REQUEST)
    assert (sent.attempts, sent.unusable, sent.stripped) == (2, ("invalid JSON",), ())


def test_answers_are_saved_under_the_configured_model_whatever_the_endpoint_names(
    tmp_path: Path,
) -> None:
    endpoint = Endpoint(_completion(model="some-served-name"))
    rec = Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=_budget())
    rec.complete([REQUEST])
    (record,) = _records(tmp_path)
    assert record["response"]["model"] == PABRIK_MODEL
    assert "some-served-name" not in json.dumps(record)


def test_each_answer_is_saved_before_the_next_is_sent(tmp_path: Path) -> None:
    """A failure on call 3 keeps calls 1 and 2."""
    endpoint = Endpoint(
        _answer(0), _answer(1), lambda _: httpx.Response(400, json={"error": "bad request"})
    )
    requests = _requests(4)
    rec = Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=_budget())
    with pytest.raises(LLMError, match="HTTP 400"):
        rec.complete(requests)
    assert len(endpoint.sent) == 3
    assert {r["key"] for r in _records(tmp_path)} == {rec.key(r) for r in requests[:2]}

    # Run again: the recorded calls replay and only the rest is sent.
    endpoint = Endpoint(_answer(2), _answer(3))
    rec = Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=_budget())
    assert [r.text for r in rec.complete(requests)] == [json.dumps({"value": i}) for i in range(4)]
    assert len(endpoint.sent) == 2
    assert [c.replayed for c in rec.calls] == [True, True, False, False]


def test_a_recorded_mode_pabrik_call_replays_with_no_live_call(tmp_path: Path) -> None:
    endpoint = Endpoint(_completion(), time=FakeTime())
    Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=_budget()).complete([REQUEST])
    replay = Recorder(tmp_path, PABRIK_MODEL, "1")
    (response,) = replay.complete([REQUEST])
    assert response.text == '{"value": 7}'
    assert response.model == PABRIK_MODEL
    (call,) = replay.calls
    assert (call.replayed, call.attempts, call.latency_s) == (True, 1, 2.0)
    assert len(endpoint.sent) == 1


def test_the_key_is_never_in_a_recording(tmp_path: Path) -> None:
    endpoint = Endpoint(_completion())
    Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=_budget()).complete([REQUEST])
    assert all(KEY not in p.read_text(encoding="utf-8") for p in tmp_path.rglob("*"))


def test_max_live_calls_refuses_before_the_call_that_would_pass_it(tmp_path: Path) -> None:
    endpoint = Endpoint(_answer(0), _answer(1), _answer(2))
    budget = _budget(max_calls=2)
    rec = Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint), budget=budget)
    with pytest.raises(BudgetExceeded, match="--max-live-calls 2"):
        rec.complete(_requests(3))
    assert len(endpoint.sent) == 2
    assert len(_records(tmp_path)) == 2


def test_the_deadline_stops_live_sending_once_it_has_passed(tmp_path: Path) -> None:
    """Checked before each call: the calls start at 0, 6.5 and 13 s and end 2 s later, so the
    fourth, asked at 15 s, is past the 10 s deadline and never sent."""
    time = FakeTime()
    endpoint = Endpoint(_completion(), time=time)
    budget = _budget(deadline_seconds=10.0, clock=time.clock)
    rec = Recorder(tmp_path, PABRIK_MODEL, "1", live=_llm(endpoint, time), budget=budget)
    with pytest.raises(LLMError, match="--deadline-minutes"):
        rec.complete(_requests(5))
    assert [t - endpoint.started[0] for t in endpoint.started] == [0.0, 6.5, 13.0]
    assert len(_records(tmp_path)) == 3


def test_the_deadline_stops_a_call_before_a_back_off_would_pass_it() -> None:
    """The first request ends at 2 s and its 20 s back-off ends at 22 s, under 30 s; the second
    ends at 24 s and a back-off to 44 s would pass 30 s, so the call stops without sleeping."""
    time = FakeTime()
    busy = httpx.Response(429, headers={"retry-after": "20"}, json={"error": "busy"})
    endpoint = Endpoint(lambda _: busy, time=time)
    llm = _llm(endpoint, deadline_seconds=30.0)
    with pytest.raises(LLMError, match=r"'extract': live sending would pass --deadline-minutes"):
        llm.send(REQUEST)
    assert len(endpoint.sent) == 2
    assert time.sleeps == [20.0]


def test_the_deadline_stops_an_answer_from_being_asked_again() -> None:
    """The unusable answer ends at 2 s; asking again after the pacing, at 6.5 s, passes 5 s."""
    time = FakeTime()
    endpoint = Endpoint(_completion("not JSON"), time=time)
    llm = _llm(endpoint, deadline_seconds=5.0)
    with pytest.raises(LLMError, match="--deadline-minutes"):
        llm.send(REQUEST)
    assert len(endpoint.sent) == 1
    assert time.sleeps == []


def test_a_batch_adapter_is_still_sent_its_calls_in_one_batch(tmp_path: Path) -> None:
    class Batch:
        model = "m"

        def __init__(self) -> None:
            self.batches: list[int] = []

        def complete(self, requests: Sequence[Request]) -> list[Response]:
            self.batches.append(len(requests))
            return [Response('{"value": 1}', "m", 1, 1) for _ in requests]

    batch = Batch()
    prices = PriceTable(batch_discount=0.5, models={"m": Price(1.0, 1.0)})
    rec = Recorder(tmp_path, "m", "1", live=batch, budget=Budget(1.0, prices))
    rec.complete(_requests(3))
    assert batch.batches == [3]
    extras = ("attempts", "latency_s", "stripped", "unusable")
    assert all(k not in r for r in _records(tmp_path) for k in extras)
    for calls in (rec.calls, _replayed(tmp_path, "m", _requests(3))):
        assert all(c.attempts is c.latency_s is c.stripped is c.unusable is None for c in calls)


def _replayed(store: Path, model: str, requests: list[Request]) -> list[Call]:
    replay = Recorder(store, model, "1")
    replay.complete(requests)
    return replay.calls


# --- traceq run --llm pabrik --------------------------------------------------------------


class _Ran:
    """``traceq.runs.run.run`` replaced: keeps what the CLI passed, or raises ``error``."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.args, self.kwargs = args, kwargs
        if self.error is not None:
            raise self.error
        metadata = {"calls": {"total": 0, "live": 0}, "cost_usd": 0.0, "dropped": []}
        return RunOutput(Path("runs/x"), cast(Any, _NoRequirements()), metadata)


class _NoRequirements:
    requirements: tuple[()] = ()


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> _Ran:
    fake = _Ran()
    monkeypatch.setattr(run_module, "run", fake)
    return fake


ARGV = ["run", "corpus", "--equipment", "TP-201"]


@pytest.mark.parametrize(
    ("llm", "model"), [("cloud", "claude-haiku-5-5"), ("pabrik", PABRIK_MODEL)]
)
def test_the_model_defaults_per_llm_so_replay_finds_its_recordings(
    ran: _Ran, llm: str, model: str
) -> None:
    assert cli.main([*ARGV, "--llm", llm]) == 0
    assert ran.args[3] == model
    assert ran.kwargs["live"] is None


def test_a_live_pabrik_run_sends_through_the_pabrik_adapter_with_its_brakes(
    ran: _Ran, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(API_KEY_ENV, KEY)
    argv = [*ARGV, "--llm", "pabrik", "--live", "--max-live-calls", "200"]
    assert cli.main([*argv, "--deadline-minutes", "40", "--structured-output", "tool"]) == 0
    live = ran.kwargs["live"]
    assert isinstance(live, PabrikLLM)
    assert live.model == ran.args[3] == PABRIK_MODEL
    assert live.structured_output == "tool"
    assert live.base_url == "https://api.sea-lion.ai/v1"
    assert live.thinking_param == "both"
    assert (ran.kwargs["max_live_calls"], ran.kwargs["deadline_seconds"]) == (200, 2400.0)
    assert live.deadline_seconds == 2400.0  # the adapter checks it too, before each retry


def test_a_live_pabrik_run_takes_another_base_url_and_model(
    ran: _Ran, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(API_KEY_ENV, KEY)
    argv = [*ARGV, "--llm", "pabrik", "--live", "--base-url", "http://gpu.local:8000/v1"]
    assert cli.main([*argv, "--model", "local-27b", "--thinking-param", "none"]) == 0
    live = ran.kwargs["live"]
    assert isinstance(live, PabrikLLM)
    assert (live.base_url, live.model, live.thinking_param) == (
        "http://gpu.local:8000/v1",
        "local-27b",
        "none",
    )
    assert live.deadline_seconds is None
    assert ran.args[3] == "local-27b"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["run", "corpus", "--llm", "pabrik", "--live"], "--equipment"),
        ([*ARGV, "--llm", "pabrik", "--live"], API_KEY_ENV),
        ([*ARGV, "--llm", "pabrik", "--max-live-calls", "5"], "--live"),
        ([*ARGV, "--llm", "pabrik", "--deadline-minutes", "5"], "--live"),
        ([*ARGV, "--llm", "pabrik", "--live", "--max-live-calls", "0"], "--max-live-calls"),
        ([*ARGV, "--llm", "pabrik", "--live", "--deadline-minutes", "0"], "--deadline-minutes"),
        ([*ARGV, "--base-url", "http://gpu.local:8000/v1"], "--llm pabrik"),
        ([*ARGV, "--structured-output", "tool"], "--llm pabrik"),
        ([*ARGV, "--thinking-param", "none"], "--llm pabrik"),
        ([*ARGV, "--live", "--max-live-calls", "5"], "--llm pabrik"),
        ([*ARGV, "--live", "--deadline-minutes", "5"], "--llm pabrik"),
    ],
)
def test_a_pabrik_run_is_refused_before_anything_runs(
    ran: _Ran,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    if message != API_KEY_ENV:
        monkeypatch.setenv(API_KEY_ENV, KEY)
    assert cli.main(argv) == 2
    assert message in capsys.readouterr().err
    assert ran.args == ()


def test_a_failed_llm_call_exits_2_with_its_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    error = LLMError("'extract': no usable answer after 3 attempts (invalid JSON)")
    monkeypatch.setattr(run_module, "run", _Ran(error))
    monkeypatch.setenv(API_KEY_ENV, KEY)
    assert cli.main([*ARGV, "--llm", "pabrik", "--live"]) == 2
    err = capsys.readouterr().err
    assert "no usable answer after 3 attempts" in err
    assert KEY not in err


def test_the_help_names_the_key_variable_and_the_deadlines_worst_case(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        cli.main(["run", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert API_KEY_ENV in out
    assert "overruns it by at most one HTTP request" in out
