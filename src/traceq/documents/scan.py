"""Scan ingest with the local OCR model: PP-OCRv6 small through RapidOCR 3.10.0, on the CPU.

The model was chosen by the OCR spike (spec #29, ADR 0004 kept) and is called directly, with
no port (ADR 0008). It is pinned explicitly (``ocr_version`` and ``model_type`` for detection
and recognition), since RapidOCR's default model changes between its releases. It is an
optional dependency (``uv sync --extra ocr``): a run that finds every scan in the ingest cache
needs neither the model nor ONNX Runtime.

Each page is rendered at the scan's own resolution. RapidOCR returns one box per text line,
so lines that sit in the same table cell (``TACH-07`` above ``SW-03``) are joined into one
entry: a line joins the one above it when they overlap horizontally, the gap between them is
less than half a line, and no ruled line runs between them. Page text is the entries in
reading order, one visual row per line.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from traceq.documents.pages import OcrLine, Page, Quad

OCR_VERSION = "PP-OCRv6"
MODEL_TYPE = "small"
RAPIDOCR = "3.10.0"
SCAN_VERSION = f"{OCR_VERSION}-{MODEL_TYPE}-rapidocr-{RAPIDOCR}-1"
"""Part of the ingest cache key: bump the last part when a change alters the output."""
ENGINE = f"{OCR_VERSION} {MODEL_TYPE} via RapidOCR {RAPIDOCR}"

MAX_GAP = 0.5
"""A cell's next line starts at most this many line heights below the previous one."""
MIN_OVERLAP = 0.5
"""Lines of one cell overlap horizontally by at least this share of the narrower line."""
SEGMENT_PX = 24
PIECE_COVER = 0.8
"""A segment holds a piece of rule when a row of it is at least this share ink."""
RULE_COVER = 0.8
"""A ruled line puts a piece in at least this share of the segments."""
MIN_SKEW_WIDTH = 50.0
"""Lines at least this wide (pt) measure the page's skew."""
BORDER_REACH = 1.5
"""How far left of a cell's lines (in line heights) its left border is sought."""
BOX_PAD = 0.15
"""How far into each line's box (share of the line height) a rule between them is sought."""
INK = 0.75
"""A pixel is ink when darker than this share of the page's median grey (the paper)."""

Gray = NDArray[np.uint8]


class OcrUnavailable(RuntimeError):
    """A scan is not in the ingest cache and the OCR model is not installed."""


@dataclass(frozen=True)
class ScanRead:
    pages: tuple[Page, ...]
    seconds_per_page: tuple[float, ...]
    load_seconds: float


def _module(name: str) -> Any:
    """Imported at run time: the OCR model and pypdfium2 ship no type information, and the
    model is an optional dependency."""
    return importlib.import_module(name)


@cache
def _engine() -> Any:
    if (
        importlib.util.find_spec("rapidocr") is None
        or importlib.util.find_spec("onnxruntime") is None
    ):
        raise OcrUnavailable(
            "the OCR model is not installed (uv sync --extra ocr) and a scan is not in the"
            " ingest cache"
        )
    ro = _module("rapidocr")
    version, kind = ro.OCRVersion(OCR_VERSION), ro.ModelType(MODEL_TYPE)
    return ro.RapidOCR(
        params={
            "Det.ocr_version": version,
            "Det.model_type": kind,
            "Rec.ocr_version": version,
            "Rec.model_type": kind,
        }
    )


def box(quad: Quad) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    return min(xs), min(ys), max(xs), max(ys)


def _box_quad(x0: float, y0: float, x1: float, y1: float) -> Quad:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _ink(gray: Gray, scale: float, x0: float, x1: float, y0: float, y1: float) -> NDArray[np.bool_]:
    """Which pixels of the area (pt) are ink."""
    top, bottom = max(0, math.floor(y0 * scale)), max(0, math.ceil(y1 * scale))
    left, right = max(0, math.floor(x0 * scale)), max(0, math.ceil(x1 * scale))
    return gray[top : bottom + 1, left : right + 1] < INK * float(np.median(gray))


