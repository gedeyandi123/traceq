"""Deterministic units of Evidence and Coverage (spec #29, Testing Decisions): the ambiguity
rule (S7), the ``covered_by_vendor`` decision table per condition and tie-break order, the
Coverage ``conflict`` (S6), and the superseded value (S8)."""

from __future__ import annotations

import datetime as dt

from traceq.traceability.ambiguity import Ambiguous, parse_date, read_number
from traceq.traceability.coverage import (
    DesignFact,
    Observed,
    Protocol,
    RequirementFacts,
    Result,
    Step,
    VendorAssessment,
    classify,
)
from traceq.traceability.values import Number, OneOf, Present, Range, Text, Value

# --- Ambiguous values (S7) --------------------------------------------------------------


def test_a_decimal_separator_before_three_digits_reads_two_ways() -> None:
    # English document: "." is the decimal point, but an Indonesian hand groups thousands.
    assert read_number("1.500 rpm", "en", reference=(10, 60)) == Ambiguous((1500, 1.5))
    # Indonesian document: "," is the decimal point.
    assert read_number("1,500 rpm", "id", reference=(10, 60)) == Ambiguous((1500, 1.5))


def test_the_document_convention_reads_grouping_without_doubt() -> None:
    assert read_number("120.000 tablet/jam", "id", reference=()) == 120000
    assert read_number("151,200 tablets/h", "en", reference=()) == 151200
    assert read_number("0,8 µm", "id", reference=()) == 0.8
    assert read_number("0.6 µm", "en", reference=()) == 0.6
    assert read_number("96 kN", "en", reference=(100,)) == 96


def test_a_reading_off_by_a_factor_100_is_implausible() -> None:
    # 122.4 tablets/h against at least 120,000: only 122,400 is plausible.
    assert read_number("122.400 tablets/h", "en", reference=(120000,)) == 122400
    # Without a reference, never guess.
    assert read_number("122.400 tablets/h", "en", reference=()) == Ambiguous((122400, 122.4))


def test_no_number_reads_as_none() -> None:
    assert read_number("Present and functional", "en", reference=()) is None


def test_dates() -> None:
    assert parse_date("22-Jan-2026") == dt.date(2026, 1, 22)
    assert parse_date("29/10/2025") == dt.date(2025, 10, 29)
    assert parse_date("2026-02-01") == dt.date(2026, 2, 1)
    assert parse_date("03/04/2026") == Ambiguous((dt.date(2026, 4, 3), dt.date(2026, 3, 4)))
    assert parse_date("04/04/2026") == dt.date(2026, 4, 4)
    assert parse_date("signed") is None


# --- Decision table: covered_by_vendor (design section 6) -------------------------------

ASSESSED = VendorAssessment(scope=frozenset({"mechanical", "control"}))
APPROVED = Protocol(
    "FAT-X", 0, "FAT", site_approved_on=dt.date(2026, 1, 22), executed_on=dt.date(2026, 2, 1)
)
UNAPPROVED = Protocol("FAT-Y", 0, "FAT", site_approved_on=None, executed_on=dt.date(2026, 2, 3))
SAT = Protocol(
    "SAT-X", 0, "SAT", site_approved_on=dt.date(2026, 4, 1), executed_on=dt.date(2026, 5, 1)
)
SPEED = Range(min=20, max=70, unit="rpm")
FULL = Range(min=20, max=70, unit="rpm")
SHORT = Range(min=20, max=60, unit="rpm")


def _req(
    value: Value | None = SPEED,
    *,
    transport: bool = False,
    site_only: bool = False,
    scope: str | None = "mechanical",
) -> RequirementFacts:
    return RequirementFacts(
        "URS-X-001", value, site_only=site_only, transport_sensitive=transport, scope=scope
    )


def _step(
    observed: Observed | None,
    protocol: Protocol = APPROVED,
    step: str = "FAT-01",
    result: Result | None = "pass",
) -> Step:
    return Step(protocol, step, observed, result)


