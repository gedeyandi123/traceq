"""Reading record facts from a page (ticket #76).

OCR may join a signature row and a stamp beside it into one line. The model copies that
line; the citation keeps only the span from the printed role to the last printed field, so
the stamp text never reaches the cited quote. The LLM here is a scripted fake.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from traceq.ai import Request, Response
from traceq.documents import Corpus
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
    """One calibration certificate whose single page prints ``text``."""

    text: str = ""

    def pages(self, doc: CorpusDocument) -> list[str]:
        return [self.text]


class FakeLLM:
    def __init__(self, signature: dict[str, object]) -> None:
        self.signature = signature

    @property
    def model(self) -> str:
        return "scripted"

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        answer = {
            "signatures": [self.signature],
            "instruments": [],
            "step_instruments": [],
            "deviations": [],
            "calculations": [],
        }
        return [Response(json.dumps(answer), "scripted", 1, 1) for _ in requests]


def cited(page: str, name: str, date: str, quote: str) -> str:
    corpus = OnePageCorpus(Path("."), "EQ", (DOC,), text=page)
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
    records, _ = read_records(corpus, FakeLLM(signature), dropped)
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
