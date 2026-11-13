"""Deterministic units of the system: citation check, cost and budget, recording keys, and
the module boundaries (ADR 0008)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import pytest
from importlinter.cli import lint_imports

from traceq.ai import Budget, BudgetExceeded, MissingRecording, PriceTable, Recorder
from traceq.ai.cost import CHARS_PER_TOKEN, Price
from traceq.ai.port import Prompt, Request, Response
from traceq.traceability.citations import (
    Citation,
    number_forms,
    quote_on_page,
    value_in_quote,
    verified,
)
from traceq.traceability.values import Number, OneOf, Present, Range, Text

ROOT = Path(__file__).parents[1]
PAGE = (
    "No. Kritis Persyaratan\nX-01 Ya Kapasitas minimal 100.000 tablet/jam.\nX-02 Tidak Ra ≤ 0,8 µm"
)

# --- Citation check -------------------------------------------------------------------


def test_quote_must_be_printed_on_the_page() -> None:
    assert quote_on_page("Kapasitas  minimal\n100.000 tablet/jam.", PAGE)
    assert not quote_on_page("Kapasitas minimal 120.000 tablet/jam.", PAGE)
    assert not quote_on_page("", PAGE)
    assert not quote_on_page("x" * 201, "x" * 300)


def test_number_forms() -> None:
    assert {"100000", "100.000", "100,000"} <= number_forms(100000)
    assert {"0.8", "0,8"} <= number_forms(0.8)
    assert "1.234,5" in number_forms(1234.5)


def test_value_must_be_stated_by_the_quote() -> None:
    q = "Kapasitas minimal 100.000 tablet/jam."
    assert value_in_quote(Range(min=100000, unit="tablets/h"), q)
    assert not value_in_quote(Range(min=100, unit="tablets/h"), q)
    assert value_in_quote(Number(value=0.8, unit="µm"), "Ra ≤ 0,8 µm")
    assert not value_in_quote(Number(value=36, unit="st"), "360 stations")
    assert value_in_quote(OneOf(allowed=("SS 316L",)), "terbuat dari SS 316L.")
    assert not value_in_quote(Text(value="EU D"), "tooling tipe EU B")
    assert value_in_quote(Present(), "anything")


def test_verified_checks_page_quote_and_value() -> None:
    c = Citation("X", 0, 1, "Kapasitas minimal 100.000 tablet/jam.")
    assert verified(c, [PAGE], Range(min=100000, unit="tablets/h"))
    assert not verified(c, [PAGE], Range(min=120000, unit="tablets/h"))
    assert not verified(Citation("X", 0, 2, c.quote), [PAGE])
    assert not verified(Citation("X", 0, 0, c.quote), [PAGE])


# --- Cost and budget ------------------------------------------------------------------

PROMPT = Prompt("p", "system", {"type": "object"}, max_tokens=1000)
PRICES = PriceTable(batch_discount=0.5, models={"m": Price(2.0, 10.0)})


def test_price_table_ships_with_the_default_model() -> None:
    table = PriceTable.load()
    assert "claude-haiku-5-5" in table.models
    assert table.batch_discount == 0.5


def test_cost_applies_the_batch_discount() -> None:
    assert PRICES.cost_usd("m", 1_000_000, 100_000) == pytest.approx((2.0 + 1.0) * 0.5)
    with pytest.raises(KeyError):
        PRICES.cost_usd("other", 1, 1)


def test_estimate_is_an_upper_bound_on_tokens() -> None:
    r = Request(PROMPT, "u" * 300, "doc")
    chars = len("system" + "u" * 300 + str(PROMPT.schema))
    inp = math.ceil(chars / CHARS_PER_TOKEN)
    assert PRICES.estimate_usd("m", [r]) == pytest.approx(PRICES.cost_usd("m", inp, 1000))


def test_budget_refuses_when_the_estimate_passes_the_limit() -> None:
    reqs = [Request(PROMPT, "u", "doc")] * 10
    estimate = PRICES.estimate_usd("m", reqs)
    Budget(estimate, PRICES).authorise("m", reqs)
    budget = Budget(estimate * 1.5, PRICES)
    budget.spent_usd = estimate
    with pytest.raises(BudgetExceeded):
        budget.authorise("m", reqs)


# --- Record and replay ----------------------------------------------------------------


class Echo:
    model = "m"

    def __init__(self) -> None:
        self.sent: list[Request] = []

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.sent += requests
        return [Response(r.user, "m", 10, 5) for r in requests]


def test_recording_key_covers_document_pipeline_prompt_and_request(tmp_path: Path) -> None:
    rec = Recorder(tmp_path, "m", "1")
    base = Request(PROMPT, "u", "doc")
    other_prompt = Prompt("p", "system 2", {"type": "object"}, max_tokens=1000)
    keys = {
        rec.key(base),
        rec.key(Request(PROMPT, "u", "doc2")),
        rec.key(Request(PROMPT, "v", "doc")),
        rec.key(Request(other_prompt, "u", "doc")),
        Recorder(tmp_path, "m", "2").key(base),
        Recorder(tmp_path, "m2", "1").key(base),
    }
    assert len(keys) == 6
    assert rec.key(Request(PROMPT, "u", "doc")) == rec.key(base)


def test_recorder_sends_only_unrecorded_calls(tmp_path: Path) -> None:
    echo = Echo()
    live = Recorder(tmp_path, "m", "1", live=echo, budget=Budget(1.0, PRICES))
    a, b = Request(PROMPT, "a", "d"), Request(PROMPT, "b", "d")
    assert [r.text for r in live.complete([a])] == ["a"]
    assert [r.text for r in live.complete([a, b])] == ["a", "b"]
    assert [r.user for r in echo.sent] == ["a", "b"]
    assert [c.replayed for c in live.calls] == [False, True, False]

    replay = Recorder(tmp_path, "m", "1")
    assert [r.text for r in replay.complete([b, a])] == ["b", "a"]
    with pytest.raises(MissingRecording):
        replay.complete([Request(PROMPT, "c", "d")])


# --- Module boundaries ----------------------------------------------------------------


def test_import_linter_contracts_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    assert lint_imports(config_filename=str(ROOT / "pyproject.toml"), no_logo=True) == 0
