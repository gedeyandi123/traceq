"""Coverage by the decision table (design section 6): deterministic over extracted facts.

The LLM proposes which vendor test steps and design facts concern a requirement and judges
two properties of the requirement (whether only the site can test it, and whether transport
or installation can affect it); this module decides the class. Order of evaluation, as in
the answer key:

1. A design fact (datasheet row, certificate) that does not meet the URS -> ``conflict``.
2. The requirement cannot be tested by the vendor -> ``site_only``.
3. No step can test the URS value -> ``gap``. A step whose observation cannot be compared
   with the URS value (a document check offered for a material) is no Evidence.
4. ``covered_by_vendor`` only if a step meets all four conditions of the decision table;
   otherwise ``partial``, with the first failing condition of each step as the reason.

A step proves nothing when its result does not meet the URS, is recorded as a fail, or reads
two ways (the ambiguity rule: ask for confirmation, never guess). A date that reads two ways
fails condition 2 for the same reason.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from traceq.documents import normalise
from traceq.traceability.ambiguity import Ambiguous
from traceq.traceability.values import Number, OneOf, Present, Range, Text, Value

CoverageClass = Literal["covered_by_vendor", "partial", "site_only", "gap", "conflict"]
Stage = Literal["FAT", "SAT"]
Result = Literal["pass", "fail"]
Observed = Value | Ambiguous[float]
Date = dt.date | Ambiguous[dt.date] | None


@dataclass(frozen=True)
class VendorAssessment:
    """The site's Vendor Assessment: the areas of vendor activity whose results it relies on,
    as printed (``traceability.assessment``)."""

    scope: frozenset[str]


@dataclass(frozen=True)
class Protocol:
    """A vendor FAT/SAT protocol and report."""

    doc: str
    rev: int
    stage: Stage
    site_approved_on: Date
    executed_on: Date


@dataclass(frozen=True)
class Step:
    protocol: Protocol
    step: str
    observed: Observed | None
    result: Result | None


@dataclass(frozen=True)
class DesignFact:
    """A value the design or the delivered item states: a datasheet row, a certificate."""

    doc: str
    rev: int
    value: Value


@dataclass(frozen=True)
class RequirementFacts:
    id: str
    value: Value | None
    """The verified URS value, or ``None`` when none was verified."""
    site_only: bool
    transport_sensitive: bool
    scope: str | None = None
    """The Vendor Assessment area the requirement belongs to, ``None`` when none is named."""


@dataclass(frozen=True)
class StepVerdict:
    step: Step
    failure: str | None
    """The first failing condition, or ``None`` when the step meets conditions 1-3."""


@dataclass(frozen=True)
class Coverage:
    coverage: CoverageClass
    reason: str
    verdicts: tuple[StepVerdict, ...] = ()
    """Every step that is Evidence for the requirement, with its verdict."""
    design: tuple[DesignFact, ...] = ()
    """The design facts compared with the URS value."""

    @property
    def evidence(self) -> tuple[Step, ...]:
        return tuple(v.step for v in self.verdicts)

    @property
    def ambiguous(self) -> tuple[Step, ...]:
        return tuple(v.step for v in self.verdicts if isinstance(v.step.observed, Ambiguous))


# --- Comparing values --------------------------------------------------------------------


def _same_unit(a: str, b: str) -> bool:
    return normalise(a).casefold() == normalise(b).casefold()


def _same_text(a: str, b: str) -> bool:
    return normalise(a).casefold() == normalise(b).casefold()


def comparable(spec: Value, observed: Observed) -> bool:
    """Whether the observation says anything about the URS value."""
    match spec, observed:
        case Range() | Number(), Ambiguous():
            return True
        case Range(unit=u) | Number(unit=u), Range(unit=v) | Number(unit=v):
            return _same_unit(u, v)
        case OneOf() | Text(), Text() | OneOf():
            return True
        case Present(), Present():
            return True
        case _:
            return False


def meets(spec: Value, observed: Value) -> bool:
    """Does an observed value satisfy the URS value? Call only when ``comparable``. A range
    (a design range or a sweep) meets it when it spans the whole URS range."""
    match spec, observed:
        case Range(), Range():
            return covers_full_range(spec, observed)
        case Range(min=lo, max=hi), Number(value=x):
            return (lo is None or x >= lo) and (hi is None or x <= hi)
        case Number(value=x), Number(value=y):
            return x == y
        case Number(value=x), Range(min=lo, max=hi):
            return lo == hi == x
        case OneOf(allowed=allowed) | Text(value=allowed), Text(value=v):
            options = (allowed,) if isinstance(allowed, str) else allowed
            return any(_same_text(o, v) for o in options)
        case OneOf(allowed=allowed) | Text(value=allowed), OneOf(allowed=values):
            options = (allowed,) if isinstance(allowed, str) else allowed
            return all(any(_same_text(o, v) for o in options) for v in values)
        case Present(), Present(value=v):
            return v is True
        case _:
            return False


def covers_full_range(spec: Value, observed: Value) -> bool:
    """Decision-table condition 3: was the whole URS range exercised?"""
    match spec, observed:
        case Range(min=lo, max=hi), Range(min=olo, max=ohi):
            return (lo is None or (olo is not None and olo <= lo)) and (
                hi is None or (ohi is not None and ohi >= hi)
            )
        case Range(min=lo, max=hi), Number():
            # One reading proves a one-sided limit or a fixed value, not a span.
            return lo is None or hi is None or lo == hi
        case _:
            return True


# --- The decision table ------------------------------------------------------------------


def _proves(spec: Value, step: Step) -> bool:
    observed = step.observed
    if step.result == "fail" or observed is None or isinstance(observed, Ambiguous):
        return False
    if isinstance(observed, Range):
        # A sweep is recorded against its own AC; the span is condition 3.
        return step.result == "pass"
    return meets(spec, observed)


def _approved_before_execution(p: Protocol) -> bool | None:
    """``None`` when a date reads two ways."""
    if isinstance(p.site_approved_on, Ambiguous) or isinstance(p.executed_on, Ambiguous):
        return None
    if p.site_approved_on is None or p.executed_on is None:
        return False
    return p.site_approved_on <= p.executed_on


def step_failure(
    req: RequirementFacts, step: Step, assessment: VendorAssessment | None
) -> str | None:
    """The first failing condition of one step, in the order of the decision table."""
    if req.value is None:
        return "URS value not verified"
    if isinstance(step.observed, Ambiguous):
        # Not proof until a human confirms which reading was meant (#53).
        return "value awaits confirmation"
    if not _proves(req.value, step):
        return "result does not meet the URS"
    if assessment is None:
        return "condition 1: no Vendor Assessment"
    if req.scope is None:
        return "condition 1: no assessed area named"
    if req.scope not in assessment.scope:
        return f"condition 1: scope {req.scope!r} not in vendor assessment"
    approved = _approved_before_execution(step.protocol)
    if approved is None:
        return "condition 2: date ambiguous, ask for confirmation"
    if not approved:
        return "condition 2: protocol not approved by site before execution (CPOB 12.14)"
    assert step.observed is not None
    if not covers_full_range(req.value, step.observed):
        return "condition 3: full URS range not tested"
    return None


def classify(
    req: RequirementFacts,
    steps: Iterable[Step],
    design: Iterable[DesignFact],
    assessment: VendorAssessment | None,
) -> Coverage:
    """Apply the decision table to one requirement and the facts linked to it."""
    value = req.value
    compared = tuple(d for d in design if value is not None and comparable(value, d.value))
    for fact in compared:
        assert value is not None
        if not meets(value, fact.value):
            return Coverage("conflict", f"{fact.doc} does not meet the URS", design=compared)

    evidence = [
        s
        for s in steps
        if value is None or (s.observed is not None and comparable(value, s.observed))
    ]
    if req.site_only:
        return Coverage("site_only", "cannot be tested by the vendor", design=compared)
    if not evidence:
        return Coverage("gap", "no FAT/SAT step addresses it", design=compared)

    verdicts = tuple(StepVerdict(s, step_failure(req, s, assessment)) for s in evidence)
    failures = [f"{v.step.step}: {v.failure}" for v in verdicts if v.failure is not None]
    qualifying = [v.step.protocol for v in verdicts if v.failure is None]
    if qualifying:
        if not req.transport_sensitive or any(p.stage == "SAT" for p in qualifying):
            docs = ", ".join(sorted({p.doc for p in qualifying}))
            return Coverage("covered_by_vendor", f"proved by {docs}", verdicts, compared)
        failures.append("condition 4: transport-sensitive and not retested at SAT (CPOB 12.24)")
    return Coverage("partial", "; ".join(failures), verdicts, compared)
