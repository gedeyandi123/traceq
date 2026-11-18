"""``protocol_draft.json``: the Protocol Draft of a Review Package run, as read (spec #196,
"Outputs").

One row per Test Step read, in draft order: the requirement ids its header prints, its
Acceptance Criterion as printed with the value code read from it and its citation, the URS
limit of each requirement the draft's traceability table lists it under (read from that
requirement's verified URS citation, with the citation, or why it was not parsed), and why the
row was not compared. Then the traceability rows read, each with its citation. What the
citation check dropped is in ``run.json``.
"""

from __future__ import annotations

from typing import Any

from traceq.review.draft import DraftReading, DraftRow, Read
from traceq.runs.submission import DraftStep, cite
from traceq.traceability import Ambiguous, Citation


def _cite(c: Citation | None) -> dict[str, Any] | None:
    return None if c is None else {"doc": c.doc, "rev": c.rev, "page": c.page, "quote": c.quote}


def _value(v: Read) -> dict[str, Any] | None:
    if v is None:
        return None
    if isinstance(v, Ambiguous):
        return {"type": "ambiguous", "readings": list(v.readings)}
    return v.model_dump(mode="json", exclude_none=True)


def protocol_draft(package: str, reading: DraftReading, rows: list[DraftRow]) -> dict[str, Any]:
    doc = reading.doc
    return {
        "package": package,
        "document": {"doc_id": doc.doc_id, "rev": doc.rev, "sha256": doc.sha256},
        "test_steps": [
            {
                "id": r.step.id,
                "requirements": list(r.step.requirements),
                "acceptance": {
                    "printed": r.step.printed,
                    "value": _value(r.step.value),
                    "citation": _cite(r.step.citation),
                },
                "traced": [
                    {
                        "requirement": u.requirement,
                        "urs_limit": _value(u.value),
                        "citation": _cite(u.citation),
                        "not_parsed": u.not_parsed,
                    }
                    for u in r.traced
                ],
                "compared": r.not_compared is None,
                "not_compared": r.not_compared,
            }
            for r in rows
        ],
        "trace_rows": [
            {
                "requirement": t.requirement,
                "test_steps": list(t.steps),
                "citation": _cite(t.citation),
            }
            for t in reading.rows
        ],
    }


def draft_steps(rows: list[DraftRow]) -> tuple[DraftStep, ...]:
    """The submission's ``draft_steps``: the AC value only when code read one from the print
    (an ambiguous or unknown form leaves it empty), always with its verified citation."""
    out: list[DraftStep] = []
    for r in rows:
        v = r.step.value
        out.append(
            DraftStep(
                id=r.step.id,
                acceptance=None if v is None or isinstance(v, Ambiguous) else v,
                acceptance_citation=cite(r.step.citation),
                compared=r.not_compared is None,
                not_compared=r.not_compared,
            )
        )
    return tuple(out)
