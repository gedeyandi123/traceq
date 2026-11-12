"""LLM-judged criteria of a drafted Test Step (design section 9, criteria 3–5).

v0 defines the interface only. A judge sees the drafted step and the requirement as printed
in the URS (id, sentence, value): never the answer key, which is not sent to an LLM (design
section 6). It returns a binary verdict with a written critique, or ``None`` when it does
not score that criterion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from traceq_eval.submission import TestStep


class Criterion(StrEnum):
    LIMITS = "limits_or_worst_case"
    """3: tests upper/lower limits or the worst case (CPOB 12.29b)."""
    INSTRUMENT = "names_instrument"
    """4: names the measuring instrument."""
    EXECUTABLE = "executable_method"
    """5: the method is executable."""


@dataclass(frozen=True)
class UrsRequirement:
    """What a judge may know about a requirement: the URS sentence, nothing derived."""

    id: str
    text: str
    value: dict[str, Any]


@dataclass(frozen=True)
class JudgeVerdict:
    passed: bool
    critique: str


class Judge(Protocol):
    name: str

    def judge(
        self, step: TestStep, requirement: UrsRequirement | None, criterion: Criterion
    ) -> JudgeVerdict | None: ...


class NoJudge:
    """The v0 default: every judged criterion is reported as not scored."""

    name = "none"

    def judge(
        self, step: TestStep, requirement: UrsRequirement | None, criterion: Criterion
    ) -> JudgeVerdict | None:
        return None
