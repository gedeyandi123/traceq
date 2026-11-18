"""Check Findings on a Protocol Draft (spec #196, "Rules"): layer Rule, over values read with a
verified citation. The LLM reads; it never judges a limit.

- ``ac_deviates_from_urs``: a Test Step's AC accepts a value the URS limit of a requirement
  the draft's traceability table traces it to rejects (``traceq.review.compare``). Cites the
  AC in the draft and the URS sentence.
- ``requirement_not_tested``: a traceability row none of whose Test Step ids the draft prints
  outside the traceability table. The table itself prints every planned id, so code searches
  the pages with the rows read taken out; a Test Step whose reading the citation check
  dropped is still printed, so it causes no finding. An id inside a longer one (``OQ-2`` in
  ``OQ-22``) is not that id. Cites the row.

A finding names its Test Step id (or, for a table row, the row's requirement id). Its detail
is written from the values as parsed, never from quote text, so a re-run whose quote differs
only in length gives the same finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from traceq.documents import normalise
from traceq.review.draft import DraftReading, DraftRow, TraceRow
from traceq.review.printed import Limit, PrintedValue, Tolerance
from traceq.traceability import Ambiguous, Citation
from traceq.traceability.values import Number, Text

DraftType = Literal["ac_deviates_from_urs", "requirement_not_tested"]


@dataclass(frozen=True)
class DraftFinding:
    type: DraftType
    detail: str
    citations: tuple[Citation, ...]
    requirement: str
    test_step: str | None = None
    row: str | None = None
    """The traceability row's requirement id, for ``requirement_not_tested``."""
    ac: PrintedValue | None = None
    urs: PrintedValue | None = None
    """The values compared, as parsed."""


def _n(x: float) -> str:
    return f"{x:g}"


def _unit(v: Number | Limit) -> str:
    return f" {v.unit}" if v.unit else ""


def describe(v: PrintedValue) -> str:
    """A parsed value in words: ``at least 80 kN``, ``less than 0.8 µm``, ``20 to 30 mm``."""
    match v:
        case Number():
            return f"{_n(v.value)}{_unit(v)}"
        case Limit(min=lo, max=hi) if lo is not None and hi is not None:
            return f"{_n(lo)} to {_n(hi)}{_unit(v)}"
        case Limit(min=lo) if lo is not None:
            return f"{'more than' if v.min_exclusive else 'at least'} {_n(lo)}{_unit(v)}"
        case Limit():
            assert v.max is not None  # a Limit has at least one bound
            return f"{'less than' if v.max_exclusive else 'at most'} {_n(v.max)}{_unit(v)}"
        case Tolerance():
            return f"{_n(v.nominal)} {v.unit} ± {_n(v.tolerance)} {v.tolerance_unit}"
        case Text():
            return f"'{v.value}'"


def ac_deviates_from_urs(rows: list[DraftRow]) -> list[DraftFinding]:
    out: list[DraftFinding] = []
    for r in rows:
        for c in r.traced:
            if not c.deviates:
                continue
            ac, urs = r.step.value, c.urs.value
            assert ac is not None and urs is not None and c.urs.citation is not None
            assert not isinstance(ac, Ambiguous)
            detail = (
                f"{r.step.id} accepts {describe(ac)}, which {c.urs.requirement} rejects:"
                f" it requires {describe(urs)}."
            )
            out.append(
                DraftFinding(
                    "ac_deviates_from_urs",
                    detail,
                    (r.step.citation, c.urs.citation),
                    c.urs.requirement,
                    test_step=r.step.id,
                    ac=ac,
                    urs=urs,
                )
            )
    return out


def _outside_table(reading: DraftReading) -> list[str]:
    """The draft's pages with every traceability row read taken out of its page."""
    texts = [normalise(p.text) for p in reading.pages]
    for r in reading.rows:
        n = r.citation.page - 1
        texts[n] = texts[n].replace(normalise(r.citation.quote), " ")
    return texts


def _printed(step: str, texts: list[str]) -> bool:
    pattern = re.compile(rf"(?<![\w-]){re.escape(normalise(step))}(?![\w]|-\w)")
    return any(pattern.search(t) for t in texts)


def requirement_not_tested(reading: DraftReading) -> list[DraftFinding]:
    texts = _outside_table(reading)
    read = {s.id for s in reading.steps}
    by_requirement: dict[str, list[TraceRow]] = {}
    for r in reading.rows:
        by_requirement.setdefault(r.requirement, []).append(r)
    out: list[DraftFinding] = []
    for req, rows in by_requirement.items():
        steps = list(dict.fromkeys(s for r in rows for s in r.steps))
        if any(s in read or _printed(s, texts) for s in steps):
            continue
        detail = (
            f"The traceability table lists {req} under {', '.join(steps)}, but the draft has"
            " no such Test Step: the requirement is not tested."
        )
        cites = tuple(dict.fromkeys(r.citation for r in rows))
        out.append(DraftFinding("requirement_not_tested", detail, cites, req, row=req))
    return out


def draft_findings(reading: DraftReading, rows: list[DraftRow]) -> list[DraftFinding]:
    """Every Check Finding on the draft: by Test Step in draft order, then by table row."""
    return [*ac_deviates_from_urs(rows), *requirement_not_tested(reading)]
