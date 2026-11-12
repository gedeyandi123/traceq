"""One corpus instance: every document of an Equipment rendered for a T0, paper documents
scanned, plus the corpus ``manifest.json`` (design section 8).

The published file of a paper document is its scan; its born-digital render is kept here
because the answer key and the validator need the exact text and boxes behind the pixels.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

import pypdfium2 as pdfium

from traceq_dataset.degrade import SEED, Scanned, degrade
from traceq_dataset.render import EVAL_T0, Rendered, render_all
from traceq_dataset.schema import Document, Equipment

DocKey = tuple[str, int]
"""(document id, revision)"""

GENERATOR_PACKAGES = ("typst", "pillow", "pypdfium2", "numpy")
"""Versions recorded in the manifest: they decide the bytes of the corpus."""


@dataclass(frozen=True)
class Corpus:
    eq: Equipment
    t0: dt.date
    seed: int
    rendered: Mapping[DocKey, Rendered]
    """Born-digital render of every document, paper documents included."""
    scanned: Mapping[DocKey, Scanned]
    """Scan of every paper document (``Document.scan`` set)."""

    def document(self, key: DocKey) -> Document:
        return next(d for d in self.eq.documents if (d.id, d.rev) == key)

    def published(self, key: DocKey) -> bytes:
        """The file a user of the corpus gets: the scan for paper documents."""
        return self.scanned[key].pdf if key in self.scanned else self.rendered[key].pdf

    def filename(self, key: DocKey) -> str:
        return self.rendered[key].filename


def build_corpus(eq: Equipment, t0: dt.date = EVAL_T0, seed: int = SEED) -> Corpus:
    rendered = {(r.doc_id, r.rev): r for r in render_all(eq, t0)}
    scanned = {
        (d.id, d.rev): degrade(rendered[(d.id, d.rev)], d.scan, seed)
        for d in eq.documents
        if d.scan
    }
    return Corpus(eq=eq, t0=t0, seed=seed, rendered=rendered, scanned=scanned)


def manifest(corpora: Iterable[Corpus]) -> dict[str, Any]:
    """``manifest.json`` of a corpus directory: one entry per published file.

    All corpora must share T0 and seed; paths are relative to the corpus directory.
    """
    corpora = list(corpora)
    t0s, seeds = {c.t0 for c in corpora}, {c.seed for c in corpora}
    if len(t0s) != 1 or len(seeds) != 1:
        raise ValueError("a corpus directory holds one T0 and one seed")
    documents = []
    for c in corpora:
        for key in c.rendered:
            doc, pdf = c.document(key), c.published(key)
            documents.append(
                {
                    "path": f"{c.eq.tag}/{c.filename(key)}",
                    "equipment": c.eq.tag,
                    "doc_id": doc.id,
                    "rev": doc.rev,
                    "type": doc.type,
                    "language": doc.language,
                    "format": "scan" if doc.scan else "born_digital",
                    "scan_level": doc.scan,
                    "issued": c.rendered[key].issued.isoformat(),
                    "pages": len(pdfium.PdfDocument(pdf)),
                    "bytes": len(pdf),
                    "sha256": hashlib.sha256(pdf).hexdigest(),
                }
            )
    return {
        "dataset": "traceq",
        "version": version("traceq-dataset"),
        "t0": t0s.pop().isoformat(),
        "seed": seeds.pop(),
        "generator": {p: version(p) for p in GENERATOR_PACKAGES},
        "equipment": [c.eq.tag for c in corpora],
        "documents": documents,
    }
