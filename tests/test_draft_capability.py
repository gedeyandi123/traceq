"""``ac_outside_documented_capability`` (spec #375, ticket S2a): a Test Step whose Acceptance
Criterion demands more than the Datasheet states the Equipment can do, judged by code over
values read with a verified citation. Built on facts as the readers keep them; no model.

The rule tests inputs the package does not hold (other units, phrasings and values): with two
planted defects a rule that only fits the author's key could not be told from one that works.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from traceq.documents import CorpusDocument, Page
from traceq.review.draft import DraftReading, DraftRow, StepReading, TraceRow, draft_rows
from traceq.review.draft_rules import (
    NOT_REVIEWED_LABEL,
    Datasheet,
    DraftFinding,
    draft_findings,
)
from traceq.review.printed import read_printed
from traceq.traceability import Citation, Linked, Requirement, RowFact, Traceability
from traceq.traceability.coverage import Coverage, DesignFact, RequirementFacts
from traceq.traceability.values import Number

DOC = CorpusDocument(
    "OQ-XY100", 0, "oq_protocol", "born_digital", "id", Path("draft.pdf"), "d" * 64
)
URS = "URS-XY100"
REQ = "URS-XY100-004"
DS_PAGE = (
    "Technical Datasheet\n"
    "Performance\n"
    "Turret speed 20–70 rpm\n"
    "Maximum main compression force 100 kN\n"
    "Maximum tablet diameter 25 mm\n"
    "Control and safety\n"
    "Compression force measurement accuracy (max. ±) 1 % FS\n"
    "Feeder paddle speed 10–60 rpm\n"
    "Utilities\n"
    "Maximum power draw 15 kW\n"
    "Compressed air 6–7 bar\n"
)
SHEET = Datasheet("DS-XY100", 1, "en", (DS_PAGE,))


def _step(sid: str, ac: str, *reqs: str) -> StepReading:
    return StepReading(
        sid, reqs, ac, read_printed(ac, "id"), Citation(DOC.doc_id, 0, 1, f"Kriteria {ac}")
    )


def _row(req: str, *steps: str) -> TraceRow:
    return TraceRow(req, steps, Citation(DOC.doc_id, 0, 2, f"{req} {' '.join(steps)}"))


def _req(rid: str, sentence: str) -> Requirement:
    return Requirement(rid, sentence, Citation(URS, 1, 1, f"{rid} Ya {sentence}"), True)


def _fact(name: str, printed: str, doc: str = "DS-XY100", rev: int = 1) -> RowFact:
    line = f"{name} {printed}"
    return RowFact(
        f"{doc}/{name}",
        name,
        printed,
        DesignFact(doc, rev, Number(value=0.0, unit="")),
        Citation(doc, rev, 1, line),
    )


def _linked(*rows: RowFact) -> Linked:
    facts = RequirementFacts(REQ, None, site_only=False, transport_sensitive=False)
    return Linked(facts, Coverage("gap", "no FAT/SAT step addresses it"), (), tuple(rows))


def _judge(
    ac: str,
    *facts: RowFact,
    urs: str = "Gaya tekan minimal 80 kN.",
    sheets: Sequence[Datasheet] = (SHEET,),
    header: Sequence[str] = (REQ,),
) -> tuple[list[DraftRow], list[DraftFinding]]:
    """One Test Step OQ-01 the table traces to ``REQ``, linked to the Datasheet ``facts``."""
    steps = [_step("OQ-01", ac, *header)]
    rows = [_row(REQ, "OQ-01")]
    page1 = "\n".join(f"Langkah uji {s.id}\nKriteria {s.printed}" for s in steps)
    pages = (Page(1, page1), Page(2, "Matriks\n" + rows[0].citation.quote))
    reading = DraftReading(DOC, pages, steps, rows)
    traced = Traceability(requirements=[_req(REQ, urs)], linked={REQ: _linked(*facts)})
    out = draft_rows(reading, traced, "id")
    return out, draft_findings(reading, out, sheets)


def _types(found: list[DraftFinding]) -> list[str]:
    return [f.type for f in found if f.type == "ac_outside_documented_capability"]


MAX_FORCE = _fact("Maximum main compression force", "100 kN")
MAX_DIAMETER = _fact("Maximum tablet diameter", "25 mm")
SPEED = _fact("Turret speed", "20–70 rpm")
ACCURACY = _fact("Compression force measurement accuracy (max. ±)", "1 % FS")

# --- A maximum bound -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ac", "fact", "finding"),
    [
        ("minimal 105 kN", MAX_FORCE, True),  # demands more than the maximum
        ("≥ 100 kN", MAX_FORCE, False),  # at the maximum, not above it
        ("minimal 95 kN", MAX_FORCE, False),
        ("> 100 kN", MAX_FORCE, True),  # strictly more than the maximum: unreachable
        ("110 kN", MAX_FORCE, True),  # a single number above the maximum
        ("100 kN", MAX_FORCE, False),
        ("90 s/d 110 kN", MAX_FORCE, True),  # a range that reaches above it
        ("90 s/d 100 kN", MAX_FORCE, False),
        ("maks. 120 kN", MAX_FORCE, False),  # an upper limit alone demands nothing
        ("≤ 25 mm", MAX_DIAMETER, False),
        ("minimal 26 mm", MAX_DIAMETER, True),
    ],
)
def test_a_maximum_bound_is_outside_when_the_ac_demands_more_than_it(
    ac: str, fact: RowFact, finding: bool
) -> None:
    _, found = _judge(ac, fact)
    assert _types(found) == (["ac_outside_documented_capability"] if finding else [])


def test_the_finding_cites_the_ac_and_the_datasheet_row_and_says_how_it_was_judged() -> None:
    rows, (f,) = _judge("minimal 105 kN", MAX_FORCE)
    assert f.type == "ac_outside_documented_capability"
    assert (f.test_step, f.row, f.requirement) == ("OQ-01", None, REQ)
    assert f.citations == (
        Citation(DOC.doc_id, 0, 1, "Kriteria minimal 105 kN"),
        Citation("DS-XY100", 1, 1, "Maximum main compression force 100 kN"),
    )
    assert f.ac == rows[0].step.value
    assert f.capability == read_printed("100 kN", "en")
    assert f.detail == (
        "OQ-01 requires at least 105 kN, above the maximum 100 kN the Datasheet DS-XY100"
        " states: the limit may not be reachable."
    )
    assert f.label == NOT_REVIEWED_LABEL == "not reviewed by a practitioner"


def test_the_detail_is_written_from_the_values_not_from_the_quote() -> None:
    _, (a,) = _judge("minimal 105 kN", MAX_FORCE)
    shorter = RowFact(
        MAX_FORCE.id,
        MAX_FORCE.name,
        MAX_FORCE.printed,
        MAX_FORCE.fact,
        Citation("DS-XY100", 1, 1, "Maximum main"),
    )
    _, (b,) = _judge("minimal 105 kN", shorter)
    assert a.detail == b.detail


# --- An operating span -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ac", "finding"),
    [
        ("20 s/d 70 rpm", False),
        ("25 s/d 60 rpm", False),
        ("20 s/d 80 rpm", True),  # reaches above the span
        ("15 s/d 70 rpm", True),  # reaches below it
        ("75 rpm", True),
        ("50 rpm", False),
        ("minimal 80 rpm", True),  # demands a speed above the span
        ("minimal 30 rpm", False),
        ("maks. 10 rpm", True),  # an upper limit below the span's start
        ("maks. 40 rpm", False),
    ],
)
def test_an_operating_span_is_outside_when_the_ac_reaches_beyond_it(ac: str, finding: bool) -> None:
    _, found = _judge(ac, SPEED)
    assert _types(found) == (["ac_outside_documented_capability"] if finding else [])


def test_the_span_detail() -> None:
    _, (f,) = _judge("20 s/d 80 rpm", SPEED)
    assert f.detail == (
        "OQ-01 requires 20 to 80 rpm, outside the span 20 to 70 rpm the Datasheet DS-XY100"
        " states: the limit may not be reachable."
    )


# --- An accuracy floor -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ac", "finding"),
    [
        ("maks. ± 0,5 % FS", True),  # tighter than the stated accuracy
        ("maks. ± 1 % FS", False),
        ("maks. ± 2 % FS", False),  # looser: not a capability problem
        ("± 0,5 % FS", True),
        ("maks. ± 0,5 %", False),  # another unit: not compared
    ],
)
def test_an_accuracy_floor_is_outside_when_the_ac_is_tighter_than_the_stated_accuracy(
    ac: str, finding: bool
) -> None:
    _, found = _judge(ac, ACCURACY, urs="Akurasi maksimal ±1% dari skala penuh.")
    assert _types(found) == (["ac_outside_documented_capability"] if finding else [])


def test_the_accuracy_detail() -> None:
    _, (f,) = _judge("maks. ± 0,5 % FS", ACCURACY, urs="Akurasi maksimal ±1% dari skala penuh.")
    assert f.detail == (
        "OQ-01 requires at most 0.5 % FS, tighter than the 1 % FS accuracy the Datasheet"
        " DS-XY100 states: the limit may not be reachable."
    )


# --- Phrasings and units outside the package -----------------------------------------------


@pytest.mark.parametrize(
    ("ac", "fact", "finding"),
    [
        ("minimal 35 mm", _fact("Max. fill depth", "18 mm"), True),
        ("minimal 35 mm", _fact("Kedalaman pengisian maksimum", "18 mm"), True),
        ("minimal 35 mm", _fact("Fill depth (maks.)", "18 mm"), True),
        ("maks. ± 0,1 %", _fact("Akurasi pengukuran (maks. ±)", "0,5 %"), True),
        ("maks. ± 0,5 %", _fact("Akurasi pengukuran (maks. ±)", "0,5 %"), False),
        ("minimal 35 mm", _fact("Fill depth", "18 mm"), False),  # no stated kind: not typed
        ("minimal 105 N", MAX_FORCE, False),  # another unit: unit_error's, not this rule's
        ("minimal 105", MAX_FORCE, False),
    ],
)
def test_other_phrasings_and_units(ac: str, fact: RowFact, finding: bool) -> None:
    sheet = Datasheet("DS-XY100", 1, "id", (f"{fact.name} {fact.printed}\n",))
    _, found = _judge(ac, fact, sheets=[sheet])
    assert _types(found) == (["ac_outside_documented_capability"] if finding else [])


# --- Only a Datasheet row whose name the page holds ----------------------------------------


def test_a_row_whose_name_the_datasheet_page_does_not_hold_is_not_a_comparator() -> None:
    invented = _fact("Maximum clamping force", "100 kN")
    _, found = _judge("minimal 105 kN", invented)
    assert _types(found) == []


def test_the_name_is_checked_on_the_page_of_its_own_citation() -> None:
    other_page = Datasheet("DS-XY100", 1, "en", ("Technical Datasheet\n", DS_PAGE))
    _, found = _judge("minimal 105 kN", MAX_FORCE, sheets=[other_page])
    assert _types(found) == []  # the citation says page 1, which does not print the name


def test_a_comparator_of_a_document_that_is_no_datasheet_is_not_used() -> None:
    cert = _fact("Maximum main compression force", "100 kN", doc="CERT-XY100", rev=0)
    _, found = _judge("minimal 105 kN", cert)  # CERT-XY100 is not among the datasheets
    assert _types(found) == []
    _, found = _judge("minimal 105 kN", MAX_FORCE, sheets=[])
    assert _types(found) == []


def test_the_datasheet_revision_must_be_the_one_cited() -> None:
    old = Datasheet("DS-XY100", 0, "en", (DS_PAGE,))
    _, found = _judge("minimal 105 kN", MAX_FORCE, sheets=[old])
    assert _types(found) == []


# --- Utilities are no comparator --------------------------------------------------------------


def test_rows_under_a_utilities_heading_are_excluded_by_the_page_text() -> None:
    power = _fact("Maximum power draw", "15 kW")
    _, found = _judge("minimal 20 kW", power)
    assert _types(found) == []
    # The same row above the heading is a capability like any other.
    above = Datasheet(
        "DS-XY100",
        1,
        "en",
        ("Performance\nMaximum power draw 15 kW\nUtilities\nCompressed air 6–7 bar\n",),
    )
    _, found = _judge("minimal 20 kW", power, sheets=[above])
    assert _types(found) == ["ac_outside_documented_capability"]


def test_a_utilities_heading_on_an_earlier_page_covers_the_rows_after_it() -> None:
    power = _fact("Maximum power draw", "15 kW")
    sheet = Datasheet("DS-XY100", 1, "en", ("Utilities\n", "Maximum power draw 15 kW\n"))
    fact = RowFact(power.id, power.name, power.printed, power.fact, Citation("DS-XY100", 1, 2, "x"))
    _, found = _judge("minimal 20 kW", fact, sheets=[sheet])
    assert _types(found) == []


@pytest.mark.parametrize(
    "heading",
    [
        "Utilitas dan lingkungan",
        "5. Utilitas",
        "UTILITIES",
        "Site utilities",
        "Utilities and services",
        "Utilities & services",
        "Utilities:",
        "5.1 Utilities",
        "5.1. Utilitas:",
        "  utilities  ",
        "Utilitas site",
        "Utility connections",
        "Electrical utilities",
    ],
)
def test_utilities_headings_in_other_phrasings(heading: str) -> None:
    sheet = Datasheet("DS-XY100", 1, "en", (f"{heading}\nMaximum power draw 15 kW\n",))
    _, found = _judge("minimal 20 kW", _fact("Maximum power draw", "15 kW"), sheets=[sheet])
    assert _types(found) == []


@pytest.mark.parametrize(
    "line",
    [
        "All utilities must be provided by the site before installation.",
        "Utilities are supplied by the site.",
        "The maximum utilities load is stated below",
        "Maximum utilities load",
        "See the utilities drawing 12",
    ],
)
def test_a_line_that_only_mentions_utilities_is_not_a_heading(line: str) -> None:
    sheet = Datasheet("DS-XY100", 1, "en", (f"Performance\n{line}\nMaximum power draw 15 kW\n",))
    _, found = _judge("minimal 20 kW", _fact("Maximum power draw", "15 kW"), sheets=[sheet])
    assert _types(found) == ["ac_outside_documented_capability"]


def test_the_utilities_section_ends_at_the_next_heading() -> None:
    """Rows after the section, under another heading, are judged like any other row."""
    sheet = Datasheet(
        "DS-XY100",
        1,
        "en",
        (
            "Performance\nTurret speed 20-70 rpm\nUtilities\nMaximum power draw 15 kW\n"
            "Compressed air 6-7 bar\nControl and safety\nMaximum main compression force 100 kN\n",
        ),
    )
    power = _fact("Maximum power draw", "15 kW")
    _, inside = _judge("minimal 20 kW", power, sheets=[sheet])
    assert _types(inside) == []
    _, after = _judge("minimal 105 kN", MAX_FORCE, sheets=[sheet])
    assert _types(after) == ["ac_outside_documented_capability"]


@pytest.mark.parametrize("next_heading", ["Control and safety", "6. Control", "Safety:", "General"])
def test_a_numbered_or_plain_heading_ends_the_section(next_heading: str) -> None:
    sheet = Datasheet(
        "DS-XY100",
        1,
        "en",
        (
            f"Utilities\nCompressed air 6-7 bar\n{next_heading}\n"
            "Maximum main compression force 100 kN\n",
        ),
    )
    _, found = _judge("minimal 105 kN", MAX_FORCE, sheets=[sheet])
    assert _types(found) == ["ac_outside_documented_capability"]


def test_a_second_utilities_section_excludes_its_own_rows_only() -> None:
    sheet = Datasheet(
        "DS-XY100",
        1,
        "en",
        (
            "Utilities\nMaximum power draw 15 kW\nPerformance\n"
            "Maximum main compression force 100 kN\nSite utilities\n"
            "Maximum water flow 5 m3/h\n",
        ),
    )
    _, force = _judge("minimal 105 kN", MAX_FORCE, sheets=[sheet])
    assert _types(force) == ["ac_outside_documented_capability"]
    _, flow = _judge("minimal 6 m3/h", _fact("Maximum water flow", "5 m3/h"), sheets=[sheet])
    assert _types(flow) == []


def test_a_utilities_section_runs_over_a_page_until_a_heading() -> None:
    def on_page_2(fact: RowFact) -> RowFact:
        return RowFact(fact.id, fact.name, fact.printed, fact.fact, Citation("DS-XY100", 1, 2, "x"))

    sheet = Datasheet(
        "DS-XY100",
        1,
        "en",
        (
            "Utilities\nCompressed air 6-7 bar\n",
            "Maximum power draw 15 kW\nPerformance\nMaximum main compression force 100 kN\n",
        ),
    )
    power = on_page_2(_fact("Maximum power draw", "15 kW"))
    _, inside = _judge("minimal 20 kW", power, sheets=[sheet])
    assert _types(inside) == []
    _, after = _judge("minimal 105 kN", on_page_2(MAX_FORCE), sheets=[sheet])
    assert _types(after) == ["ac_outside_documented_capability"]


def test_the_row_being_judged_is_never_taken_for_a_heading() -> None:
    """A row line with no digit looks like a heading; the row itself must not end its section."""
    sheet = Datasheet("DS-XY100", 1, "en", ("Utilities\nMaximum power draw\n15 kW\n",))
    _, found = _judge("minimal 20 kW", _fact("Maximum power draw", "15 kW"), sheets=[sheet])
    assert _types(found) == []


@pytest.mark.parametrize(
    "header",
    [
        "Parameter Value Unit",
        "Parameter Specification",
        "Item Description",
        "No. Item Remarks",
        "PARAMETER  SATUAN  NILAI",
        "Parameter Spesifikasi Keterangan",
        "Requirement Range Limit",
    ],
)
def test_a_table_column_header_under_utilities_does_not_end_the_section(header: str) -> None:
    """A column-header line holds no value, as a heading does not; its words are the table's."""
    sheet = Datasheet("DS-XY100", 1, "en", (f"Utilities\n{header}\nMaximum power draw 15 kW\n",))
    _, found = _judge("minimal 20 kW", _fact("Maximum power draw", "15 kW"), sheets=[sheet])
    assert _types(found) == []


