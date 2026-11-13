"""A released corpus directory: ``manifest.json`` plus one file per document.

Born-digital PDFs are read with Docling (``traceq.documents.pdf``), spreadsheets with
openpyxl (``traceq.documents.xlsx``) and scans with the local OCR model
(``traceq.documents.scan``). Every reading goes through the ingest cache
(``traceq.documents.cache``): a document found there is not read again, nor even opened.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traceq.documents import pdf, scan, xlsx
from traceq.documents.cache import IngestCache, Ingested, peak_ram_bytes
from traceq.documents.pages import Page

VERSIONS = {"born_digital": pdf.PDF_VERSION, "xlsx": xlsx.XLSX_VERSION, "scan": scan.SCAN_VERSION}
"""The reader version per document format: part of the ingest cache key."""

_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """NFKC and collapsed whitespace; case and punctuation stay."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


@dataclass(frozen=True)
class CorpusDocument:
    doc_id: str
    rev: int
    type: str
    format: str
    language: str
    path: Path
    sha256: str


@dataclass
class Corpus:
    root: Path
    equipment: str
    documents: tuple[CorpusDocument, ...]
    cache: IngestCache = field(default_factory=lambda: IngestCache(None), repr=False)
    _ingested: dict[tuple[str, int], Ingested] = field(
        default_factory=dict[tuple[str, int], Ingested], repr=False
    )

    @classmethod
    def load(cls, root: Path, equipment: str | None = None, cache: Path | None = None) -> Corpus:
        """Read ``root/manifest.json``. ``equipment`` may be omitted when the corpus holds
        exactly one Equipment. ``cache``: the ingest cache directory (none: nothing kept)."""
        manifest: dict[str, Any] = json.loads((root / "manifest.json").read_text("utf-8"))
        tags = [str(t) for t in manifest["equipment"]]
        if equipment is None:
            if len(tags) != 1:
                raise ValueError(f"corpus holds {tags}; choose one Equipment")
            equipment = tags[0]
        elif equipment not in tags:
            raise ValueError(f"corpus holds {tags}, not {equipment}")
        entries: list[dict[str, Any]] = manifest["documents"]
        docs = tuple(
            CorpusDocument(
                doc_id=str(d["doc_id"]),
                rev=int(d["rev"]),
                type=str(d["type"]),
                format=str(d["format"]),
                language=str(d.get("language") or "en"),
                path=root / str(d["path"]),
                sha256=str(d["sha256"]),
            )
            for d in entries
            if d["equipment"] == equipment
        )
        return cls(root=root, equipment=equipment, documents=docs, cache=IngestCache(cache))

    def current(self, doc_type: str) -> list[CorpusDocument]:
        """The highest revision of every document of a type."""
        latest: dict[str, CorpusDocument] = {}
        for d in self.documents:
            if d.type == doc_type and (d.doc_id not in latest or d.rev > latest[d.doc_id].rev):
                latest[d.doc_id] = d
        return sorted(latest.values(), key=lambda d: d.doc_id)

    def find(self, doc_id: str, rev: int) -> CorpusDocument | None:
        return next((d for d in self.documents if (d.doc_id, d.rev) == (doc_id, rev)), None)

    def readable(self, doc: CorpusDocument) -> bool:
        """Whether ingest can read the document's format."""
        return doc.format in VERSIONS

    def ingest(self, doc: CorpusDocument) -> Ingested:
        """The document's pages from the ingest cache, else read by its engine and cached.
        Raises ``scan.OcrUnavailable`` for a scan the cache lacks when the OCR model is not
        installed."""
        key = (doc.doc_id, doc.rev)
        if key in self._ingested:
            return self._ingested[key]
        if not self.readable(doc):
            raise NotImplementedError(f"{doc.doc_id}: no ingest for {doc.format}")
        version = VERSIONS[doc.format]
        got = self.cache.get(doc.sha256, version)
        if got is None:
            data = doc.path.read_bytes()
            if hashlib.sha256(data).hexdigest() != doc.sha256:
                raise ValueError(f"{doc.path}: bytes do not match the manifest")
            if doc.format == "scan":
                r = scan.read_scan(doc.path)
                pages, seconds, load, engine = (
                    r.pages,
                    r.seconds_per_page,
                    r.load_seconds,
                    scan.ENGINE,
                )
            else:
                t0 = time.perf_counter()
                if doc.format == "xlsx":
                    pages, engine = xlsx.read_xlsx(doc.path), xlsx.ENGINE
                else:
                    pages, engine = pdf.read_pdf(doc.path), pdf.ENGINE
                per_page = round((time.perf_counter() - t0) / max(len(pages), 1), 2)
                seconds, load = (per_page,) * len(pages), 0.0
            got = Ingested(doc.sha256, version, engine, pages, seconds, load, peak_ram_bytes())
            self.cache.put(got)
        self._ingested[key] = got
        return got

    def ingested(self) -> list[tuple[CorpusDocument, Ingested]]:
        """Every document ingested so far, in the order it was first read."""
        by_key = {(d.doc_id, d.rev): d for d in self.documents}
        return [(by_key[k], i) for k, i in self._ingested.items()]

    def read(self, doc: CorpusDocument) -> tuple[Page, ...]:
        """Page text, tables and OCR entries: page n is item n - 1."""
        return self.ingest(doc).pages

    def pages(self, doc: CorpusDocument) -> list[str]:
        """Printed text per page: page n is item n - 1."""
        return [p.text for p in self.read(doc)]
