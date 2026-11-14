"""Ingest of spreadsheets and scans, and the ingest cache (spec #29, ticket #36).

The scans are read from the recorded OCR output (``tests/conftest.py``), except in the one
test that runs the OCR model where it is installed.
"""

from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from traceq.documents import Corpus, CorpusDocument, OcrLine, OcrUnavailable, normalise, scan
from traceq.documents.pages import Quad
from traceq.documents.xlsx import read_xlsx
from traceq.runs.submission import ocr_entries
from traceq_dataset import render
from traceq_dataset.answer_key import load_key
from traceq_dataset.corpus import build_corpus
from traceq_dataset.world import load
from traceq_eval.citations import PageTexts
from traceq_eval.ocr import score_ocr
from traceq_eval.submission import OcrEntry, Submission, System

ROOT = Path(__file__).parents[1]
TP201 = ROOT / "world" / "tp201.yaml"
KEY = ROOT / "answer_key" / "TP-201"

Seed = Callable[[Path, Path], None]


def score(corpus: Corpus, docs: list[CorpusDocument]) -> dict[str, Any]:
    scans = [(d, corpus.read(d)) for d in docs]
    sub = Submission(
        equipment="TP-201",
        system=System(name="test"),
        ocr=tuple(OcrEntry.model_validate(e.model_dump()) for e in ocr_entries(scans)),
    )
    return score_ocr(sub, load_key(KEY))


def _counts(report: dict[str, Any]) -> tuple[int, int, int]:
    """Exact matches overall, and among the number and date entries, of how many."""
    items: list[dict[str, Any]] = report["items"]
    nd = [i for i in items if i["kind"] in ("number", "date")]
    return sum(bool(i["exact"]) for i in items), sum(bool(i["exact"]) for i in nd), len(nd)


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    assert render.main([str(TP201), "--out", str(out)]) == 0
    return next(out.glob("t0-*"))


def _doc(corpus: Corpus, doc_id: str) -> CorpusDocument:
    return next(d for d in corpus.documents if d.doc_id == doc_id)


# --- XLSX -----------------------------------------------------------------------------


def test_a_sheet_reads_as_the_scorer_prints_it(corpus_dir: Path) -> None:
    corpus = Corpus.load(corpus_dir)
    ra = _doc(corpus, "RA-TP201")
    pages = read_xlsx(ra.path)
    printed = PageTexts(build_corpus(load(TP201))).pages((ra.doc_id, ra.rev))
    assert [normalise(p.text) for p in pages] == printed
    (table,) = pages[0].tables
    row = next(r for r in table.rows if "URS-TP201-002" in r)
    assert row[-2:] == ("Ya", "Tinjauan desain di DQ; verifikasi fisik saat FAT/SAT dan IQ")


# --- Joining the lines of a table cell -------------------------------------------------


def _quad(x0: float, y0: float, x1: float, y1: float) -> Quad:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _page() -> np.ndarray:
    """A 400 x 300 px page at 72 dpi (1 px = 1 pt): a table with its left border at x 20 and
    a rule at y 100 between two rows; free text below it, outside any table."""
    page = np.full((300, 400), 240, dtype=np.uint8)
    page[20:130, 20:22] = 30  # the table's left border
    page[20:22, 20:300] = 30
    page[99:101, 20:300] = 30  # the rule between the rows
    page[129:131, 20:300] = 30
    return page


def test_lines_of_one_cell_join_and_rows_do_not() -> None:
    lines = [
        OcrLine("TACH-07", _quad(30, 60, 90, 76)),
        OcrLine("SW-03", _quad(30, 80, 80, 96)),  # same cell, no rule between
        OcrLine("SW-11", _quad(30, 102, 80, 118)),  # the next row, below the rule
        OcrLine("5. Deviations", _quad(30, 160, 130, 176)),  # outside the table
        OcrLine("Tidak ada", _quad(30, 180, 100, 196)),
    ]
    joined = scan.join_cells(lines, _page(), 72.0)
    assert [(e.text, e.quad) for e in joined] == [
        ("TACH-07 SW-03", _quad(30, 60, 90, 96)),
        ("SW-11", _quad(30, 102, 80, 118)),
        ("5. Deviations", _quad(30, 160, 130, 176)),
        ("Tidak ada", _quad(30, 180, 100, 196)),
    ]