def test_a_running_page_header_does_not_end_a_utilities_section() -> None:
    """Chosen behaviour: a first line that opens two or more pages is a running header, never a
    heading, so the section of page 1 runs on into page 2 past it."""
    pages = (
        "Technical Datasheet\nUtilities\nCompressed air 6-7 bar\n",
        "Technical Datasheet\nMaximum power draw 15 kW\n",
    )
    sheet = Datasheet("DS-XY100", 1, "en", pages)
    power = _fact("Maximum power draw", "15 kW")
    row = RowFact(power.id, power.name, power.printed, power.fact, Citation("DS-XY100", 1, 2, "x"))
    _, found = _judge("minimal 20 kW", row, sheets=[sheet])
    assert _types(found) == []


def test_a_first_line_of_one_page_only_is_a_heading_like_any_other() -> None:
    """A first line that no other page repeats is not a running header: it is a heading."""
    pages = (
        "Utilities\nCompressed air 6-7 bar\n",
        "Control and safety\nMaximum power draw 15 kW\n",
    )
    sheet = Datasheet("DS-XY100", 1, "en", pages)
    power = _fact("Maximum power draw", "15 kW")
    row = RowFact(power.id, power.name, power.printed, power.fact, Citation("DS-XY100", 1, 2, "x"))
    _, found = _judge("minimal 20 kW", row, sheets=[sheet])
    assert _types(found) == ["ac_outside_documented_capability"]


