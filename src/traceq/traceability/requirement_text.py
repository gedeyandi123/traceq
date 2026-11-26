"""The requirement text a reviewer reads: the printed id and the Kritis cell are dropped.

The ``segment`` answer for some URS pages returns the whole table row. The cleaned text is
for output only (matrix, Protocol Draft); the LLM requests keep ``Requirement.text`` as read.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_KRITIS_VALUES = frozenset({"Ya", "Tidak", "Yes", "No"})
_KRITIS = re.compile(r"\bkritis\b", re.IGNORECASE)
_PERSYARATAN = re.compile(r"\bpersyaratan\b", re.IGNORECASE)
_SEPARATORS = re.compile(r"[\s|]+")


def has_kritis_column(pages: Sequence[str]) -> bool:
    """Whether some line of some page holds both "Kritis" and "Persyaratan" (a table header)."""
    return any(
        _KRITIS.search(line) and _PERSYARATAN.search(line)
        for page in pages
        for line in page.splitlines()
    )


def clean_requirement_text(text: str, printed_id: str | None, kritis_column: bool) -> str:
    """Drop the printed id the text starts with and, when the document has a Kritis column,
    the one cell after it that is ``Ya``, ``Tidak``, ``Yes`` or ``No``. Anything else is kept."""
    if not printed_id or not text.startswith(printed_id):
        return text
    rest = text[len(printed_id) :]
    if rest and not (rest[0].isspace() or rest[0] == "|"):
        return text
    rest = rest.lstrip(" \t\r\n|")
    if kritis_column:
        parts = _SEPARATORS.split(rest, maxsplit=1)
        if parts[0] in _KRITIS_VALUES:
            rest = parts[1] if len(parts) > 1 else ""
    return rest
