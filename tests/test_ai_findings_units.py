"""AI Findings (spec #29, deterministic unit): the citation check on what the model reports.
A finding is kept only when every citation names a document given to the model and quotes
its cited page; otherwise it is dropped whole."""

from __future__ import annotations

import json
from typing import Any, get_args

from traceq.review import AiType
from traceq.review.ai_findings import verify_findings
from traceq.review.prompts import AI_TYPES
from traceq.traceability import Citation, Dropped

PAGES = {
    ("SAT-X", 0): ["Serial no. AB-1234\nSAT-01 Output 98 units/h Pass", "Executed by A. Person"],
    ("DS-X", 2): ["Serial number AB-1243"],
}
SAT = {"doc": "SAT-X", "rev": 0, "page": 1, "quote": "Serial no. AB-1234"}
DS = {"doc": "DS-X", "rev": 2, "page": 1, "quote": "Serial number AB-1243"}


def finding(*cites: dict[str, Any], kind: str = "inconsistent_data") -> dict[str, Any]:
    return {"type": kind, "detail": "Serial numbers differ.", "citations": list(cites)}


def answer(*findings: dict[str, Any]) -> str:
    return json.dumps({"findings": list(findings)})


def test_a_finding_whose_citations_all_verify_is_kept() -> None:
    dropped: list[Dropped] = []
    (f,) = verify_findings(answer(finding(SAT, DS)), PAGES, dropped)
    assert f.type == "inconsistent_data"
    assert f.citations == (Citation(**SAT), Citation(**DS))
    assert dropped == []


def test_one_unverifiable_citation_drops_the_whole_finding() -> None:
    dropped: list[Dropped] = []
    invented = DS | {"quote": "Serial number AB-9999"}
    assert verify_findings(answer(finding(SAT, invented)), PAGES, dropped) == []
    assert dropped == [Dropped("ai_finding", "inconsistent_data 1", "quote not on page")]


def test_a_quote_on_another_page_does_not_verify() -> None:
    dropped: list[Dropped] = []
    assert verify_findings(answer(finding(SAT | {"page": 2})), PAGES, dropped) == []
    assert verify_findings(answer(finding(SAT | {"page": 3})), PAGES, dropped) == []
    assert [d.reason for d in dropped] == ["quote not on page"] * 2


def test_a_document_not_given_to_the_model_cannot_be_cited() -> None:
    dropped: list[Dropped] = []
    other_rev = DS | {"rev": 1}
    assert verify_findings(answer(finding(SAT, other_rev)), PAGES, dropped) == []
    assert dropped == [Dropped("ai_finding", "inconsistent_data 1", "document not given")]


def test_a_finding_without_citation_or_detail_is_dropped() -> None:
    dropped: list[Dropped] = []
    blank = finding(SAT) | {"detail": "  "}
    assert verify_findings(answer(blank), PAGES, dropped) == []
    assert verify_findings(answer(finding()), PAGES, dropped) == []
    assert [d.reason for d in dropped] == ["no detail", "bad answer"]


def test_a_type_outside_the_ai_layer_is_a_bad_answer() -> None:
    """The rule layer's types are never reported by the model."""
    dropped: list[Dropped] = []
    assert verify_findings(answer(finding(SAT, kind="missing_signature")), PAGES, dropped) == []
    assert dropped == [Dropped("ai_finding", "ai_review", "bad answer")]


def test_the_same_finding_twice_is_reported_once() -> None:
    dropped: list[Dropped] = []
    gdp = finding(SAT | {"quote": "98 units/h"}, kind="gdp_correction")
    found = verify_findings(answer(gdp, gdp, finding(SAT, DS)), PAGES, dropped)
    assert [f.type for f in found] == ["gdp_correction", "inconsistent_data"]


def test_the_prompt_offers_exactly_the_ai_types() -> None:
    assert get_args(AiType) == AI_TYPES