def test_a_text_valued_row_under_utilities_ends_the_section_a_known_limit() -> None:
    """Pinned limit: a row with a text value and no digit ("Power supply Three phase") cannot be
    told from a heading by its text, so it ends the section and the rows after it are judged.
    The CHANGELOG names this."""
    sheet = Datasheet(
        "DS-XY100", 1, "en", ("Utilities\nPower supply Three phase\nMaximum power draw 15 kW\n",)
    )
    _, found = _judge("minimal 20 kW", _fact("Maximum power draw", "15 kW"), sheets=[sheet])
    assert _types(found) == ["ac_outside_documented_capability"]


def test_a_row_that_only_mentions_utilities_in_its_name_is_not_excluded() -> None:
    sheet = Datasheet("DS-XY100", 1, "en", ("Maximum utilities load 15 kW\n",))
    _, found = _judge("minimal 20 kW", _fact("Maximum utilities load", "15 kW"), sheets=[sheet])
    assert _types(found) == ["ac_outside_documented_capability"]


# --- No link, no finding -------------------------------------------------------------------


def test_with_no_linked_datasheet_row_nothing_is_raised() -> None:
    rows, found = _judge("minimal 105 kN")
    assert _types(found) == []
    assert rows[0].traced[0].comparators == ()


def test_a_step_whose_header_names_another_requirement_is_not_judged() -> None:
    _, found = _judge("minimal 105 kN", MAX_FORCE, header=("URS-XY100-005",))
    assert _types(found) == []


