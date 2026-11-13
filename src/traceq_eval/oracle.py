"""The perfect submission for an answer key: what a flawless system would hand in.

It is the reference shape of a submission and the upper bound of every metric; the tests
score it, and broken variants of it, against the committed key.
"""

from __future__ import annotations

from typing import Any

from traceq_eval.citations import MAX_QUOTE
from traceq_eval.ocr import expected_entries
from traceq_eval.score import NEEDS_SITE_TEST, Key
from traceq_eval.submission import Submission


def perfect(key: Key, equipment: str) -> Submission:
    requirements, steps = [], []
    for r in key["requirements.yaml"]:
        src = r["source"]
        source = {**_where(src), "quote": r["text"][:MAX_QUOTE], "value": r["value"]}
        covered = r["expected_coverage"] == "covered_by_vendor"
        evidence = [e for e in r["evidence"] if e["qualifies"]] if covered else []
        requirements.append(
            {
                "id": r["id"],
                "value": r["value"],
                "coverage": r["expected_coverage"],
                "citations": [
                    source,
                    *({**_where(e), "quote": e["observed"], "value": e["value"]} for e in evidence),
                ],
                "evidence": [
                    {"doc": e["doc"], "rev": e["rev"], "step": e["step"]} for e in evidence
                ],
            }
        )
        if r["expected_coverage"] in NEEDS_SITE_TEST:
            steps.append(
                {
                    "id": f"OQ-{r['id'].rsplit('-', 1)[-1]}",
                    "requirement": r["id"],
                    "description": f"Verify: {r['text']}",
                    "acceptance": r["value"],
                    "acceptance_citation": source,
                }
            )
    findings = [
        {
            "type": d["type"],
            "severity": d["severity"],
            "detail": d["detail"],
            "citations": [
                {**_where(loc), "quote": loc["text"]} for loc in d["locations"] if "page" in loc
            ],
        }
        for d in key["defects.yaml"]
    ]
    missing = [
        {"type": d["type"], "stage": d["stage"], "id": d["id"]}
        for d in key["documents.yaml"]
        if d["status"] != "in_corpus"
    ]
    return Submission.model_validate(
        {
            "equipment": equipment,
            "system": {"name": "oracle"},
            "requirements": requirements,
            "findings": findings,
            "missing_documents": missing,
            "test_steps": steps,
            "ocr": [
                {k: e[k] for k in ("doc", "rev", "page", "text", "quad")}
                for e in expected_entries(key)
            ],
        }
    )


def _where(x: dict[str, Any]) -> dict[str, Any]:
    return {"doc": x["doc"], "rev": x["rev"], "page": x["page"]}
