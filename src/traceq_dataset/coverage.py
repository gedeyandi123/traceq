"""Expected Coverage class per requirement (design section 6, decision table).

Order of evaluation:

1. A design or delivered-item fact that does not meet the URS -> ``conflict``.
2. The requirement cannot be tested by the vendor -> ``site_only``.
3. No FAT/SAT step addresses it -> ``gap``.
4. ``covered_by_vendor`` only if one step meets all four decision-table conditions;
   otherwise ``partial``. The reason names the first condition that failed.

A step counts as Evidence only if its observation actually meets the URS. A step
recorded "pass" with an out-of-limit value (planted defect) does not prove anything.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from traceq_dataset.schema import (
    CoverageClass,
    DesignEvidence,
    NumberObs,
    Observation,
    OneOfSpec,
    PendingObs,
    PendingSpec,
    PresentObs,
    PresentSpec,
    RangeObs,
    RangeSpec,
    Requirement,
    Spec,
    Stage,
    TestEvidence,
    TextObs,
    Vendor,
    VendorProtocol,
)


class IncomparableError(ValueError):
    """An observation cannot be compared with a spec (wrong kind or unit)."""


class PendingError(ValueError):
    """A skeleton value is not filled yet, so Coverage cannot be decided."""


def meets(spec: Spec, obs: Observation) -> bool:
    """Does a single observed value satisfy the URS spec?"""
    match spec, obs:
        case RangeSpec(), NumberObs():
            _same_unit(spec.unit, obs.unit)
            return (spec.min is None or obs.value >= spec.min) and (
                spec.max is None or obs.value <= spec.max
            )
        case OneOfSpec(), TextObs():
            return obs.value in spec.allowed
        case PresentSpec(), PresentObs():
            return obs.value
    raise IncomparableError(f"cannot compare {spec.type} spec with {obs.type} observation")


def covers_full_range(spec: Spec, obs: Observation) -> bool:
    """Decision-table condition 3: was the whole URS range exercised?"""
    match spec, obs:
        case RangeSpec(), RangeObs():
            _same_unit(spec.unit, obs.unit)
            return (spec.min is None or obs.min <= spec.min) and (
                spec.max is None or obs.max >= spec.max
            )
        case RangeSpec(), NumberObs():
            # One reading proves a one-sided limit or a fixed value, not a span.
            return spec.min is None or spec.max is None or spec.min == spec.max
    return True


def _same_unit(spec_unit: str, obs_unit: str) -> None:
    if spec_unit != obs_unit:
        raise IncomparableError(f"unit mismatch: spec {spec_unit!r}, observed {obs_unit!r}")


def proves(req: Requirement, step: TestEvidence) -> bool:
    """Does the step's real outcome meet the URS? Range sweeps rely on the recorded result."""
    if isinstance(step.observed, RangeObs):
        return step.recorded_result == "pass"
    return meets(req.spec, step.observed)


@dataclass(frozen=True)
class CoverageResult:
    coverage: CoverageClass
    reason: str


def classify(
    req: Requirement,
    tests: Iterable[TestEvidence],
    designs: Iterable[DesignEvidence],
    protocols: Mapping[str, VendorProtocol],
    vendors: Mapping[str, Vendor],
) -> CoverageResult:
    """Apply the decision table to one requirement. Inputs may hold other requirements' data."""
    tests, designs = list(tests), list(designs)
    _require_filled(req, tests, designs)
    for fact in designs:
        if fact.requirement == req.id and not meets(req.spec, fact.observed):
            return CoverageResult(CoverageClass.CONFLICT, f"{fact.doc_id} does not meet the URS")

    if req.site_only:
        return CoverageResult(CoverageClass.SITE_ONLY, "cannot be tested by the vendor")

    steps = [s for s in tests if s.requirement == req.id]
    if not steps:
        return CoverageResult(CoverageClass.GAP, "no FAT/SAT step addresses it")

    failures: list[str] = []
    qualifying: list[VendorProtocol] = []
    for step in steps:
        protocol = protocols[step.protocol]
        failure = step_failure(req, step, protocol, vendors[protocol.vendor])
        if failure is None:
            qualifying.append(protocol)
        else:
            failures.append(f"{step.step}: {failure}")

    if qualifying:
        if not req.transport_sensitive or any(p.stage is Stage.SAT for p in qualifying):
            steps_ok = ", ".join(sorted({p.doc_id for p in qualifying}))
            return CoverageResult(CoverageClass.COVERED_BY_VENDOR, f"proved by {steps_ok}")
        failures.append("condition 4: transport-sensitive and not retested at SAT (CPOB 12.24)")

    return CoverageResult(CoverageClass.PARTIAL, "; ".join(failures))


def _require_filled(
    req: Requirement, tests: list[TestEvidence], designs: list[DesignEvidence]
) -> None:
    observed = [e.observed for e in [*tests, *designs] if e.requirement == req.id]
    if isinstance(req.spec, PendingSpec) or any(isinstance(o, PendingObs) for o in observed):
        raise PendingError(f"{req.id}: value or Evidence still pending")


def step_failure(
    req: Requirement, step: TestEvidence, protocol: VendorProtocol, vendor: Vendor
) -> str | None:
    if not proves(req, step):
        return "result does not meet the URS"
    assessment = vendor.assessment
    if assessment is None or req.scope not in assessment.scope:
        return f"condition 1: scope {req.scope!r} not in vendor assessment"
    if protocol.site_approved_on is None or protocol.site_approved_on > protocol.executed_on:
        return "condition 2: protocol not approved by site before execution (CPOB 12.14)"
    if not covers_full_range(req.spec, step.observed):
        return "condition 3: full URS range not tested"
    return None