def test_all_four_conditions_hold_covered_by_vendor() -> None:
    c = classify(_req(), [_step(FULL)], [], ASSESSED)
    assert (c.coverage, c.reason) == ("covered_by_vendor", "proved by FAT-X")
    assert [s.step for s in c.evidence] == ["FAT-01"]


def test_condition_1_vendor_not_assessed_or_out_of_scope() -> None:
    c = classify(_req(), [_step(FULL)], [], None)
    assert (c.coverage, c.reason) == ("partial", "FAT-01: condition 1: no Vendor Assessment")
    c = classify(_req(scope="software"), [_step(FULL)], [], ASSESSED)
    assert c.reason == "FAT-01: condition 1: scope 'software' not in vendor assessment"
    c = classify(_req(scope=None), [_step(FULL)], [], ASSESSED)
    assert c.reason == "FAT-01: condition 1: no assessed area named"


def test_condition_2_protocol_not_approved_before_execution() -> None:
    c = classify(_req(), [_step(FULL, UNAPPROVED)], [], ASSESSED)
    assert c.coverage == "partial"
    assert c.reason == (
        "FAT-01: condition 2: protocol not approved by site before execution (CPOB 12.14)"
    )
    late = Protocol(
        "FAT-Z", 0, "FAT", site_approved_on=dt.date(2026, 2, 2), executed_on=dt.date(2026, 2, 1)
    )
    assert classify(_req(), [_step(FULL, late)], [], ASSESSED).coverage == "partial"


def test_condition_2_never_guesses_an_ambiguous_date() -> None:
    unclear = Protocol(
        "FAT-Z",
        0,
        "FAT",
        site_approved_on=Ambiguous((dt.date(2026, 4, 3), dt.date(2026, 3, 4))),
        executed_on=dt.date(2026, 5, 1),
    )
    c = classify(_req(), [_step(FULL, unclear)], [], ASSESSED)
    assert (c.coverage, c.reason) == (
        "partial",
        "FAT-01: condition 2: date ambiguous, ask for confirmation",
    )


def test_condition_3_full_urs_range_not_tested() -> None:
    c = classify(_req(), [_step(SHORT)], [], ASSESSED)
    assert (c.coverage, c.reason) == ("partial", "FAT-01: condition 3: full URS range not tested")
    # One reading proves a one-sided limit, not a span.
    force = _req(Range(min=100, unit="kN"))
    assert classify(force, [_step(Number(value=101, unit="kN"))], [], ASSESSED).coverage == (
        "covered_by_vendor"
    )
    c = classify(_req(), [_step(Number(value=50, unit="rpm"))], [], ASSESSED)
    assert c.reason == "FAT-01: condition 3: full URS range not tested"


def test_condition_4_transport_sensitive_needs_a_sat_retest() -> None:
    fat = _step(Number(value=0.5, unit="% FS"))
    accuracy = _req(Range(max=1, unit="% FS"), transport=True)
    c = classify(accuracy, [fat], [], ASSESSED)
    assert (c.coverage, c.reason) == (
        "partial",
        "condition 4: transport-sensitive and not retested at SAT (CPOB 12.24)",
    )
    sat = _step(Number(value=0.6, unit="% FS"), SAT, "SAT-01")
    c = classify(accuracy, [fat, sat], [], ASSESSED)
    assert (c.coverage, c.reason) == ("covered_by_vendor", "proved by FAT-X, SAT-X")


def test_tie_break_reports_the_first_failing_condition() -> None:
    bad = _step(SHORT, UNAPPROVED)  # fails conditions 1 (out of scope), 2 and 3
    c = classify(_req(scope="software"), [bad], [], ASSESSED)
    assert c.reason.startswith("FAT-01: condition 1")
    assert classify(_req(), [bad], [], ASSESSED).reason.startswith("FAT-01: condition 2")
    # A result that does not meet the URS comes before every condition.
    low = _step(Number(value=96, unit="kN"), UNAPPROVED)
    c = classify(_req(Range(min=100, unit="kN")), [low], [], None)
    assert c.reason == "FAT-01: result does not meet the URS"


