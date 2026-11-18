"""``protocol_draft.json``: the Protocol Draft of a Review Package run, as read and judged (spec
#196, "Outputs").

One row per Test Step read, in draft order: the requirement ids its header prints, its
Acceptance Criterion as printed with the value code read from it and its citation, and for
each requirement the draft's traceability table lists it under: the URS limit (read from that
requirement's verified URS citation, with the citation, or why it was not parsed), whether
the AC deviates from it or why it was not compared, and the comparators available (the vendor
facts of the requirement's matrix row by document; empty: none). Then whether the row was
compared at all (why not), the traceability rows read, each with its citation, and the draft's
Check Findings (layer Rule) with the values they compared. What the citation check dropped
is in ``run.json``.
"""

from __future__ import annotations

from typing import Any

from traceq.review.draft import Comparator, DraftReading, DraftRow, Read
from traceq.review.draft_rules import DraftFinding
from traceq.runs.submission import DraftStep, Finding, cite
from traceq.traceability import Ambiguous, Citation


def _cite(c: Citation | None) -> dict[str, Any] | None:
    return None if c is None else {"doc": c.doc, "rev": c.rev, "page": c.page, "quote": c.quote}


def _value(v: Read) -> dict[str, Any] | None:
    if v is None:
        return None
    if isinstance(v, Ambiguous):
        return {"type": "ambiguous", "readings": list(v.readings)}
    return v.model_dump(mode="json", exclude_none=True)


def _comparator(c: Comparator) -> dict[str, Any]:
    return {
        "doc": c.doc,
        "rev": c.rev,
        "kind": c.kind,
        "facts": [
            {"name": f.name, "printed": f.printed, "citation": _cite(f.citation)} for f in c.facts
        ],
    }


def _finding(f: DraftFinding) -> dict[str, Any]:
    where = {"test_step": f.test_step} if f.test_step is not None else {"row": f.row}
    return {
        "type": f.type,
        "layer": "rule",
        **where,
        "requirement": f.requirement,
        "detail": f.detail,
        "ac": _value(f.ac),
        "urs_limit": _value(f.urs),
        "citations": [_cite(c) for c in f.citations],
    }


def protocol_draft(
    package: str, reading: DraftReading, rows: list[DraftRow], findings: list[DraftFinding]
) -> dict[str, Any]:
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
                        "requirement": c.urs.requirement,
                        "urs_limit": _value(c.urs.value),
                        "citation": _cite(c.urs.citation),
                        "not_parsed": c.urs.not_parsed,
                        "compared": c.not_compared is None,
                        "deviates": c.deviates,
                        "not_compared": c.not_compared,
                        "comparators": [_comparator(x) for x in c.comparators],
                    }
                    for c in r.traced
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
        "findings": [_finding(f) for f in findings],
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


def draft_findings_out(findings: list[DraftFinding]) -> tuple[Finding, ...]:
    """The draft's findings in ``submission.json``: each with its Test Step id or table row."""
    return tuple(
        Finding(
            type=f.type,
            detail=f.detail,
            citations=tuple(cite(c) for c in f.citations),
            test_step=f.test_step,
            row=f.row,
        )
        for f in findings
    )
