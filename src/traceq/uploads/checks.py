"""What a file must be to be accepted as an uploaded Protocol Draft.

Four checks, in order and each cheap before the next: the size cap (counted while the body
is read, so an oversize body is never held), the PDF signature (``%PDF-`` at the start), the
page cap (read by pdfium, which refuses a file it cannot parse and an encrypted one), and the
page size: each page's MediaBox is read before any page is decoded, and a page too large, or
pages that together would render to too many pixels, are refused (a small file can declare a
page that would take gigabytes of memory to rasterise).
The file is named by its SHA-256, never by what its sender called it.
"""

from __future__ import annotations

import hashlib
import importlib
from dataclasses import dataclass
from typing import Any

SIGNATURE = b"%PDF-"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_PAGES = 40
DEFAULT_MAX_PAGE_POINTS = 3600.0
"""Longest side of a page, in points (1/72 in): 50 in, past A0 (3370 pt)."""
DEFAULT_MAX_RENDER_PIXELS = 400_000_000
"""Pixels all pages together may render to at ``RENDER_DPI``: about 100 A4 pages."""
RENDER_DPI = 200


class Refused(ValueError):
    """The upload is not accepted; the message says why and is safe to show."""


class TooLarge(Refused):
    """The body passes the size cap."""


@dataclass(frozen=True)
class Checked:
    sha256: str
    size_bytes: int
    pages: int


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _open(data: bytes) -> Any:
    pdfium: Any = importlib.import_module("pypdfium2")  # ships no type information
    try:
        return pdfium.PdfDocument(data)
    except Exception as e:  # pdfium raises its own error types for every unreadable file
        raise Refused("the file is not a PDF that can be read (damaged or protected)") from e


def page_count(data: bytes) -> int:
    """Pages of a PDF; ``Refused`` for bytes pdfium cannot read (damaged, encrypted)."""
    document = _open(data)
    try:
        return len(document)
    finally:
        document.close()


def check_page_sizes(
    data: bytes,
    *,
    max_page_points: float = DEFAULT_MAX_PAGE_POINTS,
    max_render_pixels: int = DEFAULT_MAX_RENDER_PIXELS,
) -> None:
    """``Refused`` when a page is larger than ``max_page_points`` on a side, or the pages
    together would render to more than ``max_render_pixels``. Only the page boxes are read;
    no page content is decoded."""
    document = _open(data)
    try:
        scale = RENDER_DPI / 72
        pixels = 0.0
        for index in range(len(document)):
            try:
                width, height = document.get_page_size(index)
            except Exception as e:
                raise Refused(f"page {index + 1} has no readable size") from e
            if not (0 < width <= max_page_points and 0 < height <= max_page_points):
                raise Refused(
                    f"page {index + 1} is {width:.0f} x {height:.0f} points; "
                    f"the cap is {max_page_points:.0f} on a side"
                )
            pixels += width * scale * height * scale
            if pixels > max_render_pixels:
                raise Refused(
                    f"the pages are too large together (more than {max_render_pixels:,} "
                    f"pixels to read at {RENDER_DPI} dpi)"
                )
    finally:
        document.close()


def check_pdf(
    data: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_page_points: float = DEFAULT_MAX_PAGE_POINTS,
    max_render_pixels: int = DEFAULT_MAX_RENDER_PIXELS,
) -> Checked:
    """``Refused`` unless ``data`` is a readable PDF within the size, page-count and page-size
    caps."""
    if not data:
        raise Refused("the file is empty")
    if len(data) > max_bytes:
        raise TooLarge(f"the file passes the size cap of {max_bytes // (1024 * 1024)} MB")
    if not data.startswith(SIGNATURE):
        raise Refused("the file is not a PDF (it does not start with the PDF signature)")
    pages = page_count(data)
    if pages < 1:
        raise Refused("the PDF has no pages")
    if pages > max_pages:
        raise Refused(f"the PDF has {pages} pages; the cap is {max_pages}")
    check_page_sizes(data, max_page_points=max_page_points, max_render_pixels=max_render_pixels)
    return Checked(sha256=sha256_of(data), size_bytes=len(data), pages=pages)
