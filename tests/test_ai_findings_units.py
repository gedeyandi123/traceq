"""AI Findings (spec #29, deterministic unit): the citation check on what the model reports.
A finding is kept only when every citation names a document given to the model and quotes
its cited page, and none rests on an uncertain OCR reading (#78); otherwise it is dropped
whole."""

from __future__ import annotations

import json
from typing import Any, get_args

from traceq.documents import OcrLine, Page
from traceq.review import AiType
from traceq.review.ai_findings import verify_findings
from traceq.review.prompts import AI_TYPES
from traceq.traceability import Citation, Dropped

BOX = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


def scanned(n: int, *rows: tuple[tuple[str, float], ...]) -> Page:
    """A scanned page: each row the entries the OCR model read on it, with their scores."""
    text = "\n".join(" ".join(t for t, _ in row) for row in rows)
    return Page(n, text, ocr=tuple(OcrLine(t, BOX, s) for row in rows for t, s in row))


PAGES = {
    ("SAT-X", 0): [
        scanned(
            1,
            (("Serial no.", 0.99), ("AB-1234", 0.97)),
            (("SAT-01", 0.99), ("Output 98 units/h", 0.95), ("Pass", 0.9)),
            (("E0-MS", 0.82), ("Stopwatch", 0.96), ("SW-11907", 0.95)),
        ),
        scanned(2, (("Executed by A. Person", 0.98),)),
    ],
    ("DS-X", 2): [Page(1, "Serial number AB-1243")],
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


def test_a_citation_resting_on_an_uncertain_ocr_reading_drops_the_finding() -> None:
    """``E0-MS`` is the model's misreading of a handwritten id, scored below 0.9: a quote
    that covers any of it, even in part, is not trusted."""
    dropped: list[Dropped] = []
    for quote in ("E0-MS Stopwatch SW-11907", "MS Stopwatch"):
        misread = SAT | {"quote": quote}
        assert verify_findings(answer(finding(misread, DS)), PAGES, dropped) == []
    assert dropped == [Dropped("ai_finding", "inconsistent_data 1", "uncertain OCR reading")] * 2


def test_a_citation_on_ocr_lines_scored_at_or_above_the_threshold_is_kept() -> None:
    dropped: list[Dropped] = []
    beside = SAT | {"quote": "Stopwatch SW-11907"}  # next to the misread entry, not on it
    at_threshold = SAT | {"quote": "98 units/h Pass"}  # "Pass" scored exactly 0.9
    (f,) = verify_findings(answer(finding(beside, at_threshold)), PAGES, dropped)
    assert [c.quote for c in f.citations] == ["Stopwatch SW-11907", "98 units/h Pass"]
    assert dropped == []


def test_a_born_digital_citation_is_never_uncertain() -> None:
    """A born-digital page has no OCR entries, whatever text it shares with a scan."""
    dropped: list[Dropped] = []
    pages = PAGES | {("DS-X", 2): [Page(1, "E0-MS Stopwatch SW-11907")]}
    ds = DS | {"quote": "E0-MS Stopwatch"}
    (f,) = verify_findings(answer(finding(ds)), pages, dropped)
    assert f.citations == (Citation("DS-X", 2, 1, "E0-MS Stopwatch"),)
    assert dropped == []


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
