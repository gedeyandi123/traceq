"""What ingest makes of a document, whatever its format: one ``Page`` per page (a PDF page, a
spreadsheet sheet or a scanned page) with its printed text, its tables and, for a scan, the
lines the OCR model read with where it read them."""

from __future__ import annotations

from dataclasses import dataclass

Row = tuple[str, ...]
Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]
"""Four corners in pt, top-left origin, clockwise from top-left (pixels = pt * dpi / 72)."""


@dataclass(frozen=True)
class Table:
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class OcrLine:
    """One entry the OCR model read: a text line, or the lines of one table cell joined."""

    text: str
    quad: Quad


@dataclass(frozen=True)
class Page:
    number: int
    """1-based."""
    text: str
    tables: tuple[Table, ...] = ()
    ocr: tuple[OcrLine, ...] = ()
