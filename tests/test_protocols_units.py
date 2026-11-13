"""Deterministic units of drafting: the AC validator and which requirements get a drafted
Test Step under the ``vendor_reuse`` run setting (spec #29, ticket #39)."""

from __future__ import annotations

from traceq.protocols import HUMAN, needs_draft, validate_acceptance
from traceq.traceability import Citation
from traceq.traceability.values import Number, Present, Range

URS: tuple[str, int] = ("X-URS", 1)
SOURCES: dict[tuple[str, int], list[str]] = {
    URS: [
        "X-01 Ya Kapasitas minimal 100.000 tablet/jam.\nX-02 Ya Kecepatan turret 20–70 rpm.",
        "X-03 Ya Pintu pelindung menghentikan mesin.",
    ]
}
SPEED = Range(min=20, max=70, unit="rpm")


def _cite(quote: str, page: int = 1, doc: tuple[str, int] = URS) -> Citation:
    return Citation(doc[0], doc[1], page, quote)


def test_an_ac_copied_from_a_verified_citation_is_kept() -> None:
    c = _cite("Kecepatan turret 20–70 rpm.")
    ac = validate_acceptance(SPEED, c, SOURCES)
    assert (ac.value, ac.citation, ac.flag) == (SPEED, c, None)
    assert ac.sourced


def test_an_ac_without_a_citation_is_emptied_and_flagged() -> None:
    ac = validate_acceptance(SPEED, None, SOURCES)
    assert (ac.value, ac.citation) == (None, None)
    assert ac.flag == f"{HUMAN}: no source cited"
    assert not ac.sourced


def test_a_citation_without_the_value_empties_the_ac() -> None:
    """The quote is on the page, but it states 20-70 rpm, not 20-60 rpm."""
    ac = validate_acceptance(
        Range(min=20, max=60, unit="rpm"), _cite("Kecepatan turret 20–70 rpm."), SOURCES
    )
    assert (ac.value, ac.citation) == (None, None)
    assert ac.flag == f"{HUMAN}: value not in the quote"


def test_a_quote_not_on_the_cited_page_empties_the_ac() -> None:
    wrong_page = validate_acceptance(SPEED, _cite("Kecepatan turret 20–70 rpm.", 2), SOURCES)
    invented = validate_acceptance(
        Number(value=2, unit="s"), _cite("Mesin berhenti dalam 2 s.", 2), SOURCES
    )
    no_page = validate_acceptance(SPEED, _cite("Kecepatan turret 20–70 rpm.", 3), SOURCES)
    for ac in (wrong_page, invented, no_page):
        assert (ac.value, ac.citation, ac.flag) == (None, None, f"{HUMAN}: quote not on the page")


def test_a_citation_of_a_document_not_given_empties_the_ac() -> None:
    ac = validate_acceptance(SPEED, _cite("Kecepatan turret 20–70 rpm.", doc=("X-URS", 0)), SOURCES)
    assert (ac.value, ac.flag) == (None, f"{HUMAN}: source not given")


def test_no_ac_proposed_is_flagged_for_a_human() -> None:
    ac = validate_acceptance(None, _cite("Pintu pelindung menghentikan mesin.", 2), SOURCES)
    assert (ac.value, ac.citation) == (None, None)
    assert ac.flag == f"{HUMAN}: no acceptance criterion in the sources"


def test_a_present_ac_needs_only_a_verified_quote() -> None:
    c = _cite("Pintu pelindung menghentikan mesin.", 2)
    assert validate_acceptance(Present(), c, SOURCES).value == Present()


# --- vendor_reuse ---------------------------------------------------------------------


def test_with_vendor_reuse_a_requirement_the_vendor_covered_gets_no_draft() -> None:
    drafted = ["partial", "site_only", "gap", "conflict", None]
    assert [c for c in [*drafted, "covered_by_vendor"] if needs_draft(c, vendor_reuse=True)] == (
        drafted
    )


def test_without_vendor_reuse_every_requirement_gets_a_draft() -> None:
    classes = ("covered_by_vendor", "partial", "site_only", "gap", "conflict", None)
    assert all(needs_draft(c, vendor_reuse=False) for c in classes)
