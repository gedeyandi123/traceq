"""Turn a born-digital paper document into a scan (design section 8, degrader).

The renderer decides what is on the page; the degrader only decides how the scan looks.
It rasterises each page, rotates it by a small skew, adds paper tone, blur and sensor
noise, and stores it as JPEG in an image-only PDF: the text layer is gone, as on a real
scan. Every handwritten box gets the same rotation, so the OCR answer key follows the
pixels (:attr:`ScannedPlaced.quad`).

Output is deterministic: parameters come from the document's level, and the random
draws from ``seed`` plus the document id and revision.
"""

from __future__ import annotations

import calendar
import datetime as dt
import io
import math
import time
import zlib
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter

from traceq_dataset.render import Box, Rendered

SEED = 0
"""Corpus seed; a different seed gives a different but equally valid scan."""

Point = tuple[float, float]


@dataclass(frozen=True)
class Level:
    """Scan quality for one document (design: level per document, not global)."""

    dpi: int
    skew: tuple[float, float]
    """Range of the absolute skew angle in degrees; the sign is drawn too."""
    noise: float
    """Standard deviation of grey sensor noise, 0–255 scale."""
    blur: float
    """Gaussian blur radius in px (scanner optics)."""
    jpeg_quality: int


LEVELS: Mapping[str, Level] = {
    "light": Level(dpi=200, skew=(0.5, 0.8), noise=3.0, blur=0.4, jpeg_quality=85),
    "medium": Level(dpi=150, skew=(0.8, 1.4), noise=6.0, blur=0.6, jpeg_quality=70),
    "heavy": Level(dpi=150, skew=(1.4, 2.0), noise=10.0, blur=0.8, jpeg_quality=55),
}

PAPER = (0.97, 0.96, 0.92)
"""Multiplier per RGB channel: white paper scans slightly warm."""


@dataclass(frozen=True)
class ScannedPlaced:
    """A placed string on the scan. ``quad`` (handwritten entries only) holds the four
    corners of its box after skew, in pt with origin top-left, clockwise from top-left."""

    page: int
    text: str
    quad: tuple[Point, Point, Point, Point] | None


@dataclass(frozen=True)
class Scanned:
    doc_id: str
    rev: int
    pdf: bytes
    dpi: int
    level: str
    skew: tuple[float, ...]
    """Skew per page in degrees, counter-clockwise positive."""
    placed: Mapping[str, ScannedPlaced]

    @property
    def filename(self) -> str:
        return f"{self.doc_id}_rev{self.rev}.pdf"


def rotate_quad(
    box: Box, angle: float, width: float, height: float
) -> tuple[Point, Point, Point, Point]:
    """Corners of ``box`` after the page rotates ``angle`` degrees counter-clockwise about
    its centre (as :meth:`PIL.Image.Image.rotate` does, y pointing down)."""
    cx, cy = width / 2, height / 2
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    corners = ((box.x, box.y), (box.x + box.w, box.y), (box.x + box.w, box.y + box.h))
    corners += ((box.x, box.y + box.h),)
    p0, p1, p2, p3 = (
        (cx + (x - cx) * c + (y - cy) * s, cy - (x - cx) * s + (y - cy) * c) for x, y in corners
    )
    return p0, p1, p2, p3


def _scan_page(
    page: pdfium.PdfPage, level: Level, angle: float, rng: np.random.Generator
) -> Image.Image:
    # pypdfium2's stub types `scale` as int; the library takes a float (dpi / 72).
    bitmap = page.render(scale=level.dpi / 72)  # pyright: ignore[reportArgumentType]
    image = bitmap.to_pil().convert("RGB")
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255))
    image = image.filter(ImageFilter.GaussianBlur(level.blur))
    pixels = np.asarray(image, dtype=np.float32) * np.array(PAPER, dtype=np.float32)
    pixels += rng.normal(0.0, level.noise, size=pixels.shape[:2])[..., None]
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def _image_pdf(pages: list[Image.Image], level: Level, issued: dt.date) -> bytes:
    """An image-only PDF, one JPEG per page and no text layer, dated ``issued``."""
    date = time.gmtime(calendar.timegm(issued.timetuple()))
    out = io.BytesIO()
    pages[0].save(
        out,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=level.dpi,
        quality=level.jpeg_quality,
        creationDate=date,
        modDate=date,
    )
    return out.getvalue()


def degrade(rendered: Rendered, level: str, seed: int = SEED) -> Scanned:
    """Scan ``rendered`` at ``level`` (a key of :data:`LEVELS`)."""
    params = LEVELS[level]
    rng = np.random.default_rng([seed, zlib.crc32(rendered.doc_id.encode()), rendered.rev])
    source = pdfium.PdfDocument(rendered.pdf)
    sizes = [(p.get_width(), p.get_height()) for p in source]
    lo, hi = params.skew
    angles = tuple(float(rng.choice((-1, 1)) * rng.uniform(lo, hi)) for _ in sizes)
    pages = [_scan_page(p, params, a, rng) for p, a in zip(source, angles, strict=True)]
    placed = {
        key: ScannedPlaced(
            p.page,
            p.text,
            rotate_quad(p.box, angles[p.page - 1], *sizes[p.page - 1]) if p.box else None,
        )
        for key, p in rendered.placed.items()
    }
    return Scanned(
        doc_id=rendered.doc_id,
        rev=rendered.rev,
        pdf=_image_pdf(pages, params, rendered.issued),
        dpi=params.dpi,
        level=level,
        skew=angles,
        placed=placed,
    )