def test_a_value_read_two_ways_or_not_as_a_limit_is_not_judged() -> None:
    for ac in ("Gaya tekan tercapai", "minimal 1,500 kN", "100 kN ± 5 kN"):
        _, found = _judge(ac, MAX_FORCE)
        assert _types(found) == [], ac
    ambiguous = _fact("Maximum main compression force", "1,500 kN")
    sheet = Datasheet("DS-XY100", 1, "id", ("Maximum main compression force 1,500 kN\n",))
    _, found = _judge("minimal 105 kN", ambiguous, sheets=[sheet])
    assert _types(found) == []


def test_two_steps_linked_to_one_row_each_get_their_own_finding() -> None:
    steps = [_step("OQ-01", "minimal 105 kN", REQ), _step("OQ-02", "minimal 120 kN", REQ)]
    rows = [_row(REQ, "OQ-01", "OQ-02")]
    page1 = "\n".join(f"Langkah uji {s.id}\nKriteria {s.printed}" for s in steps)
    reading = DraftReading(DOC, (Page(1, page1), Page(2, rows[0].citation.quote)), steps, rows)
    traced = Traceability(
        requirements=[_req(REQ, "Gaya tekan minimal 80 kN.")], linked={REQ: _linked(MAX_FORCE)}
    )
    found = draft_findings(reading, draft_rows(reading, traced, "id"), [SHEET])
    assert [(f.type, f.test_step) for f in found] == [
        ("ac_outside_documented_capability", "OQ-01"),
        ("ac_outside_documented_capability", "OQ-02"),
    ]


def test_it_is_raised_beside_a_deviation_and_after_the_existing_findings() -> None:
    """A step that the URS rule also flags keeps its finding; the new type is added after the
    existing ones, so the numbering of the older findings does not move."""
    _, found = _judge("minimal 75 kN", MAX_FORCE)  # looser than the URS: ac_deviates_from_urs
    assert [f.type for f in found] == ["ac_deviates_from_urs"]
    _, found = _judge("minimal 105 kN", MAX_FORCE)
    assert [f.type for f in found] == ["ac_outside_documented_capability"]


def test_the_existing_types_carry_no_practitioner_label() -> None:
    _, found = _judge("minimal 75 kN", MAX_FORCE)
    assert [f.label for f in found] == [None]
