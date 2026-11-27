"""What a file must be to be accepted as an uploaded Protocol Draft.

Three checks, in order and each cheap before the next: the size cap (counted while the body
is read, so an oversize body is never held), the PDF signature (``%PDF-`` at the start), and
the page cap (read by pdfium, which refuses a file it cannot parse and an encrypted one).
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


def page_count(data: bytes) -> int:
    """Pages of a PDF; ``Refused`` for bytes pdfium cannot read (damaged, encrypted)."""
    pdfium: Any = importlib.import_module("pypdfium2")  # ships no type information
    try:
        document = pdfium.PdfDocument(data)
    except Exception as e:  # pdfium raises its own error types for every unreadable file
        raise Refused("the file is not a PDF that can be read (damaged or protected)") from e
    try:
        return len(document)
    finally:
        document.close()


def check_pdf(
    data: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES, max_pages: int = DEFAULT_MAX_PAGES
) -> Checked:
    """``Refused`` unless ``data`` is a readable PDF within the size and page caps."""
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
    return Checked(sha256=sha256_of(data), size_bytes=len(data), pages=pages)
