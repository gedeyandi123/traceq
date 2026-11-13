"""Pre-review rules: deterministic Check Findings over cited facts (design section 7).

No model decides here. Each rule reads facts that passed the citation check and cites them;
a rule that cannot cite its finding does not report it. A date that reads two ways is never
judged (design section 6, "Ambiguous values").

Rules the site sets (signatures with name and date, segregation of duties, site approval of
vendor protocols) are applied only when the qualification SOP states them, and their finding
also cites the SOP sentence. The others follow from the record itself or from GMP:
out-of-limit marked Pass and failed result without Deviation (CPOB 12.16), impossible date
order, expired calibration and calculation error.

One fact gets one finding: a vendor protocol without site approval is reported as not
approved, not also as missing the approval signatures; a reading outside its Acceptance
Criterion marked Pass is out of limit, not also a failed result without Deviation.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from traceq.documents import normalise
from traceq.review.facts import Record, Role, Signature, SiteRule
from traceq.review.limits import outside
from traceq.traceability import Citation, StepFact

CheckType = Literal[
    "missing_signature",
    "impossible_date_order",
    "segregation_of_duties",
    "out_of_limit_marked_pass",
    "failed_result_no_deviation",
    "vendor_protocol_not_approved",
    "expired_calibration",
    "calculation_error",
]


@dataclass(frozen=True)
class CheckFinding:
    type: CheckType
    doc: str
    detail: str
    citations: tuple[Citation, ...]
    rule: Citation | None = None
    """The SOP sentence that sets the rule, for a site rule."""


SiteRules = Mapping[SiteRule, Citation]


def _date(s: Signature | None) -> dt.date | None:
    return s.date if s is not None and isinstance(s.date, dt.date) else None


def _with_rule(
    t: CheckType, r: Record, detail: str, cites: Sequence[Citation], rule: Citation | None
) -> list[CheckFinding]:
    if not cites:
        return []
    return [CheckFinding(t, r.doc, detail, tuple(dict.fromkeys(cites)), rule)]


# --- Signatures --------------------------------------------------------------------------


def vendor_protocol_not_approved(r: Record, rules: SiteRules) -> list[CheckFinding]:
    """A vendor FAT/SAT protocol needs a site approval signed and dated on or before its
    execution (CPOB 12.14)."""
    rule = rules.get("vendor_protocol_approved_before_execution")
    if rule is None or not r.vendor_protocol:
        return []
    executed = r.first("executed")
    approvals = [s for s in r.signatures if s.role == "approved"]
    signed = [s for s in approvals if s.site and s.signed and s.date is not None]
    if any(s.date is not None and not isinstance(s.date, dt.date) for s in signed):
        return []
    if executed is not None and executed.date is not None and _date(executed) is None:
        return []
    done = _date(executed)
    dates = [d for s in signed if (d := _date(s)) is not None]
    if dates and (done is None or min(dates) <= done):
        return []
    cites: list[Citation]
    if dates:
        assert done is not None
        detail = (
            f"{r.doc} was executed on {done:%d %b %Y}, before the site approved it on"
            f" {min(dates):%d %b %Y}; its results cannot be used as Vendor Evidence."
        )
        cites = [s.citation for s in signed] + ([executed.citation] if executed else [])
    else:
        detail = (
            f"{r.doc} was executed with no site approval of the protocol; its results cannot"
            " be used as Vendor Evidence."
        )
        cites = [s.citation for s in approvals] or (
            [s.citation for s in r.signatures if s.role == "checked"]
            or ([executed.citation] if executed else [])
        )
    return _with_rule("vendor_protocol_not_approved", r, detail, cites, rule)


def missing_signatures(r: Record, rules: SiteRules, not_approved: bool) -> list[CheckFinding]:
    """Every signature row carries a name, a signature and a date."""
    rule = rules.get("signature_name_and_date")
    if rule is None:
        return []
    out: list[CheckFinding] = []
    for s in r.signatures:
        if s.complete or (not_approved and s.role in ("checked", "approved")):
            continue
        lacks = [
            what
            for what, ok in (
                ("name", bool(s.name.strip())),
                ("signature", s.signed),
                ("date", s.date is not None),
            )
            if not ok
        ]
        detail = f"{r.doc}: '{s.role_printed}' has no {', '.join(lacks)}."
        out += _with_rule("missing_signature", r, detail, [s.citation], rule)
    return out


_ORDER: tuple[tuple[Role, Role], ...] = (
    ("prepared", "checked"),
    ("prepared", "approved"),
    ("checked", "approved"),
    ("prepared", "executed"),
    ("executed", "witnessed"),
)


def impossible_date_order(r: Record) -> list[CheckFinding]:
    """A record signed out of order: checked or approved before it was prepared, executed
    before it was prepared, witnessed before execution; for a site protocol, executed before
    it was approved (a vendor protocol's approval is ``vendor_protocol_not_approved``)."""
    site: tuple[tuple[Role, Role], ...] = (("approved", "executed"),)
    pairs = _ORDER if r.vendor_protocol else (*_ORDER, *site)
    out: list[CheckFinding] = []
    for before, after in pairs:
        a, b = r.first(before), r.first(after)
        da, db = _date(a), _date(b)
        if a is None or b is None or da is None or db is None or da <= db:
            continue
        detail = (
            f"{r.doc}: '{b.role_printed}' is dated {db:%d %b %Y}, before"
            f" '{a.role_printed}' on {da:%d %b %Y}."
        )
        out += _with_rule("impossible_date_order", r, detail, [a.citation, b.citation], None)
    return out


_DUTIES: tuple[tuple[SiteRule, Role, Role, str], ...] = (
    ("preparer_not_approver", "prepared", "approved", "prepared and approved"),
    ("checker_not_approver", "checked", "approved", "checked and approved"),
    ("performer_not_witness", "executed", "witnessed", "performed and witnessed"),
)


def _same_person(a: str, b: str) -> bool:
    x, y = normalise(a).casefold(), normalise(b).casefold()
    return bool(x) and x == y


def segregation_of_duties(r: Record, rules: SiteRules) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    for name, first, second, what in _DUTIES:
        rule = rules.get(name)
        a, b = r.first(first), r.first(second)
        if rule is None or a is None or b is None or not _same_person(a.name, b.name):
            continue
        detail = f"{r.doc}: {a.name.strip()} both {what} it."
        out += _with_rule("segregation_of_duties", r, detail, [a.citation, b.citation], rule)
    return out


# --- Results -----------------------------------------------------------------------------


def out_of_limit_marked_pass(steps: Iterable[StepFact]) -> list[CheckFinding]:
    """A reading outside its own Acceptance Criterion recorded as Pass (CPOB 12.16)."""
    return [
        CheckFinding(
            "out_of_limit_marked_pass",
            s.protocol.doc,
            f"{s.step} records {s.observed} against an Acceptance Criterion of"
            f" {s.acceptance} and is marked Pass; it is a failed result to raise as a"
            " Deviation.",
            (s.citation,),
        )
        for s in steps
        if s.result == "pass" and outside(s.acceptance, s.observed, s.language)
    ]


def failed_result_no_deviation(
    steps: Iterable[StepFact], records: Mapping[tuple[str, int], Record]
) -> list[CheckFinding]:
    """A step recorded as failed that no Deviation of its record names (CPOB 12.16). A
    record whose deviations were not read is not judged."""
    out: list[CheckFinding] = []
    for s in steps:
        r = records.get((s.protocol.doc, s.protocol.rev))
        if s.result != "fail" or r is None:
            continue
        if any(_same_step(s.step, d) for dev in r.deviations for d in dev.steps):
            continue
        out.append(
            CheckFinding(
                "failed_result_no_deviation",
                s.protocol.doc,
                f"{s.step} is recorded as failed ({s.observed}) and no Deviation is raised.",
                (s.citation,),
            )
        )
    return out


def _same_step(a: str, b: str) -> bool:
    return normalise(a).casefold() == normalise(b).casefold()


# --- Instruments -------------------------------------------------------------------------


def expired_calibration(r: Record, calibrations: Iterable[Record]) -> list[CheckFinding]:
    """An instrument used on a record executed after its calibration validity ended. The
    validity is the latest printed for the instrument on any record or certificate."""
    executed = r.first("executed")
    done = _date(executed)
    if executed is None or done is None:
        return []
    used: dict[str, list[Citation]] = {}
    for u in r.uses:
        used.setdefault(normalise(u.instrument).casefold(), []).append(u.citation)
    for c in r.calibrations:
        used.setdefault(normalise(c.instrument).casefold(), [])
    validity = [c for rec in calibrations for c in rec.calibrations]
    out: list[CheckFinding] = []
    for key, uses in used.items():
        known = [c for c in validity if normalise(c.instrument).casefold() == key]
        if not known or any(not isinstance(c.valid_until, dt.date) for c in known):
            continue
        until = max(c.valid_until for c in known if isinstance(c.valid_until, dt.date))
        if done <= until:
            continue
        name = known[0].instrument
        detail = (
            f"{r.doc}: {name} was used on {done:%d %b %Y}; its calibration was valid until"
            f" {until:%d %b %Y}, so its results lack valid measurement Evidence."
        )
        cites = [c.citation for c in known] + [executed.citation] + uses
        out += _with_rule("expired_calibration", r, detail, cites, None)
    return out


# --- Calculations ------------------------------------------------------------------------


def _compute(op: str, xs: Sequence[float]) -> float | None:
    if not xs:
        return None
    match op:
        case "mean":
            return sum(xs) / len(xs)
        case "sum":
            return sum(xs)
        case "difference":
            return xs[0] - sum(xs[1:]) if len(xs) > 1 else None
        case "min":
            return min(xs)
        case "max":
            return max(xs)
        case "range":
            return max(xs) - min(xs)
        case _:
            return None


def calculation_error(r: Record) -> list[CheckFinding]:
    """A printed result that its printed inputs do not give, beyond rounding to the printed
    decimals."""
    out: list[CheckFinding] = []
    for c in r.calculations:
        expected = _compute(c.operation, c.inputs)
        if expected is None or abs(expected - c.result) <= 0.5 * 10**-c.decimals + 1e-9:
            continue
        detail = (
            f"{r.doc} {c.step}: the {c.operation} of the recorded values is"
            f" {expected:.{c.decimals + 1}f}, not the {c.result:.{c.decimals}f} stated."
        )
        out += _with_rule("calculation_error", r, detail, [c.citation], None)
    return out


# --- All rules ---------------------------------------------------------------------------


def check(
    records: Sequence[Record], steps: Sequence[StepFact], rules: SiteRules
) -> list[CheckFinding]:
    """Every rule over every record and vendor test step."""
    out: list[CheckFinding] = []
    for r in records:
        approval = vendor_protocol_not_approved(r, rules)
        out += approval
        out += missing_signatures(r, rules, not_approved=bool(approval))
        out += impossible_date_order(r)
        out += segregation_of_duties(r, rules)
        out += expired_calibration(r, records)
        out += calculation_error(r)
    out += out_of_limit_marked_pass(steps)
    out += failed_result_no_deviation(steps, {(r.doc, r.rev): r for r in records})
    return out
