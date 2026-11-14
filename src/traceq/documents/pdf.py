"""Born-digital PDF ingest with Docling: the text printed on each page, and its tables.

Docling reads the PDF through its pypdfium2 backend (the docling-parse backend rewrites an en
dash as a hyphen, so ``20–60 rpm`` would no longer be the printed text) and finds tables with
its layout and table-structure models, on the CPU. Page furniture (running headers and
footers) is left out.

Page text is what the page prints, in reading order: each text block on its own line, and
each table row as its cells joined by a space, one row per line. That is the order a reader
(and the scorer's printed text) sees, so a quote of a table row is checked against it
verbatim. The rows themselves are kept in ``Page.tables``.

Docling runs only when the ingest cache (``traceq.documents.cache``) has no entry for the
document's hash and ``PDF_VERSION``.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from traceq.documents.pages import Page, Row, Table

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.items.table.table import TableItem

PDF_VERSION = "docling-1"
"""Part of the ingest cache key: bump it when a change alters the page text."""
ENGINE = "Docling (pypdfium2 backend)"


@cache
def _converter() -> DocumentConverter:
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    pdf = PdfFormatOption(pipeline_options=options, backend=PyPdfiumDocumentBackend)
    return DocumentConverter(format_options={InputFormat.PDF: pdf})


def _cell(text: str) -> str:
    return " ".join(text.split())


def _rows(table: TableItem) -> tuple[Row, ...]:
    """Cells per row; a cell spanning several columns or rows is kept once, where it starts."""
    rows: list[Row] = []
    for r, grid_row in enumerate(table.data.grid):
        cells: list[str] = []
        starts: set[int] = set()
        for c in grid_row:
            if c.start_row_offset_idx == r and c.start_col_offset_idx not in starts:
                starts.add(c.start_col_offset_idx)
                cells.append(_cell(c.text))
        if any(cells):
            rows.append(tuple(cells))
    return tuple(rows)


def pages_of(doc: DoclingDocument, page_count: int) -> tuple[Page, ...]:
    from docling_core.types.doc.items.table.table import TableItem
    from docling_core.types.doc.items.text import TextItem

    lines: dict[int, list[str]] = {n: [] for n in range(1, page_count + 1)}
    tables: dict[int, list[Table]] = {n: [] for n in range(1, page_count + 1)}
    for item, _level in doc.iterate_items(with_groups=False):
        if isinstance(item, TableItem) and item.prov:
            n = item.prov[0].page_no
            t = Table(_rows(item))
            tables[n].append(t)
            lines[n] += [" ".join(c for c in row if c) for row in t.rows]
        elif isinstance(item, TextItem) and item.prov and item.text.strip():
            lines[item.prov[0].page_no].append(_cell(item.text))
    return tuple(Page(n, "\n".join(lines[n]), tuple(tables[n])) for n in range(1, page_count + 1))


def read_pdf(path: Path) -> tuple[Page, ...]:
    """The pages of a born-digital PDF."""
    result = _converter().convert(path)
    return pages_of(result.document, len(result.pages))
