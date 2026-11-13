"""Spreadsheet ingest with openpyxl: page n is sheet n.

A sheet's text is its rows in order, one row per line, each row's non-empty cell values
joined by a space; the rows are also kept as the sheet's one table, with an empty string
for an empty cell so columns stay aligned. Cell values are read as stored (the corpus writes
values, not formulas).
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from traceq.documents.pages import Page, Row, Table

XLSX_VERSION = "openpyxl-1"
"""Part of the ingest cache key: bump it when a change alters the page text."""
ENGINE = "openpyxl"


def read_xlsx(path: Path) -> tuple[Page, ...]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        pages: list[Page] = []
        for n, ws in enumerate(wb.worksheets, 1):
            rows: list[Row] = []
            for values in ws.iter_rows(values_only=True):
                cells = ["" if v is None else " ".join(str(v).split()) for v in values]
                while cells and not cells[-1]:
                    cells.pop()
                if cells:
                    rows.append(tuple(cells))
            text = "\n".join(" ".join(c for c in row if c) for row in rows)
            pages.append(Page(n, text, (Table(tuple(rows)),) if rows else ()))
        return tuple(pages)
    finally:
        wb.close()
