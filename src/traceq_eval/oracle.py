"""The perfect submission for an answer key: what a flawless system would hand in.

It is the reference shape of a submission and the upper bound of every metric; the tests
score it, and broken variants of it, against the committed key.
"""

from __future__ import annotations

from typing import Any

from traceq_dataset.review_package import comparable
from traceq_eval.citations import MAX_QUOTE
from traceq_eval.ocr import expected_entries
from traceq_eval.score import NEEDS_SITE_TEST, Key, ReviewPackage
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
    planted = {d["scenario"] for d in key["defects.yaml"] if d["type"] == "ambiguous_value"}
    findings += [
        {
            "type": "ambiguous_value",
            "detail": f"'{loc['text']}' reads two ways; ask for confirmation",
            "citations": [{**_where(loc), "quote": loc["text"]}],
        }
        for a in key["ambiguous.yaml"]
        if a.get("scenario") not in planted
        for loc in [a["location"]]
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


def perfect_review(key: Key, package: ReviewPackage) -> Submission:
    """The perfect submission for a Review Package: the Equipment's perfect answers, every
    Test Step of the draft read with its citation (compared when its URS value is a one-sided
    limit or a single number), and each planted defect reported on its Test Step or table
    row, citing the draft and, for an AC, the URS sentence it is compared with."""
    equipment = perfect(key, package.equipment)
    reqs = key["requirements.yaml"]
    compared = set(comparable(reqs))
    traced = {r["id"]: r for r in reqs}
    steps = []
    for s in package.key["test_steps.yaml"]:
        loc = s["location"]
        is_compared = any(r in compared for r in s["requirements"])
        steps.append(
            {
                "id": s["id"],
                "acceptance": s["acceptance"],
                "acceptance_citation": {**_where(loc), "quote": loc["text"]},
                "compared": is_compared,
                **(
                    {}
                    if is_compared
                    else {"not_compared": "URS value is not a one-sided limit or a number"}
                ),
            }
        )
    findings = []
    for d in package.key["defects.yaml"]:
        urs = d.get("compared_with")
        cites = [{**_where(loc), "quote": loc["text"]} for loc in d["locations"]]
        if urs:
            text = traced[urs["requirement"]]["text"][:MAX_QUOTE]
            cites.append({**_where(urs), "quote": text})
        findings.append(
            {
                "type": d["type"],
                "severity": d["severity"],
                "detail": d["detail"],
                "citations": cites,
                **({"test_step": d["test_step"]} if "test_step" in d else {"row": d["row"]}),
            }
        )
    base = equipment.model_dump(mode="json", exclude_none=True)
    return Submission.model_validate(
        {
            **base,
            "findings": [*base["findings"], *findings],
            "review_package": package.id,
            "draft_steps": steps,
        }
    )


def _where(x: dict[str, Any]) -> dict[str, Any]:
    return {"doc": x["doc"], "rev": x["rev"], "page": x["page"]}
