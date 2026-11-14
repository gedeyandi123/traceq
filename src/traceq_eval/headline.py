"""Headline rates of a report (#74): the rates the eval screen shows, each with k/n.

A section counts k and n once (``Count``) and derives both its own metric and the headline
entry from that count, so the two cannot drift. Names are the ratchet's
(``traceq_eval.ratchet.RATCHETED``), and so is each metric's direction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, get_args

from traceq_eval.ratchet import RATCHETED

Metric = Literal[
    "requirements.value_accuracy",
    "citations.verified_rate",
    "defects.recall",
    "fabrication.rate",
    "probes.fabrication_rate",
    "ocr.exact_match_rate",
    "ocr.entry_recall",
    "ocr.cer",
]
HEADLINE: tuple[Metric, ...] = get_args(Metric)
"""The headline metrics, in the order the report and the eval screen list them."""

COUNTS = "_counts"
"""Private section key holding the section's ``Count`` per headline metric; ``score`` pops it."""


@dataclass(frozen=True)
class Count:
    k: int
    n: int

    @property
    def rate(self) -> float | None:
        """k / n to 4 places; ``None`` when n is 0, so an empty denominator is not a score."""
        return round(self.k / self.n, 4) if self.n else None


def headline(counts: Mapping[str, Count]) -> dict[str, dict[str, Any]]:
    """``{metric: {k, n, rate, better}}`` for every headline metric, in ``HEADLINE`` order."""
    better = dict(RATCHETED)
    return {
        m: {"k": counts[m].k, "n": counts[m].n, "rate": counts[m].rate, "better": str(better[m])}
        for m in HEADLINE
    }
