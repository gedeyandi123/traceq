"""Semantic validator for rendered documents (design section 8, "CI").

CI re-renders and checks meaning, not bytes: every placed string the answer key relies on
must appear in the extracted text of the page the renderer says it is on. A handwritten
entry must also appear inside its recorded bounding box, which the OCR answer key uses.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from pypdf import PdfReader

from traceq_dataset.degrade import Scanned
from traceq_dataset.render import Box, Rendered

_SPACE = re.compile(r"\s+")
BOX_TOLERANCE = 1.0
"""pt added on every side: glyph outlines may touch the measured box."""


def normalise(text: str) -> str:
    """Collapse whitespace, so line breaks inside table cells do not matter."""
    return _SPACE.sub(" ", text).strip()


def page_texts(pdf: bytes) -> list[str]:
    return [normalise(p.extract_text()) for p in PdfReader(io.BytesIO(pdf)).pages]


def text_in_box(pdf: pdfium.PdfDocument, page: int, box: Box) -> str:
    """Text whose characters lie inside ``box`` (top-left origin, pt) on ``page`` (1-based)."""
    p = pdf[page - 1]
    height, t = p.get_height(), BOX_TOLERANCE
    return normalise(
        p.get_textpage().get_text_bounded(
            left=box.x - t,
            bottom=height - box.y - box.h - t,
            right=box.x + box.w + t,
            top=height - box.y + t,
        )
    )


MIN_INK = 0.05
"""Least share of dark pixels inside a handwritten quad on a scan (measured ≥ 0.11)."""


def scan_problems(scanned: Scanned) -> list[str]:
    """A scan must have no text layer, and every handwritten quad must lie on its page
    and hold ink. The quad geometry itself is tested against Pillow's rotation."""
    reader = PdfReader(io.BytesIO(scanned.pdf))
    out = [
        f"{scanned.filename} page {i}: has a text layer"
        for i, p in enumerate(reader.pages, 1)
        if p.extract_text().strip()
    ]
    pdf, scale = pdfium.PdfDocument(scanned.pdf), scanned.dpi / 72
    pages = [pdf[i].render(scale=scale).to_pil().convert("L") for i in range(len(pdf))]
    for key, placed in scanned.placed.items():
        if placed.quad is None:
            continue
        page = pages[placed.page - 1]
        corners = [(x * scale, y * scale) for x, y in placed.quad]
        if not all(0 <= x <= page.width and 0 <= y <= page.height for x, y in corners):
            out.append(f"{scanned.filename} {key}: quad off page {placed.page}")
            continue
        mask = Image.new("1", page.size)
        ImageDraw.Draw(mask).polygon(corners, fill=1)
        ink = np.asarray(page)[np.asarray(mask)] < 170
        if ink.mean() < MIN_INK:
            out.append(f"{scanned.filename} {key}: no ink in its quad on page {placed.page}")
    return out


def missing_text(rendered: Rendered) -> list[str]:
    """Placed strings not found on their recorded page, or outside their recorded box."""
    pages = page_texts(rendered.pdf)
    pdf = pdfium.PdfDocument(rendered.pdf)
    out = []
    for key, placed in rendered.placed.items():
        where = f"{rendered.filename} {key}"
        text = normalise(placed.text)
        if not 1 <= placed.page <= len(pages):
            out.append(f"{where}: page {placed.page} out of range")
        elif text not in pages[placed.page - 1]:
            out.append(f"{where}: text not on page {placed.page}")
        elif placed.box and text not in text_in_box(pdf, placed.page, placed.box):
            out.append(f"{where}: text not in its box on page {placed.page}")
    return out
