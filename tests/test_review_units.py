"""Pre-review rules (spec #29, deterministic units): each rule on the planted scenario it
targets and on a clean counterexample. Facts are written as the TP-201 records print them;
S2 is on a scan, so its facts are written by hand until scan ingest reads them."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from traceq.review.facts import (
    Calculation,
    Calibration,
    Deviation,
    InstrumentUse,
    Record,
    Role,
    Signature,
    SiteRule,
)
from traceq.review.limits import outside, parse
from traceq.review.rules import (
    CheckFinding,
    calculation_error,
    check,
    expired_calibration,
    failed_result_no_deviation,
    impossible_date_order,
    missing_signatures,
    out_of_limit_marked_pass,
    segregation_of_duties,
    vendor_protocol_not_approved,
)
from traceq.traceability import Citation, StepFact
from traceq.traceability.ambiguity import parse_date
from traceq.traceability.coverage import Protocol, Result

# StepFact holds the parsed model answer, which has no public type; the rules never read it.
from traceq.traceability.evidence import _Value  # pyright: ignore[reportPrivateUsage]

SOP = Citation("SOP-X", 0, 1, "rule sentence")
RULES: dict[SiteRule, Citation] = {
    "signature_name_and_date": SOP,
    "vendor_protocol_approved_before_execution": SOP,
    "preparer_not_approver": SOP,
    "checker_not_approver": SOP,
    "performer_not_witness": SOP,
}


def sig(
    doc: str, role: Role, printed: str, name: str, date: str, *, site: bool = False
) -> Signature:
    quote = " ".join(x for x in (printed, name, "Signed electronically" if name else "", date) if x)
    return Signature(
        printed, role, site, name, bool(name), parse_date(date) if date else None,
        Citation(doc, 0, 1, quote),
    )  # fmt: skip


def fat_m() -> Record:
    """FAT-TP201-M as printed: clean signatures, approved before execution."""
    d = "FAT-TP201-M"
    return Record(
        d,
        0,
        "fat",
        signatures=[
            sig(d, "prepared", "Prepared by", "Markus Brandt", "12-Jan-2026"),
            sig(d, "checked", "Checked by", "Bayu Pratama", "22-Jan-2026", site=True),
            sig(d, "approved", "Approved by", "Dewi Anggraini", "22-Jan-2026", site=True),
            sig(d, "executed", "Executed by", "Markus Brandt", "01-Feb-2026"),
            sig(d, "witnessed", "Witnessed by", "Agus Setiawan", "01-Feb-2026", site=True),
        ],
    )


def fat_c() -> Record:
    """FAT-TP201-C as printed (S4): no site check or approval."""
    d = "FAT-TP201-C"
    return Record(
        d,
        0,
        "fat",
        signatures=[
            sig(d, "prepared", "Prepared by", "Markus Brandt", "14-Jan-2026"),
            sig(d, "checked", "Checked by", "", ""),
            sig(d, "approved", "Approved by", "", ""),
            sig(d, "executed", "Executed by", "Markus Brandt", "03-Feb-2026"),
            sig(d, "witnessed", "Witnessed by", "Agus Setiawan", "03-Feb-2026", site=True),
        ],
    )


def quotes(findings: list[CheckFinding]) -> list[list[str]]:
    return [[c.quote for c in f.citations] for f in findings]


# --- S4: vendor protocol not approved ------------------------------------------------


def test_s4_vendor_protocol_executed_without_site_approval() -> None:
    (f,) = vendor_protocol_not_approved(fat_c(), RULES)
    assert f.type == "vendor_protocol_not_approved"
    assert [c.quote for c in f.citations] == ["Approved by"]
    assert f.rule == SOP


def test_s4_counterexample_approved_before_execution() -> None:
    assert vendor_protocol_not_approved(fat_m(), RULES) == []


def test_approval_after_execution_is_not_approval_before_execution() -> None:
    r = fat_m()
    r.signatures[2] = sig(
        r.doc, "approved", "Approved by", "Dewi Anggraini", "02-Feb-2026", site=True
    )
    (f,) = vendor_protocol_not_approved(r, RULES)
    assert "before the site approved it" in f.detail
    assert impossible_date_order(r) == []  # one fact, one finding


def test_a_vendor_signature_is_not_site_approval() -> None:
    r = fat_m()
    r.signatures[2] = sig(r.doc, "approved", "Approved by", "Markus Brandt", "22-Jan-2026")
    assert len(vendor_protocol_not_approved(r, RULES)) == 1


def test_an_ambiguous_date_is_never_judged() -> None:
    r = fat_m()
    r.signatures[2] = sig(
        r.doc, "approved", "Approved by", "Dewi Anggraini", "03/04/2026", site=True
    )
    r.signatures[3] = sig(r.doc, "executed", "Executed by", "Markus Brandt", "02/01/2026")
    assert vendor_protocol_not_approved(r, RULES) == []
    assert impossible_date_order(r) == []


# --- Site rules come from the SOP -----------------------------------------------------


def test_site_rules_apply_only_when_the_sop_states_them() -> None:
    r = fat_c()
    r.signatures[4] = sig(r.doc, "witnessed", "Witnessed by", "Markus Brandt", "03-Feb-2026")
    assert check([r], [], RULES) != []
    assert check([r], [], {}) == []


# --- Missing signature / date ---------------------------------------------------------


def test_missing_signature_date() -> None:
    r = fat_m()
    r.signatures[4] = sig(r.doc, "witnessed", "Witnessed by", "Agus Setiawan", "", site=True)
    (f,) = missing_signatures(r, RULES, not_approved=False)
    assert f.type == "missing_signature" and "no date" in f.detail
    assert f.citations[0].quote == "Witnessed by Agus Setiawan Signed electronically"


def test_missing_signature_counterexample() -> None:
    assert missing_signatures(fat_m(), RULES, not_approved=False) == []


def test_unapproved_protocol_is_one_finding_not_three() -> None:
    assert [f.type for f in check([fat_c()], [], RULES)] == ["vendor_protocol_not_approved"]


# --- Impossible date order -----------------------------------------------------------


def test_impossible_date_order() -> None:
    r = fat_m()
    r.signatures[4] = sig(r.doc, "witnessed", "Witnessed by", "Agus Setiawan", "30-Jan-2026")
    (f,) = impossible_date_order(r)
    assert f.type == "impossible_date_order"
    assert quotes([f]) == [[r.signatures[3].citation.quote, r.signatures[4].citation.quote]]


def test_impossible_date_order_counterexample() -> None:
    assert impossible_date_order(fat_m()) == []


def test_site_protocol_executed_before_approval() -> None:
    r = fat_m()
    r.type = "iq_protocol"
    r.signatures[2] = sig(r.doc, "approved", "Approved by", "Dewi Anggraini", "02-Feb-2026")
    assert [f.type for f in impossible_date_order(r)] == ["impossible_date_order"]


# --- Segregation of duties -----------------------------------------------------------


def test_segregation_performer_is_witness() -> None:
    r = fat_m()
    r.signatures[4] = sig(r.doc, "witnessed", "Witnessed by", "markus  brandt", "01-Feb-2026")
    (f,) = segregation_of_duties(r, RULES)
    assert f.type == "segregation_of_duties" and f.rule == SOP


def test_segregation_checker_is_approver() -> None:
    r = fat_m()
    r.signatures[1] = sig(r.doc, "checked", "Checked by", "Dewi Anggraini", "22-Jan-2026")
    assert [f.type for f in segregation_of_duties(r, RULES)] == ["segregation_of_duties"]


def test_segregation_counterexample() -> None:
    # The vendor's preparer also executes: the SOP does not forbid that.
    assert segregation_of_duties(fat_m(), RULES) == []


# --- S5: out of limit marked Pass ----------------------------------------------------

PROTOCOL = Protocol("FAT-TP201-M", 0, "FAT", dt.date(2026, 1, 22), dt.date(2026, 2, 1))
BLANK = _Value(kind="none", min=None, max=None, number=None, unit=None, text=None, present=None)


def step(sid: str, acceptance: str, observed: str, result: Result = "pass") -> StepFact:
    quote = f"{sid} test. {acceptance} {observed} {result.title()}"
    return StepFact(
        PROTOCOL, sid, "test", acceptance, observed, result,
        Citation(PROTOCOL.doc, 0, 1, quote), "en", BLANK,
    )  # fmt: skip


def test_s5_out_of_limit_marked_pass() -> None:
    (f,) = out_of_limit_marked_pass([step("FAT-M-03", "≥ 100 kN", "96 kN")])
    assert f.type == "out_of_limit_marked_pass"
    assert "96 kN" in f.citations[0].quote and "≥ 100 kN" in f.citations[0].quote


def test_s5_counterexamples() -> None:
    clean = [
        step("FAT-M-01", "≥ 36 stations", "36 stations"),
        step("FAT-M-02", "20–60 rpm", "20–60 rpm"),
        step("FAT-M-06", "≤ 0.8 µm", "0.6 µm"),
        step("FAT-M-08", "≤ 1 % FS", "0.5 % FS"),
        step("FAT-M-07", "SS 304", "SS 304"),
        step("FAT-M-10", "Present and functional", "Present and functional"),
        # S7: reads 1500 or 1.5; the ambiguity rule asks, this rule does not guess.
        step("SAT-03", "10–60 rpm", "1.500 rpm"),
        # Out of limit but recorded as failed: another rule.
        step("FAT-M-03", "≥ 100 kN", "96 kN", "fail"),
    ]
    assert out_of_limit_marked_pass(clean) == []


@pytest.mark.parametrize(
    ("acceptance", "observed", "language", "out"),
    [
        ("≥ 100 kN", "96 kN", "en", True),
        ("≥ 100 kN", "96 N", "en", None),
        ("20–60 rpm", "15–60 rpm", "en", True),
        ("≤ 0,8 µm", "0,9 µm", "id", True),
        ("< 5 mm", "5 mm", "en", True),
        ("100.000 tablet/jam", "100.000 tablet/jam", "id", False),
    ],
)
def test_outside(acceptance: str, observed: str, language: str, out: bool | None) -> None:
    assert outside(acceptance, observed, language) is out


def test_text_is_not_a_limit() -> None:
    assert parse("SS 316L", "en") is None
    assert parse("Present and functional", "en") is None


# --- Failed result without Deviation -------------------------------------------------


def test_failed_result_without_deviation() -> None:
    failed = step("FAT-M-03", "≥ 100 kN", "96 kN", "fail")
    (f,) = failed_result_no_deviation([failed], {("FAT-TP201-M", 0): fat_m()})
    assert f.type == "failed_result_no_deviation"


def test_failed_result_with_deviation_counterexample() -> None:
    r = fat_m()
    r.deviations.append(Deviation("DEV-01", ("FAT-M-03",), Citation(r.doc, 0, 2, "DEV-01")))
    failed = step("FAT-M-03", "≥ 100 kN", "96 kN", "fail")
    assert failed_result_no_deviation([failed], {(r.doc, 0): r}) == []
    # A record whose deviations were not read is not judged.
    assert failed_result_no_deviation([failed], {}) == []


# --- S2: expired calibration ---------------------------------------------------------


def sat() -> Record:
    """SAT-TP201 as printed (a scan): TACH-07 due 17/05/2026, executed 18/05/2026."""
    d = "SAT-TP201"
    c = Citation
    return Record(
        d,
        0,
        "sat",
        signatures=[
            Signature(
                "Dilaksanakan oleh / Executed by",
                "executed",
                True,
                "Executor",
                True,
                dt.date(2026, 5, 18),
                c(d, 0, 2, "Executed by Executor 18/05/2026"),
            ),
        ],
        calibrations=[
            Calibration("TACH-07", dt.date(2026, 5, 17), c(d, 0, 1, "TACH-07 17/05/2026")),
            Calibration("SW-03", dt.date(2026, 12, 1), c(d, 0, 1, "SW-03 01/12/2026")),
        ],
        uses=[
            InstrumentUse("SAT-01", "TACH-07", c(d, 0, 1, "SAT-01 TACH-07 SW-03")),
            InstrumentUse("SAT-01", "SW-03", c(d, 0, 1, "SAT-01 TACH-07 SW-03")),
            InstrumentUse("SAT-03", "TACH-07", c(d, 0, 1, "SAT-03 TACH-07")),
        ],
    )


def test_s2_expired_calibration() -> None:
    kal = Record("KAL-2025-0412", 0, "calibration_certificate")
    kal.calibrations.append(
        Calibration(
            "TACH-07", dt.date(2026, 5, 17), Citation(kal.doc, 0, 1, "Valid until 17-May-2026")
        )
    )
    r = sat()
    (f,) = expired_calibration(r, [r, kal])
    assert f.type == "expired_calibration" and "TACH-07" in f.detail
    assert [c.quote for c in f.citations] == [
        "TACH-07 17/05/2026",
        "Valid until 17-May-2026",
        "Executed by Executor 18/05/2026",
        "SAT-01 TACH-07 SW-03",
        "SAT-03 TACH-07",
    ]


def test_s2_counterexample_valid_on_the_day_of_use() -> None:
    r = sat()
    r.calibrations[0] = Calibration("TACH-07", dt.date(2026, 5, 18), r.calibrations[0].citation)
    assert expired_calibration(r, [r]) == []


def test_renewed_calibration_counts() -> None:
    r = sat()
    renewal = Record("KAL-NEW", 0, "calibration_certificate")
    renewal.calibrations.append(
        Calibration("TACH-07", dt.date(2027, 5, 17), Citation("KAL-NEW", 0, 1, "TACH-07"))
    )
    assert expired_calibration(r, [r, renewal]) == []


# --- Calculation error ---------------------------------------------------------------


def calc(inputs: tuple[float, ...], result: float, decimals: int) -> Record:
    r = fat_m()
    r.calculations.append(
        Calculation("OQ-05", "mean", inputs, result, decimals, Citation(r.doc, 0, 1, "OQ-05"))
    )
    return r


def test_calculation_error() -> None:
    (f,) = calculation_error(calc((120.4, 121.0, 119.8), 121.4, 1))
    assert f.type == "calculation_error" and "120.40" in f.detail


def test_calculation_counterexample_rounded() -> None:
    assert calculation_error(calc((120.4, 121.0, 119.9), 120.4, 1)) == []


# --- Nothing site-specific in system code --------------------------------------------


def test_no_site_rule_or_document_list_in_system_code() -> None:
    """The required-document list and the site rules come from the VMP and SOP only: no
    document number of the corpus and no printed label of the VMP or SOP is in the system."""
    src = Path(__file__).parents[1] / "src" / "traceq"
    text = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    for printed in (
        "TP201",
        "TP-201",
        "VMP-001",
        "SOP-VAL",
        "Protokol IQ",
        "Lampiran",
        "Pemisahan tugas",
        "Saksi",
    ):
        assert printed not in text, printed
