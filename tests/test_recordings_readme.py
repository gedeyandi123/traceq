"""The spend table of ``recordings/README.md`` adds up: each row's total is the sum of its
cells, and the row totals add up to the stated total (#241)."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "recordings" / "README.md"
MONEY = re.compile(r"^\$(\d+\.\d{6})$")


def _section(text: str, heading: str) -> str:
    start = text.index(f"\n{heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def _cell(cell: str) -> Decimal:
    if cell == "–":
        return Decimal(0)
    m = MONEY.match(cell)
    assert m, f"not an amount: {cell!r}"
    return Decimal(m.group(1))


def test_spend_table_rows_add_up_to_the_total() -> None:
    cost = _section(README.read_text(encoding="utf-8"), "## Cost")
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in cost.splitlines()
        if line.startswith("| ") and not line.startswith("| Run |")
    ]
    assert rows
    totals: list[Decimal] = []
    for name, *cells, total in rows:
        assert sum(map(_cell, cells), Decimal(0)) == _cell(total), name
        totals.append(_cell(total))
    stated = re.search(r"^Total \$(\d+\.\d{6}) of the \$25", cost, re.M)
    assert stated
    assert sum(totals, Decimal(0)) == Decimal(stated.group(1))
