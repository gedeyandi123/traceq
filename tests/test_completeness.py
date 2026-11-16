"""The URS completeness check (spec #105, "What a run adds"): no LLM, on the pages the run read.

Printed requirement numbers that did not become a kept requirement, and URS text that no kept
requirement quotes. The shape of a number is learned only from the ids the model returned as
printed. Invented pages, and the TP-201 (dev) URS as the r7 run read it from the committed
ingest cache; nothing here opens a TP-202 document or run output.
"""

from __future__ import annotations

import json
from pathlib import Path

from traceq.traceability import Citation
from traceq.traceability.completeness import Missed, Unquoted, check

ROOT = Path(__file__).parents[1]
# URS-TP201 rev 1 as Docling read it for the r7 run (recordings/corpus-0.1.0 sha256).
TP201_URS = (
    ROOT
    / "recordings"
    / "haiku-r7"
    / "ingest"
    / "00fae3509f8199088287711a049583a1d400cfa4817a91a3ba7ea01e952b90f2-docling-1.json"
)

NUMBERED = [
    "User Requirements\nR-01 The press runs at 10 to 40 rpm.\nR-02 Guards are interlocked.\n"
    "R-03 The hopper holds 50 kg.",
    "Approval\nPrepared by A. Person\nR-04 Noise is below 80 dBA.",
]


def _cite(page: int, quote: str, doc: str = "URS-X", rev: int = 0) -> Citation:
    return Citation(doc, rev, page, quote)


def test_a_printed_number_the_model_did_not_return_is_missed() -> None:
    kept = {
        "R-01": _cite(1, "R-01 The press runs at 10 to 40 rpm."),
        "R-02": _cite(1, "Guards are interlocked."),
        "R-04": _cite(2, "R-04 Noise is below 80 dBA."),
    }
    got = check("URS-X", 0, NUMBERED, printed=list(kept), kept=kept, quotes=list(kept.values()))
    assert got.numbers == "checked"
    assert got.found == 4
    assert got.missed == (Missed("R-03", 1),)


def test_a_number_whose_requirement_the_citation_check_dropped_is_missed() -> None:
    """R-02 came back as printed, but its quote was not on the page: it teaches the shape and
    counts as missed."""
    kept = {
        "R-01": _cite(1, "R-01 The press runs at 10 to 40 rpm."),
        "R-03": _cite(1, "R-03 The hopper holds 50 kg."),
        "R-04": _cite(2, "R-04 Noise is below 80 dBA."),
    }
    got = check(
        "URS-X", 0, NUMBERED, printed=["R-02", *kept], kept=kept, quotes=list(kept.values())
    )
    assert got.missed == (Missed("R-02", 1),)


def test_only_printed_ids_teach_the_shape() -> None:
    """A system id (``URS-X-p1-01``) never teaches a shape: with no printed id there is no
    number to miss, and the check says so instead of reporting 0 missed."""
    pages = ["Operation\nThe dryer holds 40 to 80 °C.\nSee section 4.1 and URS-X-p1-02."]
    kept = {"URS-X-p1-01": _cite(1, "The dryer holds 40 to 80 °C.")}
    got = check("URS-X", 0, pages, printed=[], kept=kept, quotes=list(kept.values()))
    assert got.numbers == "not_applicable"
    assert got.found == 0
    assert got.missed == ()


def test_digit_runs_generalise_and_a_longer_token_is_not_a_number() -> None:
    pages = ["R-7 One.\nR-123 Two.\nR-12a is not a number, nor is XR-12, nor R-12-3.\nR-9."]
    kept = {"R-7": _cite(1, "R-7 One.")}
    got = check("URS-X", 0, pages, printed=["R-7"], kept=kept, quotes=list(kept.values()))
    assert got.missed == (Missed("R-123", 1), Missed("R-9", 1))
    assert got.found == 3


def test_unquoted_text_is_listed_by_page_with_adjacent_lines_merged() -> None:
    kept = {
        "R-01": _cite(1, "R-01 The press runs"),
        "R-02": _cite(1, "Guards are interlocked."),
        "R-04": _cite(2, "Noise is below 80 dBA."),
    }
    # A value quote of a kept requirement counts as quoted too.
    quotes = [*kept.values(), _cite(1, "holds 50 kg")]
    got = check("URS-X", 0, NUMBERED, printed=list(kept), kept=kept, quotes=quotes)
    assert got.unquoted == (
        Unquoted(1, "User Requirements"),
        Unquoted(2, "Approval\nPrepared by A. Person"),
    )


def test_a_quote_of_another_page_or_document_does_not_cover_text() -> None:
    pages = ["Scope\nThe press runs."]
    quotes = [_cite(2, "Scope"), _cite(1, "The press runs.", doc="URS-Y")]
    got = check("URS-X", 0, pages, printed=[], kept={}, quotes=quotes)
    assert got.unquoted == (Unquoted(1, "Scope\nThe press runs."),)


def _tp201_pages() -> list[str]:
    data = json.loads(TP201_URS.read_text(encoding="utf-8"))
    return [str(p["text"]) for p in data["pages"]]


def _tp201_kept(pages: list[str], drop: str = "") -> dict[str, Citation]:
    kept: dict[str, Citation] = {}
    for n, text in enumerate(pages, 1):
        for line in text.splitlines():
            rid = line.split(" ", 1)[0]
            if rid.startswith("URS-TP201-") and rid != drop and rid not in kept:
                kept[rid] = Citation("URS-TP201", 1, n, line.split(" ", 2)[2])
    return kept


def test_tp201_every_printed_number_became_a_requirement() -> None:
    pages = _tp201_pages()
    kept = _tp201_kept(pages)
    got = check("URS-TP201", 1, pages, printed=list(kept), kept=kept, quotes=list(kept.values()))
    assert (got.numbers, got.found, got.missed) == ("checked", 38, ())
    texts = [u.text for u in got.unquoted]
    assert texts[0].startswith("Spesifikasi Kebutuhan Pengguna (SKP)\nNomor dokumen URS-TP201")
    assert texts[0].endswith(
        "Tujuan\nDokumen ini menetapkan kebutuhan pengguna untuk TP-201."
        " Persyaratan dengan Kritis = Ya berdampak langsung pada mutu produk, keselamatan, atau"
        " integritas data.\n1. Kinerja\nNo. Kritis Persyaratan"
    )
    assert "2. Material dan konstruksi\nNo. Kritis Persyaratan" in texts
    assert any(t.startswith("Riwayat revisi") and "Pengesahan" in t for t in texts)
    assert {u.page for u in got.unquoted} == {1, 2}


def test_tp201_a_requirement_the_citation_check_dropped_is_missed() -> None:
    pages = _tp201_pages()
    kept = _tp201_kept(pages, drop="URS-TP201-027")
    printed = [*kept, "URS-TP201-027"]
    got = check("URS-TP201", 1, pages, printed=printed, kept=kept, quotes=list(kept.values()))
    assert got.missed == (Missed("URS-TP201-027", 2),)
    assert any("URS-TP201-027" in u.text for u in got.unquoted)
