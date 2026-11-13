"""``matrix.json``: the traceability matrix of a run, for the UI.

One row per requirement: its URS sentence and value with their citation, the Coverage class
and its reason (the first failing condition of the decision table), the two properties the
LLM judged, each Evidence step with its citation and verdict, and the design facts compared
with the URS value.
"""

from __future__ import annotations

from typing import Any

from traceq.traceability import Ambiguous, Citation, Traceability, Value
from traceq.traceability.coverage import Observed


def _cite(c: Citation) -> dict[str, Any]:
    return {"doc": c.doc, "rev": c.rev, "page": c.page, "quote": c.quote}


def _value(v: Value | None) -> dict[str, Any] | None:
    return None if v is None else v.model_dump(mode="json", exclude_none=True)


def _observed(v: Observed | None) -> dict[str, Any] | None:
    if isinstance(v, Ambiguous):
        return {"type": "ambiguous", "readings": list(v.readings)}
    return _value(v)


def matrix(t: Traceability) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for r in t.requirements:
        claim = t.values.get(r.id)
        linked = t.linked.get(r.id)
        row: dict[str, Any] = {
            "id": r.id,
            "text": r.text,
            "source": _cite(r.citation),
            "value": None if claim is None else _value(claim.value),
            "value_citation": None if claim is None else _cite(claim.citation),
            "coverage": None,
            "reason": None,
            "site_only": None,
            "transport_sensitive": None,
            "evidence": [],
            "design": [],
        }
        if linked is not None:
            row |= {
                "coverage": linked.coverage.coverage,
                "reason": linked.coverage.reason,
                "site_only": linked.facts.site_only,
                "transport_sensitive": linked.facts.transport_sensitive,
                "evidence": [
                    {
                        "doc": s.protocol.doc,
                        "rev": s.protocol.rev,
                        "stage": s.protocol.stage,
                        "step": s.step,
                        "test": s.test,
                        "acceptance": s.acceptance,
                        "observed": s.observed,
                        "observed_value": _observed(v.step.observed),
                        "result": s.result,
                        "failure": v.failure,
                        "citation": _cite(s.citation),
                    }
                    for s, v in zip(linked.steps, linked.coverage.verdicts, strict=True)
                ],
                "design": [
                    {
                        "doc": d.fact.doc,
                        "rev": d.fact.rev,
                        "name": d.name,
                        "printed": d.printed,
                        "value": _value(d.fact.value),
                        "citation": _cite(d.citation),
                    }
                    for d in linked.rows
                ],
            }
        rows.append(row)
    return {
        "requirements": rows,
        "not_read": [
            {"doc_id": d.doc_id, "rev": d.rev, "format": d.format} for d in t.vendor.not_read
        ],
    }
