"""Semantic validator for rendered documents (design section 8, "CI").

CI re-renders and checks meaning, not bytes: every string the answer key relies on
must appear in the extracted text of the page the renderer says it is on.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader

from traceq_dataset.render import Rendered

_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Collapse whitespace, so line breaks inside table cells do not matter."""
    return _SPACE.sub(" ", text).strip()


def page_texts(pdf: bytes) -> list[str]:
    return [normalise(p.extract_text()) for p in PdfReader(io.BytesIO(pdf)).pages]


def missing_text(rendered: Rendered) -> list[str]:
    """Requirements whose text is not found on their recorded page."""
    pages = page_texts(rendered.pdf)
    out = []
    for rid, placed in rendered.requirements.items():
        if not 1 <= placed.page <= len(pages):
            out.append(f"{rendered.filename} {rid}: page {placed.page} out of range")
        elif normalise(placed.text) not in pages[placed.page - 1]:
            out.append(f"{rendered.filename} {rid}: text not on page {placed.page}")
    return out
