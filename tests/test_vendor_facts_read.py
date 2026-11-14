"""Reading vendor Evidence facts from a scanned page (#78): a step whose quote rests on an OCR
entry the model scored below 0.9 is dropped, like one whose quote is not on the page. The
LLM here is a scripted fake."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from traceq.ai import Request, Response
from traceq.documents import Corpus, CorpusDocument, OcrLine, Page
from traceq.traceability import Dropped
from traceq.traceability.evidence import read_vendor_facts

SAT = CorpusDocument(
    doc_id="SAT-X",
    rev=0,
    type="sat",
    format="scan",
    language="en",
    path=Path("unused.pdf"),
    sha256="0" * 64,
)
BOX = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
PAGE = Page(
    1,
    "SAT-03 Timing E0-MS 61 s Pass\nSAT-04 Output 98 units/h Pass",
    ocr=(
        OcrLine("SAT-03", BOX, 0.99),
        OcrLine("Timing", BOX, 0.97),
        OcrLine("E0-MS", BOX, 0.82),
        OcrLine("61 s", BOX, 0.95),
        OcrLine("Pass", BOX, 0.99),
        OcrLine("SAT-04", BOX, 0.99),
        OcrLine("Output", BOX, 0.97),
        OcrLine("98 units/h", BOX, 0.96),
        OcrLine("Pass", BOX, 0.98),
    ),
)


@dataclass
class OneScanCorpus(Corpus):
    def read(self, doc: CorpusDocument) -> tuple[Page, ...]:
        return (PAGE,)


def step(sid: str, observed: str, quote: str) -> dict[str, object]:
    value = dict.fromkeys(("min", "max", "number", "unit", "text", "present"))
    return {
        "step": sid,
        "test": "test",
        "acceptance": "",
        "observed": observed,
        "result": "pass",
        "value": value | {"kind": "none"},
        "quote": quote,
    }


class FakeLLM:
    @property
    def model(self) -> str:
        return "scripted"

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        answer = {
            "site_approved_on": None,
            "executed_on": None,
            "steps": [
                step("SAT-03", "61 s", "SAT-03 Timing E0-MS 61 s Pass"),
                step("SAT-04", "98 units/h", "SAT-04 Output 98 units/h Pass"),
            ],
            "rows": [],
        }
        return [Response(json.dumps(answer), "scripted", 1, 1) for _ in requests]


def test_a_step_resting_on_an_uncertain_ocr_reading_is_dropped() -> None:
    corpus = OneScanCorpus(Path("."), "EQ", (SAT,))
    dropped: list[Dropped] = []
    facts = read_vendor_facts(corpus, FakeLLM(), dropped)
    assert [s.step for s in facts.steps] == ["SAT-04"]
    assert dropped == [Dropped("step", "SAT-X/SAT-03", "uncertain OCR reading")]
