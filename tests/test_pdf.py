"""Born-digital PDF ingest with Docling, and the recorded Docling output the rest of the suite
reads instead (ticket #231).

``tests/fixtures/ingest`` holds what Docling read on every born-digital PDF of TP-201, keyed by
the bytes it read; ``tests/conftest.py`` seeds it into an ingest cache so that only this module
runs Docling. Docling itself runs here on one PDF, and must still read it as recorded.
"""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

from traceq.documents import Corpus, pdf
from traceq.documents.cache import from_json

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"
READ = ("VA-2025-011", 0)
"""The Vendor Assessment: the quickest to read, text blocks and tables on one page."""


def _recorded(doc_id: str, rev: int) -> dict[str, object]:
    return json.loads((FIXTURES / f"{doc_id}_rev{rev}.json").read_text(encoding="utf-8"))


def test_every_born_digital_pdf_has_a_recording_of_its_rendered_bytes(tp201_dist: Path) -> None:
    """A corpus change fails here, rather than the suite reading stale page text."""
    pdfs = [d for d in Corpus.load(tp201_dist).documents if d.format == "born_digital"]
    assert len(pdfs) == 10
    stale = [
        f"{d.doc_id}_rev{d.rev}"
        for d in pdfs
        if not (FIXTURES / f"{d.doc_id}_rev{d.rev}.json").exists()
        or _recorded(d.doc_id, d.rev)["doc_sha256"] != d.sha256
        or _recorded(d.doc_id, d.rev)["version"] != pdf.PDF_VERSION
    ]
    assert stale == [], "regenerate them as tests/conftest.py says"


RECORDED: dict[str, dict[str, str]] = {
    "docling-1": {
        "docling": "2.150.0",
        "docling-slim": "2.150.0",
        "docling-core": "2.106.0",
        "docling-ibm-models": "4.0.4",
        "docling-parse": "7.25.0",
        "pypdfium2": "5.15.2",
    },
}
"""Each ``PDF_VERSION`` cache key and the packages that can change page text, at the versions
it was recorded with. Append-only: a row is never edited."""


def test_the_installed_reader_is_the_one_the_cache_key_was_recorded_with() -> None:
    """An upgrade that may change page text needs a new cache key, or cached text from the old
    reader would be served as if the new one had read it."""
    recorded = RECORDED[pdf.PDF_VERSION]
    installed = {p: version(p) for p in recorded}
    assert installed == recorded, (
        f"the reader differs from what {pdf.PDF_VERSION} was recorded with: add a new "
        "PDF_VERSION with a new row here and regenerate the recordings; never edit an existing row"
    )


def test_docling_reads_a_pdf_as_recorded(tp201_dist: Path) -> None:
    doc = Corpus.load(tp201_dist).find(*READ)
    assert doc is not None
    recorded = from_json(_recorded(*READ))
    pages = pdf.read_pdf(doc.path)
    assert pages == recorded.pages
    assert any(p.tables for p in pages)
