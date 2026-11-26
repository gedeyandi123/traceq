"""The requirement text a reviewer reads: the printed id and the Kritis cell are dropped.

The ``segment`` answer for some URS pages returns the whole table row. The cleaned text is
for output only (matrix, Protocol Draft); the LLM requests keep ``Requirement.text`` as read.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_KRITIS_VALUES = frozenset({"Ya", "Tidak", "Yes", "No"})
_HEADER = re.compile(
    r"^[\s|]*(?:no\.?(?=[\s|])[\s|]*)?kritis(?=[\s|])[\s|]*persyaratan\b", re.IGNORECASE
)
_SEPARATORS = re.compile(r"[\s|]+")


def has_kritis_column(pages: Sequence[str]) -> bool:
    """Whether some line of some page is a table header: ``[No.] Kritis Persyaratan``."""
    return any(_HEADER.match(line) for page in pages for line in page.splitlines())


def clean_requirement_text(text: str, printed_id: str | None, kritis_column: bool) -> str:
    """Drop the printed id the text starts with and, when the document has a Kritis column,
    the one cell after it that is ``Ya``, ``Tidak``, ``Yes`` or ``No``. Anything else is kept,
    and a result that would be empty gives the original text.

    In a ``|``-delimited row an empty first cell is no Kritis cell. In a whitespace-delimited
    row a blank cell cannot be told from text, so the first word is taken as the cell when it
    is one of the values; a row with a Kritis column is assumed to print a value in it.
    """
    if not printed_id or not text.startswith(printed_id):
        return text
    rest = text[len(printed_id) :]
    if rest and not (rest[0].isspace() or rest[0] == "|"):
        return text
    rest = rest.lstrip()
    if rest.startswith("|"):
        first, _, after = rest[1:].partition("|")
        rest = after if kritis_column and first.strip() in _KRITIS_VALUES else rest[1:]
    elif kritis_column:
        parts = _SEPARATORS.split(rest, maxsplit=1)
        if parts[0] in _KRITIS_VALUES:
            rest = parts[1] if len(parts) > 1 else ""
    rest = rest.strip(" \t\r\n|")
    return rest or text
