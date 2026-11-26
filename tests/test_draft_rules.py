"""Draft rules (spec #196 "Rules" and "Comparators available", ticket #208): from the facts read
from a Protocol Draft and the URS to Check Findings, and the vendor facts shown beside each
Test Step. Facts are built here as the reader keeps them (verified citations); the rules
never see a model."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from pathlib import Path

import pytest

from traceq.documents import CorpusDocument, Page
from traceq.review.draft import (
    Comparator,
    DraftReading,
    DraftRow,
    StepReading,
    TraceRow,
    VendorFact,
    draft_rows,
)
from traceq.review.draft_rules import DraftFinding, draft_findings
from traceq.review.printed import read_printed
from traceq.traceability import Citation, Linked, Requirement, RowFact, StepFact, Traceability
from traceq.traceability.coverage import Coverage, DesignFact, Protocol, RequirementFacts
from traceq.traceability.evidence import (
    _Value,  # pyright: ignore[reportPrivateUsage]  # the model's answer shape; no public builder
)
from traceq.traceability.values import Range

DOC = CorpusDocument(
    "OQ-XY100", 0, "oq_protocol", "born_digital", "id", Path("draft.pdf"), "d" * 64
)
URS = "URS-XY100"


def _step(sid: str, ac: str, *reqs: str) -> StepReading:
    return StepReading(
        sid, reqs, ac, read_printed(ac, "id"), Citation(DOC.doc_id, 0, 1, f"Kriteria {ac}")
    )


def _row(req: str, *steps: str) -> TraceRow:
    return TraceRow(req, steps, Citation(DOC.doc_id, 0, 2, f"{req} {' '.join(steps)}"))


def _req(rid: str, sentence: str) -> Requirement:
    quote = f"{rid} Ya {sentence}"
    return Requirement(rid, sentence, Citation(URS, 1, 1, quote), True)


def _reading(
    steps: Sequence[StepReading], rows: Sequence[TraceRow], body: str = ""
) -> DraftReading:
    """Page 1: the Test Steps as printed (plus ``body``); page 2: the traceability table."""
    page1 = "\n".join(f"Langkah uji {s.id}\nKriteria {s.printed}" for s in steps)
    page2 = "Matriks ketertelusuran\n" + "\n".join(r.citation.quote for r in rows)
    pages = (Page(1, f"{page1}\n{body}"), Page(2, page2))
    return DraftReading(DOC, pages, list(steps), list(rows))


def _judge(
    urs: str, ac: str, requirements: Sequence[Requirement] | None = None
) -> tuple[DraftRow, list[DraftFinding]]:
    """One Test Step OQ-01 tracing to URS-XY100-004 by the table."""
    reading = _reading([_step("OQ-01", ac, "URS-XY100-004")], [_row("URS-XY100-004", "OQ-01")])
    reqs = [_req("URS-XY100-004", urs)] if requirements is None else requirements
    rows = draft_rows(reading, Traceability(requirements=list(reqs)), "id")
    return rows[0], draft_findings(reading, rows)


# --- ac_deviates_from_urs: one-sided URS limits --------------------------------------------


@pytest.mark.parametrize(
    ("urs", "ac", "finding"),
    [
        ("Gaya tekan minimal 80 kN.", "minimal 80 kN", False),  # equal
        ("Gaya tekan minimal 80 kN.", "minimal 85 kN", False),  # stricter
        ("Gaya tekan minimal 80 kN.", "minimal 75 kN", True),  # looser
        ("Gaya tekan minimal 80 kN.", "> 80 kN", False),  # strict AC at a non-strict limit
        ("Gaya tekan lebih dari 80 kN.", "minimal 80 kN", True),  # accepts 80, URS rejects it
        ("Gaya tekan lebih dari 80 kN.", "> 80 kN", False),
        ("Gaya tekan minimal 80 kN.", "85 kN", False),  # a single number inside the limit
        ("Gaya tekan minimal 80 kN.", "75 kN", True),
        ("Gaya tekan minimal 80 kN.", "maks. 100 kN", True),  # accepts 0 kN
        ("Diameter tablet maksimal 25 mm.", "≤ 25 mm", False),
        ("Diameter tablet maksimal 25 mm.", "maks. 17,5 mm", False),
        ("Diameter tablet maksimal 25 mm.", "maks. 26 mm", True),
        ("Diameter tablet maksimal 25 mm.", "20–24 mm", False),
        ("Diameter tablet maksimal 25 mm.", "20–30 mm", True),
        ("Kekasaran Ra maksimal 0,8 µm.", "Ra < 0,8 µm", False),
        ("Kekasaran Ra kurang dari 0,8 µm.", "Ra maks. 0,8 µm", True),
        ("Kekasaran Ra kurang dari 0,8 µm.", "Ra < 0,8 µm", False),
    ],
)
def test_one_sided_urs_limit_finding_when_the_ac_accepts_what_the_urs_rejects(
    urs: str, ac: str, finding: bool
) -> None:
    row, found = _judge(urs, ac)
    assert row.not_compared is None
    assert [c.deviates for c in row.traced] == [finding]
    assert [(f.type, f.test_step) for f in found] == (
        [("ac_deviates_from_urs", "OQ-01")] if finding else []
    )


def test_a_finding_cites_the_ac_in_the_draft_and_the_urs_sentence() -> None:
    row, (f,) = _judge("Gaya tekan minimal 80 kN.", "minimal 75 kN")
    assert f.citations == (
        Citation(DOC.doc_id, 0, 1, "Kriteria minimal 75 kN"),
        Citation(URS, 1, 1, "URS-XY100-004 Ya Gaya tekan minimal 80 kN."),
    )
    assert (f.row, f.requirement) == (None, "URS-XY100-004")
    assert (f.ac, f.urs) == (row.step.value, row.traced[0].urs.value)
    assert f.detail == (
        "OQ-01 accepts at least 75 kN, which URS-XY100-004 rejects: it requires at least 80 kN."
    )


# --- ac_deviates_from_urs: a URS single number -------------------------------------------


@pytest.mark.parametrize(
    ("urs", "ac", "finding"),
    [
        ("Mesin memiliki 36 stasiun punch.", "36 stasiun", False),
        ("Mesin memiliki 36 stasiun punch.", "32 stasiun", True),
        ("Mesin memiliki 36 stasiun punch.", "36", False),  # a count without unit (#175)
        ("Lebar celah 10–10 mm.", "10 mm", False),  # min = max is a single number (Rule B)
        ("Lebar celah 10–10 mm.", "12 mm", True),
    ],
)
def test_urs_single_number_compares_only_a_single_number_ac(
    urs: str, ac: str, finding: bool
) -> None:
    row, found = _judge(urs, ac)
    assert row.not_compared is None
    assert [f.type for f in found] == (["ac_deviates_from_urs"] if finding else [])


# --- Equivalent units compare (the one unit table) ------------------------------------------


@pytest.mark.parametrize(
    ("urs", "ac", "finding"),
    [
        ("Changeover maksimal 120 menit.", "maks. 2 jam", False),  # 2 jam = 120 menit
        ("Changeover maksimal 120 menit.", "maks. 3 jam", True),
        ("Changeover maksimal 120 menit.", "maks. 120 menit", False),
        ("Kebisingan maksimal 85 dBA.", "maks. 85 dB(A)", False),
        ("Kebisingan maksimal 85 dBA.", "maks. 90 dB(A)", True),
        ("Tinggi plafon maksimal 3.000 mm.", "maks. 3 m", False),
        ("Tinggi plafon maksimal 3.000 mm.", "maks. 3,2 m", True),
        ("Diameter maksimal 15 mm.", "maks. 1,5 cm", False),  # 1.5 cm = 15 mm
        ("Diameter maksimal 15 mm.", "maks. 1,6 cm", True),
        ("Gaya tekan minimal 80 kN.", "minimal 80.000 N", False),
        ("Gaya tekan minimal 80 kN.", "minimal 70.000 N", True),
        ("Aliran minimal 300 m³/jam.", "minimal 300 m³/h", False),
        ("Output minimal 120.000 tablet/jam.", "minimal 120.000 tablets/h", False),
        ("Output minimal 120.000 tablet/jam.", "minimal 110.000 tablets/h", True),
    ],
)  # fmt: skip
def test_equivalent_units_compare_and_are_no_unit_error(urs: str, ac: str, finding: bool) -> None:
    row, found = _judge(urs, ac)
    assert row.not_compared is None
    assert [f.type for f in found] == (["ac_deviates_from_urs"] if finding else [])


# --- unit_error ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("urs", "ac", "how"),
    [
        ("Tinggi maksimal 18 mm.", "maks. 18 cm", "off by a factor of 10"),
        ("Gaya tekan minimal 100 kN.", "minimal 100 N", "off by a factor of 1/1000"),
        ("Diameter maksimal 5 mm.", "maks. 5 µm", "off by a factor of 1/1000"),
        ("Tegangan 380 V.", "380 kV", "off by a factor of 1000"),
        ("Kecepatan maksimal 70 rpm.", "maks. 70 Hz", "other dimensions"),
        ("Aliran minimal 300 m³/jam.", "minimal 300 m²/jam", "other dimensions"),
        ("Tekanan maksimal 6 bar.", "maks. 6 mm", "other dimensions"),
        ("Gaya tekan minimal 100 kN.", "100 N", "off by a factor of 1/1000"),
    ],
)  # fmt: skip
def test_the_urs_number_in_a_unit_off_by_a_prefix_or_a_dimension_is_a_unit_error(
    urs: str, ac: str, how: str
) -> None:
    row, found = _judge(urs, ac)
    (f,) = found  # unit_error takes the step: no ac_deviates_from_urs beside it
    assert f.type == "unit_error" and f.test_step == "OQ-01" and f.requirement == "URS-XY100-004"
    assert how in f.detail and f.label == "not reviewed by a practitioner"
    assert [c.doc for c in f.citations] == ["OQ-XY100", "URS-XY100"]
    assert row.traced[0].unit_error is not None


@pytest.mark.parametrize(
    ("urs", "ac"),
    [
        ("Tinggi maksimal 18 mm.", "maks. 19 cm"),  # another number: a plain deviation
        ("Changeover maksimal 120 menit.", "maks. 120 jam"),  # factor 60, not a power of ten
        ("Changeover maksimal 120 menit.", "maks. 2 jam"),  # equivalent
        ("Tinggi plafon maksimal 3.000 mm.", "maks. 3 m"),  # equivalent
        ("Diameter maksimal 15 mm.", "maks. 1,5 cm"),
        ("Kebisingan maksimal 85 dBA.", "maks. 85 dB(A)"),  # one unit, two spellings
        ("Output minimal 120.000 tablet/jam.", "minimal 120.000 tablets/h"),
        ("Tinggi maksimal 18 mm.", "maks. 18 mm"),
        ("Mesin memiliki 36 stasiun punch.", "36 stasiun"),
        ("Tinggi maksimal 18 mm.", "maks. 18"),  # no unit: not this rule's
        ("Mesin memiliki 36 stasiun punch.", "36 buah"),  # unknown unit: never another dimension
    ],
)  # fmt: skip
def test_no_unit_error_without_the_same_number_and_a_known_unit_slip(urs: str, ac: str) -> None:
    _, found = _judge(urs, ac)
    assert "unit_error" not in [f.type for f in found]


def test_a_unit_error_and_a_deviation_on_one_step_raise_the_unit_error_only() -> None:
    """18 cm accepts 180 mm, which the URS limit 18 mm rejects: both apply, one is raised."""
    row, found = _judge("Tinggi maksimal 18 mm.", "maks. 18 cm")
    assert row.traced[0].deviates and row.traced[0].unit_error is not None
    assert [f.type for f in found] == ["unit_error"]


def test_a_unit_error_in_the_smaller_direction_is_a_unit_error_too() -> None:
    """5 µm is stricter than 5 mm: no deviation, still the wrong unit."""
    row, found = _judge("Diameter maksimal 5 mm.", "maks. 5 µm")
    assert not row.traced[0].deviates
    assert [f.type for f in found] == ["unit_error"]


def test_a_dimension_slip_is_not_compared_but_is_a_unit_error() -> None:
    row, found = _judge("Aliran minimal 300 m³/jam.", "minimal 300 m²/jam")
    assert row.not_compared == "units do not compare (m²/jam and m³/jam)"
    assert [f.type for f in found] == ["unit_error"]


def test_the_unit_error_is_appended_after_the_older_findings() -> None:
    """Numbering of the older findings never moves (as for the capability type)."""
    reading = _reading(
        [
            _step("OQ-01", "maks. 18 cm", "URS-XY100-004"),
            _step("OQ-02", "minimal 70 kN", "URS-XY100-005"),
        ],
        [_row("URS-XY100-004", "OQ-01"), _row("URS-XY100-005", "OQ-02")],
    )
    reqs = [
        _req("URS-XY100-004", "Tinggi maksimal 18 mm."),
        _req("URS-XY100-005", "Gaya tekan minimal 80 kN."),
    ]
    rows = draft_rows(reading, Traceability(requirements=reqs), "id")
    found = draft_findings(reading, rows)
    assert [(f.type, f.test_step) for f in found] == [
        ("ac_deviates_from_urs", "OQ-02"),
        ("unit_error", "OQ-01"),
    ]


# --- Not compared, with the reason -------------------------------------------------------

SINGLE = "the URS states a single number; the acceptance criterion does not"
TWO_SIDED = "the URS states a two-sided range"
FORCE_80 = "Gaya tekan minimal 80 kN."


@pytest.mark.parametrize(
    ("urs", "ac", "reason"),
    [
        # an AC limit, range or tolerance around a URS single number waits for the session
        ("Mesin memiliki 36 stasiun punch.", "minimal 32 stasiun", SINGLE),
        ("Suplai listrik 380 V, 3 fase.", "380 V ± 10 %", SINGLE),
        ("Tinggi plafon 3.000 mm.", "tinggi maks. 3.200 mm", SINGLE),  # no direction read
        ("Kecepatan dapat diatur pada rentang 20–70 rpm.", "20 s/d 70 rpm", TWO_SIDED),
        ("Kecepatan dapat diatur pada rentang 20–70 rpm.", "25 s/d 60 rpm", TWO_SIDED),
        ("Bagian kontak dari SS 316L.", "SS 316L", "acceptance criterion: no number"),
        (FORCE_80, "Gaya tekan tercapai", "acceptance criterion: no number"),
        (FORCE_80, "maks. 20–30 kN", "acceptance criterion: not read as a limit"),
        (FORCE_80, "minimal 1,500 kN", "acceptance criterion: number reads two ways"),
        ("Bagian kontak dari SS 316L.", "minimal 80 kN", "URS limit: no number"),
        ("Kecepatan maks. 1,500 rpm.", "maks. 1000 rpm", "URS limit: number reads two ways"),
        ("Changeover maksimal 120 menit.", "maks. 2 kali", "units do not compare (kali and menit)"),
        (
            "Gaya tekan minimal 80 kN.",
            "80 kN ± 5 kN",
            "the acceptance criterion is a tolerance around a nominal value",
        ),
    ],
)  # fmt: skip
def test_a_value_that_cannot_be_compared_is_not_compared_with_its_reason(
    urs: str, ac: str, reason: str
) -> None:
    row, found = _judge(urs, ac)
    assert (row.not_compared, found) == (reason, [])
    assert [(c.deviates, c.not_compared) for c in row.traced] == [(False, reason)]


# --- The table decides; disagreements are not compared -----------------------------------

FORCE = _req("URS-XY100-004", "Gaya tekan minimal 80 kN.")
PRE = _req("URS-XY100-005", "Gaya pra-kompresi minimal 20 kN.")


def _rows(
    steps: Sequence[StepReading], rows: Sequence[TraceRow], reqs: Sequence[Requirement]
) -> tuple[list[DraftRow], list[DraftFinding]]:
    reading = _reading(steps, rows)
    out = draft_rows(reading, Traceability(requirements=list(reqs)), "id")
    return out, draft_findings(reading, out)


def test_a_step_whose_header_names_another_requirement_is_not_compared() -> None:
    rows, found = _rows(
        [_step("OQ-01", "minimal 15 kN", "URS-XY100-005")],
        [_row("URS-XY100-004", "OQ-01")],
        [FORCE, PRE],
    )
    assert rows[0].not_compared == (
        "the Test Step names URS-XY100-005; the traceability table lists it under URS-XY100-004"
    )
    assert found == []


def test_a_step_the_table_does_not_list_is_not_compared() -> None:
    rows, found = _rows([_step("OQ-01", "minimal 15 kN", "URS-XY100-004")], [], [FORCE])
    assert (rows[0].traced, rows[0].not_compared) == ((), "not in the traceability table")
    assert found == []


def test_a_step_without_a_requirement_in_its_header_follows_the_table() -> None:
    rows, found = _rows(
        [_step("OQ-01", "minimal 15 kN")], [_row("URS-XY100-004", "OQ-01")], [FORCE]
    )
    assert rows[0].not_compared is None
    assert [f.requirement for f in found] == ["URS-XY100-004"]


def test_a_step_listed_under_two_requirements_is_compared_with_each() -> None:
    rows, found = _rows(
        [_step("OQ-01", "minimal 50 kN", "URS-XY100-004", "URS-XY100-005")],
        [_row("URS-XY100-004", "OQ-01"), _row("URS-XY100-005", "OQ-01")],
        [FORCE, PRE],
    )
    assert [(c.urs.requirement, c.deviates) for c in rows[0].traced] == [
        ("URS-XY100-004", True),
        ("URS-XY100-005", False),
    ]
    assert rows[0].not_compared is None
    assert [(f.test_step, f.requirement) for f in found] == [("OQ-01", "URS-XY100-004")]


def test_a_step_tracing_to_a_requirement_the_urs_lacks_is_not_judged() -> None:
    rows, found = _rows(
        [_step("OQ-01", "minimal 15 kN", "URS-XY100-099")],
        [_row("URS-XY100-099", "OQ-01")],
        [FORCE],
    )
    assert rows[0].not_compared == "URS limit: requirement not read from the URS"
    assert found == []


# --- requirement_not_tested ---------------------------------------------------------------


def _untested(
    steps: Sequence[StepReading], rows: Sequence[TraceRow], body: str = ""
) -> list[DraftFinding]:
    reading = _reading(steps, rows, body)
    return [
        f
        for f in draft_findings(reading, draft_rows(reading, Traceability(), "id"))
        if f.type == "requirement_not_tested"
    ]


def test_a_row_whose_test_steps_the_draft_never_prints_is_not_tested() -> None:
    """The table itself prints every planned id, so only the pages outside it count."""
    row = _row("URS-XY100-002", "OQ-02")
    (f,) = _untested([_step("OQ-01", "minimal 80 kN")], [_row("URS-XY100-004", "OQ-01"), row])
    assert (f.row, f.test_step, f.requirement) == ("URS-XY100-002", None, "URS-XY100-002")
    assert f.citations == (row.citation,)
    assert f.detail == (
        "The traceability table lists URS-XY100-002 under OQ-02, but the draft has no"
        " such Test Step: the requirement is not tested."
    )


def test_a_row_with_a_test_step_read_is_tested() -> None:
    assert _untested([_step("OQ-01", "minimal 80 kN")], [_row("URS-XY100-004", "OQ-01")]) == []


def test_a_step_whose_reading_was_dropped_still_counts_as_printed() -> None:
    """OQ-03 is printed on page 1 but its reading did not pass the citation check."""
    body = "Langkah uji OQ-03\nKriteria Mesin berhenti"
    assert _untested([], [_row("URS-XY100-007", "OQ-03")], body) == []


def test_one_printed_step_of_a_row_is_enough() -> None:
    steps = [_step("OQ-01", "minimal 80 kN")]
    assert _untested(steps, [_row("URS-XY100-004", "OQ-09", "OQ-01")]) == []


def test_a_requirement_in_two_rows_is_judged_once_over_all_its_steps() -> None:
    steps = [_step("OQ-01", "minimal 80 kN")]
    assert _untested(steps, [_row("URS-XY100-004", "OQ-09"), _row("URS-XY100-004", "OQ-01")]) == []
    one, two = _row("URS-XY100-004", "OQ-08"), _row("URS-XY100-004", "OQ-09")
    (f,) = _untested(steps, [one, two])
    assert f.citations == (one.citation, two.citation)
    assert "under OQ-08, OQ-09" in f.detail


def test_an_id_inside_a_longer_id_is_not_the_step() -> None:
    (f,) = _untested([_step("OQ-22", "maks. 85 dBA")], [_row("URS-XY100-009", "OQ-2")])
    assert f.row == "URS-XY100-009"


# --- Comparators available: shown only, never a finding ------------------------------------

FAT = Protocol("FAT-XY100", 0, "FAT", dt.date(2026, 1, 22), dt.date(2026, 2, 1))
SAT = Protocol("SAT-XY100", 0, "SAT", dt.date(2026, 3, 1), dt.date(2026, 3, 10))
BLANK = _Value(kind="none", min=None, max=None, number=None, unit=None, text=None, present=None)


def _vendor_step(protocol: Protocol, step: str, observed: str) -> StepFact:
    quote = f"{step} Gaya tekan {observed} Lulus"
    cite = Citation(protocol.doc, 0, 1, quote)
    return StepFact(protocol, step, "Gaya tekan", "≥ 80 kN", observed, "pass", cite, "id", BLANK)


def _design(name: str, printed: str) -> RowFact:
    fact = DesignFact("DS-XY100", 1, Range(min=90, unit="kN"))
    return RowFact(f"DS-XY100/{name}", name, printed, fact, Citation("DS-XY100", 1, 2, printed))


def _linked(steps: Sequence[StepFact], rows: Sequence[RowFact]) -> Linked:
    facts = RequirementFacts("URS-XY100-004", None, site_only=False, transport_sensitive=False)
    return Linked(facts, Coverage("gap", "no FAT/SAT step addresses it"), tuple(steps), tuple(rows))


def test_each_step_shows_the_vendor_facts_of_its_requirement_by_document() -> None:
    fat1, fat2 = _vendor_step(FAT, "FAT-04", "85 kN"), _vendor_step(FAT, "FAT-05", "88 kN")
    sat = _vendor_step(SAT, "SAT-02", "84 kN")
    design = _design("Gaya tekan maks.", "100 kN")
    traced = Traceability(
        requirements=[FORCE, PRE], linked={"URS-XY100-004": _linked([fat1, sat, fat2], [design])}
    )
    reading = _reading(
        [_step("OQ-01", "minimal 80 kN"), _step("OQ-02", "minimal 20 kN")],
        [_row("URS-XY100-004", "OQ-01"), _row("URS-XY100-005", "OQ-02")],
    )
    one, two = draft_rows(reading, traced, "id")

    assert one.traced[0].comparators == (
        Comparator("FAT-XY100", 0, "FAT", (
            VendorFact("FAT-04", "85 kN", fat1.citation),
            VendorFact("FAT-05", "88 kN", fat2.citation),
        )),
        Comparator("SAT-XY100", 0, "SAT", (VendorFact("SAT-02", "84 kN", sat.citation),)),
        Comparator("DS-XY100", 1, "design", (
            VendorFact("Gaya tekan maks.", "100 kN", design.citation),
        )),
    )  # fmt: skip
    assert two.traced[0].comparators == ()  # none
    assert draft_findings(reading, [one, two]) == []
