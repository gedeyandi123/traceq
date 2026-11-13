"""The ingest cache (spec #29, "Ingest cache"): what ingest made of a document, keyed by the
document's hash and the reader's version.

One JSON file per document, ``<sha256>-<version>.json``: page text, tables and OCR entries
with their quads, plus the engine, seconds per page and peak RAM of the run that read it.
It is committed with the recordings, so a replay in CI runs neither Docling nor the OCR
model.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traceq.documents.pages import OcrLine, Page, Point, Quad, Table


@dataclass(frozen=True)
class Ingested:
    doc_sha256: str
    version: str
    engine: str
    pages: tuple[Page, ...]
    seconds_per_page: tuple[float, ...]
    load_seconds: float
    peak_ram_bytes: int | None
    """The process's peak RAM after the document was read (``None`` where unmeasured)."""
    cached: bool = False
    """Read from the cache rather than by its engine in this process."""


def peak_ram_bytes() -> int | None:
    """Peak RAM of this process so far: the peak working set on Windows, the maximum
    resident set size elsewhere."""
    try:
        if sys.platform == "win32":
            info: Any = importlib.import_module("psutil").Process().memory_info()
            return int(info.peak_wset)
        usage: Any = importlib.import_module("resource").getrusage(0)  # RUSAGE_SELF
        return int(usage.ru_maxrss) * (1 if sys.platform == "darwin" else 1024)
    except (ImportError, AttributeError):
        return None


def _quad(q: Any) -> Quad:
    p: list[Point] = [(float(x), float(y)) for x, y in q]
    return (p[0], p[1], p[2], p[3])


def _page(d: dict[str, Any]) -> Page:
    return Page(
        number=int(d["number"]),
        text=str(d["text"]),
        tables=tuple(
            Table(tuple(tuple(str(c) for c in row) for row in t)) for t in d.get("tables", [])
        ),
        ocr=tuple(OcrLine(str(o["text"]), _quad(o["quad"])) for o in d.get("ocr", [])),
    )


def to_json(i: Ingested) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for p in i.pages:
        page: dict[str, Any] = {"number": p.number, "text": p.text}
        if p.tables:
            page["tables"] = [[list(row) for row in t.rows] for t in p.tables]
        if p.ocr:
            page["ocr"] = [{"text": o.text, "quad": [list(pt) for pt in o.quad]} for o in p.ocr]
        pages.append(page)
    return {
        "doc_sha256": i.doc_sha256,
        "version": i.version,
        "engine": i.engine,
        "seconds_per_page": list(i.seconds_per_page),
        "load_seconds": i.load_seconds,
        "peak_ram_bytes": i.peak_ram_bytes,
        "pages": pages,
    }


def from_json(d: dict[str, Any]) -> Ingested:
    return Ingested(
        doc_sha256=str(d["doc_sha256"]),
        version=str(d["version"]),
        engine=str(d["engine"]),
        pages=tuple(_page(p) for p in d["pages"]),
        seconds_per_page=tuple(float(s) for s in d["seconds_per_page"]),
        load_seconds=float(d.get("load_seconds", 0.0)),
        peak_ram_bytes=None if d.get("peak_ram_bytes") is None else int(d["peak_ram_bytes"]),
        cached=True,
    )


class IngestCache:
    """``root`` ``None`` keeps nothing on disk."""

    def __init__(self, root: Path | None) -> None:
        self.root = root

    def path(self, doc_sha256: str, version: str) -> Path | None:
        return None if self.root is None else self.root / f"{doc_sha256}-{version}.json"

    def get(self, doc_sha256: str, version: str) -> Ingested | None:
        path = self.path(doc_sha256, version)
        if path is None or not path.exists():
            return None
        return from_json(json.loads(path.read_text(encoding="utf-8")))

    def put(self, i: Ingested) -> None:
        path = self.path(i.doc_sha256, i.version)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(to_json(i), ensure_ascii=False, indent=1) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
