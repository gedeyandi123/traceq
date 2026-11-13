"""A released corpus directory: ``manifest.json`` plus one file per document.

Only born-digital PDFs are read in this slice, with Docling (``traceq.documents.ingest``);
spreadsheets and scans come with their own ingest.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traceq.documents.ingest import Page, read_pdf

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
    _pages: dict[tuple[str, int], tuple[Page, ...]] = field(
        default_factory=dict[tuple[str, int], tuple[Page, ...]], repr=False
    )

    @classmethod
    def load(cls, root: Path, equipment: str | None = None) -> Corpus:
        """Read ``root/manifest.json``. ``equipment`` may be omitted when the corpus holds
        exactly one Equipment."""
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
        return cls(root=root, equipment=equipment, documents=docs)

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
        """Whether this slice can read the document (born-digital PDFs only)."""
        return doc.format == "born_digital"

    def read(self, doc: CorpusDocument) -> tuple[Page, ...]:
        """Page text and tables: page n is item n - 1."""
        key = (doc.doc_id, doc.rev)
        if key not in self._pages:
            if not self.readable(doc):
                raise NotImplementedError(f"{doc.doc_id}: no ingest for {doc.format} yet")
            data = doc.path.read_bytes()
            if hashlib.sha256(data).hexdigest() != doc.sha256:
                raise ValueError(f"{doc.path}: bytes do not match the manifest")
            self._pages[key] = read_pdf(doc.path, doc.sha256)
        return self._pages[key]

    def pages(self, doc: CorpusDocument) -> list[str]:
        """Printed text per page: page n is item n - 1."""
        return [p.text for p in self.read(doc)]