def test_one_qualifying_step_is_enough_and_failures_are_listed_otherwise() -> None:
    short = _step(SHORT, step="FAT-01")
    assert classify(_req(), [short, _step(FULL, SAT, "SAT-01")], [], ASSESSED).coverage == (
        "covered_by_vendor"
    )
    slow = _step(Number(value=1.5, unit="rpm"), SAT, step="SAT-01")
    assert classify(_req(), [short, slow], [], ASSESSED).reason == (
        "FAT-01: condition 3: full URS range not tested; SAT-01: result does not meet the URS"
    )


def test_a_recorded_fail_never_proves() -> None:
    c = classify(_req(), [_step(FULL, result="fail")], [], ASSESSED)
    assert c.reason == "FAT-01: result does not meet the URS"


def test_site_only_and_gap() -> None:
    c = classify(_req(site_only=True), [_step(FULL)], [], ASSESSED)
    assert (c.coverage, c.reason) == ("site_only", "cannot be tested by the vendor")
    c = classify(_req(), [], [], ASSESSED)
    assert (c.coverage, c.reason) == ("gap", "no FAT/SAT step addresses it")


def test_a_step_that_cannot_test_the_value_is_not_evidence() -> None:
    # A lure: "check certificates of all product-contact parts" says nothing about the gasket
    # material the URS asks for, so it is no Evidence and the requirement stays a gap.
    gasket = _req(OneOf(allowed=("EPDM", "silicone")))
    c = classify(gasket, [_step(Present(value=True))], [], ASSESSED)
    assert (c.coverage, c.evidence) == ("gap", ())
    assert classify(_req(), [_step(Number(value=50, unit="kN"))], [], ASSESSED).coverage == "gap"


def test_without_a_verified_urs_value_no_step_can_prove() -> None:
    c = classify(_req(None), [_step(FULL)], [], ASSESSED)
    assert (c.coverage, c.reason) == ("partial", "FAT-01: URS value not verified")


# --- Coverage conflict (S6) -------------------------------------------------------------


def test_a_design_fact_that_does_not_meet_the_urs_is_a_conflict() -> None:
    material = _req(OneOf(allowed=("SS 316L",)))
    proved = _step(Text(value="SS 316L"))
    cert = DesignFact("MTC-X", 0, Text(value="SS 304"))
    c = classify(material, [proved], [cert], ASSESSED)
    assert (c.coverage, c.reason) == ("conflict", "MTC-X does not meet the URS")
    ok = DesignFact("DS-X", 0, Text(value="ss 316l"))
    assert classify(material, [proved], [ok], ASSESSED).coverage == "covered_by_vendor"
    # Conflict comes before site_only.
    tooling = _req(OneOf(allowed=("EU D",)), site_only=True)
    c = classify(tooling, [], [DesignFact("DS-X", 0, Text(value="EU B"))], ASSESSED)
    assert c.coverage == "conflict"


def test_a_design_fact_that_cannot_be_compared_is_no_conflict() -> None:
    c = classify(_req(), [], [DesignFact("DS-X", 0, Text(value="variable"))], ASSESSED)
    assert c.coverage == "gap"
    assert c.design == ()


# --- Ambiguous result (S7) --------------------------------------------------------------


def test_an_ambiguous_result_is_not_guessed() -> None:
    paddle = _req(Range(min=10, max=60, unit="rpm"))
    c = classify(paddle, [_step(Ambiguous((1500.0, 1.5)), SAT, "SAT-03")], [], ASSESSED)
    assert (c.coverage, c.reason) == ("partial", "SAT-03: result ambiguous, ask for confirmation")
    assert [s.step for s in c.ambiguous] == ["SAT-03"]