def test_reading_order_follows_rows_through_the_skew() -> None:
    slope = 0.02  # about 1.1 degrees, downhill to the right
    entries = [
        OcrLine("SAT-05", _quad(50, 100, 90, 115)),
        OcrLine("Lulus", _quad(500, 109, 540, 124)),  # same row, 9 pt lower by the skew
        OcrLine("SAT-06", _quad(50, 130, 90, 145)),
    ]
    assert scan.reading_order(entries) == "SAT-05\nLulus\nSAT-06"
    assert scan.reading_order(entries, slope) == "SAT-05 Lulus\nSAT-06"
    assert scan.skew([OcrLine("x", ((0, 10), (100, 12), (100, 27), (0, 25)))]) == 0.02


# --- The ingest cache ------------------------------------------------------------------


@pytest.mark.usefixtures("no_ocr_model")
def test_a_cached_scan_is_read_without_the_ocr_model(
    corpus_dir: Path, tmp_path: Path, seed_scans: Seed
) -> None:
    corpus = Corpus.load(corpus_dir, cache=tmp_path / "ingest")
    sat = _doc(corpus, "SAT-TP201")
    with pytest.raises(OcrUnavailable):
        corpus.read(sat)

    seed_scans(corpus_dir, tmp_path / "ingest")
    corpus = Corpus.load(corpus_dir, cache=tmp_path / "ingest")
    pages = corpus.read(sat)
    assert len(pages) == 2
    assert "TACH-07 SW-03" in [e.text for e in pages[0].ocr]
    assert "SAT-01" in pages[0].text
    ((doc, ingested),) = corpus.ingested()
    assert doc == sat and ingested.cached
    assert len(ingested.seconds_per_page) == 2 and ingested.peak_ram_bytes


def test_a_document_is_read_once_then_comes_from_the_cache(
    corpus_dir: Path, tmp_path: Path
) -> None:
    first = Corpus.load(corpus_dir, cache=tmp_path)
    ra = _doc(first, "RA-TP201")
    read = first.ingest(ra)
    assert not read.cached
    (cached,) = tmp_path.glob(f"{ra.sha256}-*.json")

    again = Corpus.load(corpus_dir, cache=tmp_path).ingest(ra)
    assert again.cached
    assert again.pages == read.pages
    # A cache hit does not even open the document.
    moved = tmp_path / "elsewhere"
    shutil.copytree(corpus_dir, moved)
    _doc(Corpus.load(moved), "RA-TP201").path.unlink()
    assert Corpus.load(moved, cache=tmp_path).ingest(ra).pages == read.pages
    assert cached.exists()


@pytest.mark.usefixtures("no_ocr_model")
def test_the_scan_entries_score_on_the_sat_scan(
    corpus_dir: Path, tmp_path: Path, seed_scans: Seed
) -> None:
    """The recorded PP-OCRv6 output, scored by the OCR scorer: the spike's 34/36 exact
    with ``TACH-07 SW-03`` now joined into one entry."""
    seed_scans(corpus_dir, tmp_path)
    corpus = Corpus.load(corpus_dir, cache=tmp_path)
    report = score(corpus, [d for d in corpus.documents if d.format == "scan"])
    metrics = report["metrics"]
    assert metrics["entry_recall"] == 1.0
    assert metrics["localisation_rate"] == 1.0
    assert _counts(report) == (35, 10, 10)


@pytest.mark.skipif(
    importlib.util.find_spec("onnxruntime") is None,
    reason="needs the OCR model (uv sync --extra ocr); CI replays the recorded output instead",
)
def test_the_ocr_model_reads_the_sat_scan(corpus_dir: Path, tmp_path: Path) -> None:
    corpus = Corpus.load(corpus_dir, cache=tmp_path)
    sat = _doc(corpus, "SAT-TP201")
    corpus.read(sat)
    ((_, ingested),) = corpus.ingested()
    assert not ingested.cached
    assert max(ingested.seconds_per_page) <= 60
    assert ingested.peak_ram_bytes is not None and ingested.peak_ram_bytes <= 4e9
    exact, number_date, _ = _counts(score(corpus, [sat]))
    assert exact >= 34 and number_date == 10
