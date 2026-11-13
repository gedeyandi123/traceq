"""Cost in USD from the price table, and the ``--max-usd`` budget of a live run.

The estimate before sending is an upper bound: input tokens are counted as one per
``CHARS_PER_TOKEN`` characters (real tokenisers average more characters per token) and every
request is assumed to use its whole ``max_tokens``.
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from traceq.ai.port import Request, Response

CHARS_PER_TOKEN = 3


class BudgetExceeded(RuntimeError):
    """A live call was refused before sending: its estimate would pass ``--max-usd``."""


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float


@dataclass(frozen=True)
class PriceTable:
    batch_discount: float
    models: Mapping[str, Price]

    @classmethod
    def load(cls, text: str | None = None) -> PriceTable:
        if text is None:
            text = files("traceq.ai").joinpath("prices.toml").read_text(encoding="utf-8")
        data: dict[str, Any] = tomllib.loads(text)
        models: dict[str, dict[str, float]] = data["models"]
        return cls(
            batch_discount=float(data["batch_discount"]),
            models={m: Price(p["input_per_mtok"], p["output_per_mtok"]) for m, p in models.items()},
        )

    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Batch API cost of the tokens."""
        if model not in self.models:
            raise KeyError(f"no price for model {model!r} in the price table")
        p = self.models[model]
        list_price = (input_tokens * p.input_per_mtok + output_tokens * p.output_per_mtok) / 1e6
        return list_price * self.batch_discount

    def response_cost_usd(self, responses: Sequence[Response]) -> float:
        return sum(self.cost_usd(r.model, r.input_tokens, r.output_tokens) for r in responses)

    def estimate_usd(self, model: str, requests: Sequence[Request]) -> float:
        inp = sum(
            math.ceil(len(r.prompt.system + r.user + str(r.prompt.schema)) / CHARS_PER_TOKEN)
            for r in requests
        )
        out = sum(r.prompt.max_tokens for r in requests)
        return self.cost_usd(model, inp, out)


class Budget:
    """What a live run may spend. Checked before every send; actual cost counted after."""

    def __init__(self, max_usd: float, prices: PriceTable) -> None:
        self.max_usd = max_usd
        self.prices = prices
        self.spent_usd = 0.0

    def authorise(self, model: str, requests: Sequence[Request]) -> float:
        try:
            estimate = self.prices.estimate_usd(model, requests)
        except KeyError as e:
            raise BudgetExceeded(f"cannot estimate the cost: {e.args[0]}") from None
        if self.spent_usd + estimate > self.max_usd:
            raise BudgetExceeded(
                f"{len(requests)} live calls estimated at ${estimate:.4f}"
                f" (spent ${self.spent_usd:.4f}) would pass --max-usd {self.max_usd}"
            )
        return estimate

    def charge(self, responses: Sequence[Response]) -> None:
        self.spent_usd += self.prices.response_cost_usd(responses)
