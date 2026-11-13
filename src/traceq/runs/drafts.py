"""``drafts.json``: the drafted IQ/OQ Test Steps of a run, as AI Findings (ADR 0002).

Each draft carries what an audit of an AI Finding needs: the source document and revision
(the URS the requirement is printed in), model, prompt hash, time and the reviewer's action,
``pending`` until a write feature lets a human accept, edit or reject it. An AC is present
only when copied from a verified citation; otherwise ``acceptance_flag`` says why it is "to
be set by a human". ``saved_by_reuse`` marks a draft made only because the run set
``vendor_reuse`` false: reusing the vendor's Evidence could save it.
"""

from __future__ import annotations

from typing import Any

from traceq.protocols import Drafts
from traceq.traceability import Citation


def _cite(c: Citation) -> dict[str, Any]:
    return {"doc": c.doc, "rev": c.rev, "page": c.page, "quote": c.quote}


def drafts(d: Drafts, *, model: str, prompt: str, created: str) -> dict[str, Any]:
    return {
        "vendor_reuse": d.vendor_reuse,
        "test_steps": [
            {
                "id": x.id,
                "requirement": x.requirement.id,
                "requirement_text": x.requirement.text,
                "coverage": x.coverage,
                "saved_by_reuse": x.saved_by_reuse,
                "description": x.description,
                "method": x.method,
                "instrument": x.instrument,
                "acceptance": None
                if x.acceptance.value is None
                else x.acceptance.value.model_dump(mode="json"),
                "acceptance_citation": None
                if x.acceptance.citation is None
                else _cite(x.acceptance.citation),
                "acceptance_flag": x.acceptance.flag,
                "layer": "ai",
                "source": {"doc": x.requirement.citation.doc, "rev": x.requirement.citation.rev},
                "model": model,
                "prompt": prompt,
                "created": created,
                "reviewer_action": "pending",
            }
            for x in d.drafts
        ],
    }
