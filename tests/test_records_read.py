"""Reading record facts from a page (tickets #76 and #78).

OCR may join a signature row and a stamp beside it into one line. The model copies that
line; the citation keeps only the span from the printed role to the last printed field, so
the stamp text never reaches the cited quote. A fact whose quote rests on an OCR entry the
model scored below 0.9 is dropped. The LLM here is a scripted fake.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from traceq.ai import Request, Response
from traceq.documents import Corpus, OcrLine, Page
from traceq.documents.corpus import CorpusDocument
from traceq.review.records import read_records
from traceq.traceability import Dropped

DOC = CorpusDocument(
    doc_id="CAL-0001",
    rev=1,
    type="calibration_certificate",
    format="scan",
    language="en",
    path=Path("unused.pdf"),
    sha256="0" * 64,
)


@dataclass
class OnePageCorpus(Corpus):
    """One calibration certificate whose single page is ``page``."""

    page: Page = field(default_factory=lambda: Page(1, ""))

    def read(self, doc: CorpusDocument) -> tuple[Page, ...]:
        return (self.page,)


class FakeLLM:
    def __init__(self, **facts: list[dict[str, object]]) -> None:
        self.answer: dict[str, list[dict[str, object]]] = {
            "signatures": [],
            "instruments": [],
            "step_instruments": [],
            "deviations": [],
            "calculations": [],
        } | facts

    @property
    def model(self) -> str:
        return "scripted"

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        return [Response(json.dumps(self.answer), "scripted", 1, 1) for _ in requests]


def cited(page: str, name: str, date: str, quote: str) -> str:
    corpus = OnePageCorpus(Path("."), "EQ", (DOC,), page=Page(1, page))
    signature = {
        "role_printed": "Calibrated by",
        "role": "executed",
        "site": False,
        "name": name,
        "signed": True,
        "date": date,
        "quote": quote,
    }
    dropped: list[Dropped] = []
    records, _ = read_records(corpus, FakeLLM(signatures=[signature]), dropped)
    assert dropped == []
    [s] = records[0].signatures
    return s.citation.quote


def test_stamp_text_after_the_name_is_not_cited() -> None:
    line = "Calibrated by Markus Brandt Brandt CALIBRATED"
    assert cited(line, "Markus Brandt", "", line) == "Calibrated by Markus Brandt"


def test_a_date_printed_last_stays_in_the_quote() -> None:
    line = "Calibrated by Markus Brandt 12.03.2025 CALIBRATED"
    assert (
        cited(line, "Markus Brandt", "12.03.2025", line) == "Calibrated by Markus Brandt 12.03.2025"
    )


def test_a_minimal_quote_is_unchanged() -> None:
    line = "Calibrated by Markus Brandt 12.03.2025"
    assert cited(f"Certificate\n{line}\nEnd", "Markus Brandt", "12.03.2025", line) == line


BOX = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
SCAN = Page(
    1,
    "SAT-03 TACH-07 E0-MS\nSAT-04 TACH-07",
    ocr=(
        OcrLine("SAT-03", BOX, 0.99),
        OcrLine("TACH-07 E0-MS", BOX, 0.82),  # a joined cell: its lowest line's score
        OcrLine("SAT-04", BOX, 0.99),
        OcrLine("TACH-07", BOX, 0.95),
    ),
)


def test_a_fact_resting_on_an_uncertain_ocr_reading_is_dropped() -> None:
    corpus = OnePageCorpus(Path("."), "EQ", (DOC,), page=SCAN)
    uses = [
        {"step": "SAT-03", "instruments": ["E0-MS"], "quote": "SAT-03 TACH-07 E0-MS"},
        {"step": "SAT-04", "instruments": ["TACH-07"], "quote": "SAT-04 TACH-07"},
    ]
    dropped: list[Dropped] = []
    records, _ = read_records(corpus, FakeLLM(step_instruments=uses), dropped)
    assert [(u.step, u.instrument) for u in records[0].uses] == [("SAT-04", "TACH-07")]
    assert dropped == [Dropped("instrument", "CAL-0001 p1 SAT-03", "uncertain OCR reading")]