def _rule_along(ink: NDArray[np.bool_]) -> bool:
    """Whether a rule runs along the rows of ``ink``, from its first column to its last.

    The columns are cut into short segments, so a rule skewed by the scan still lies along
    a pixel row within each one: a segment holds a piece of rule when one of its rows (read
    two at a time, for a rule between two rows) is nearly all ink. A rule puts a piece in
    nearly every segment; text, with gaps between its strokes, does not."""
    if ink.shape[0] < 2 or ink.shape[1] < SEGMENT_PX:
        return False
    pair = ink[:-1] | ink[1:]
    starts = range(0, pair.shape[1] - SEGMENT_PX // 2, SEGMENT_PX)
    pieces = [float(pair[:, i : i + SEGMENT_PX].mean(axis=1).max()) >= PIECE_COVER for i in starts]
    return sum(pieces) >= RULE_COVER * len(pieces)


def _same_cell(above: OcrLine, below: OcrLine, gray: Gray, scale: float) -> bool:
    """Two lines share a table cell: the lower one starts just below the upper one, they
    overlap horizontally, no horizontal rule runs between them and a vertical rule (the
    cell's left border) runs just left of both."""
    ax0, ay0, ax1, ay1 = box(above.quad)
    bx0, by0, bx1, by1 = box(below.quad)
    height = min(ay1 - ay0, by1 - by0)
    left, right = max(ax0, bx0), min(ax1, bx1)
    if right - left < MIN_OVERLAP * min(ax1 - ax0, bx1 - bx0):
        return False
    if by0 < (ay0 + ay1) / 2 or by0 - ay1 > MAX_GAP * height:
        return False
    # The model's boxes are padded and may touch or overlap: look for a rule from the lower
    # part of the line above to the upper part of the line below.
    pad = BOX_PAD * height
    if _rule_along(_ink(gray, scale, left, right, min(ay1, by0) - pad, max(ay1, by0) + pad)):
        return False
    x0 = min(ax0, bx0)
    strip = _ink(gray, scale, x0 - BORDER_REACH * height, x0 + pad, ay0 + pad, by1 - pad)
    return _rule_along(strip.T)


def join_cells(lines: Sequence[OcrLine], gray: Gray, dpi: float) -> list[OcrLine]:
    """Join the lines of each table cell into one entry, top to bottom, with the box around
    them as its quad. ``gray`` is the page image at ``dpi``; quads are in pt."""
    scale = dpi / 72
    cells: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda x: box(x.quad)[1]):
        for cell in reversed(cells):
            if _same_cell(cell[-1], line, gray, scale):
                cell.append(line)
                break
        else:
            cells.append([line])
    out: list[OcrLine] = []
    for cell in cells:
        boxes = [box(x.quad) for x in cell]
        quad = cell[0].quad
        if len(cell) > 1:
            quad = _box_quad(
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            )
        out.append(OcrLine(" ".join(x.text for x in cell), quad))
    return out


def skew(lines: Sequence[OcrLine]) -> float:
    """The page's skew as a slope (dy/dx), from the top edges of the model's line boxes,
    which follow the text: the median over lines wide enough to measure it."""
    slopes = [
        (q[1][1] - q[0][1]) / (q[1][0] - q[0][0])
        for q in (x.quad for x in lines)
        if q[1][0] - q[0][0] >= MIN_SKEW_WIDTH
    ]
    return float(np.median(slopes)) if slopes else 0.0


def reading_order(entries: Sequence[OcrLine], slope: float = 0.0) -> str:
    """Entries top to bottom, one visual row per line, each row left to right. Heights are
    taken after undoing the skew ``slope``; an entry belongs to a row when it overlaps the
    row's first entry vertically by half the height of the shorter one."""

    def span(e: OcrLine) -> tuple[float, float, float]:
        x0, y0, x1, y1 = box(e.quad)
        shift = slope * (x0 + x1) / 2
        return y0 - shift, y1 - shift, x0

    rows: list[list[OcrLine]] = []
    top = bottom = -math.inf
    for e in sorted(entries, key=span):
        y0, y1, _ = span(e)
        if rows and min(y1, bottom) - max(y0, top) >= min(y1 - y0, bottom - top) / 2:
            rows[-1].append(e)
        else:
            rows.append([e])
            top, bottom = y0, y1
    return "\n".join(
        " ".join(e.text for e in sorted(r, key=lambda x: box(x.quad)[0])) for r in rows
    )


def _pt(points: Sequence[Sequence[float]], dpi: float) -> Quad:
    p = [(round(float(x) * 72 / dpi, 2), round(float(y) * 72 / dpi, 2)) for x, y in points]
    return (p[0], p[1], p[2], p[3])


def _images(path: Path) -> list[tuple[Any, float]]:
    """Each page as a PIL image at the scan's own resolution, with that dpi."""
    pdfium, raw = _module("pypdfium2"), _module("pypdfium2.raw")
    out: list[tuple[Any, float]] = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        for page in pdf:
            width_pt = float(page.get_width())
            images = list(page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]))
            dpi = images[0].get_px_size()[0] / width_pt * 72 if images else 150.0
            out.append((page.render(scale=dpi / 72).to_pil().convert("RGB"), float(dpi)))
    finally:
        pdf.close()
    return out


def read_scan(path: Path) -> ScanRead:
    """OCR every page of a scanned PDF."""
    t0 = time.perf_counter()
    engine = _engine()
    load_seconds = time.perf_counter() - t0
    pages: list[Page] = []
    seconds: list[float] = []
    for n, (image, dpi) in enumerate(_images(path), 1):
        t = time.perf_counter()
        result = engine(np.asarray(image))
        boxes: Sequence[Sequence[Sequence[float]]] = [] if result.boxes is None else result.boxes
        texts: Sequence[str] = result.txts or ()
        lines = [
            OcrLine(str(text), _pt(b, dpi))
            for b, text in zip(boxes, texts, strict=True)
            if str(text).strip()
        ]
        gray: Gray = np.asarray(image.convert("L"), dtype=np.uint8)
        entries = join_cells(lines, gray, dpi)
        seconds.append(round(time.perf_counter() - t, 2))
        pages.append(Page(n, reading_order(entries, skew(lines)), ocr=tuple(entries)))
    return ScanRead(tuple(pages), tuple(seconds), round(load_seconds, 2))
