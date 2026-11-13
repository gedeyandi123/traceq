"""Segmentation of a URS with and without printed requirement ids (ticket #60, spec #29).

A URS in prose or unnumbered tables prints no requirement numbers: the model returns each
requirement with a null id and a verbatim quote, and the system assigns an id that depends
only on the document, the page and the requirement's place on it. The LLM is a scripted
fake over invented pages; nothing here comes from TP-201 or TP-202.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from traceq.ai import Request, Response
from traceq.documents import Corpus
from traceq.documents.cache import IngestCache, Ingested
from traceq.documents.corpus import CorpusDocument
from traceq.documents.pages import Page
from traceq.documents.pdf import PDF_VERSION
from traceq.traceability import trace

NUMBERED = "R-01 The press runs at 10 to 40 rpm.\nR-02 Guards are interlocked."
PROSE = (
    "2. Operation\nThe dryer shall hold the inlet air at 40 to 80 °C. Product contact parts"
    " are made of SS 316L.\nUtilities\nCompressed air | 6 bar, oil-free"
)
SEGMENTS: dict[int, list[dict[str, Any]]] = {
    1: [
        {"id": "R-01", "text": "The press runs at 10 to 40 rpm.", "quote": "R-01 The press runs"},
        {"id": "R-02", "text": "Guards are interlocked.", "quote": "Guards are interlocked."},
    ],
    2: [
        {
            "id": None,
            "text": "The dryer shall hold the inlet air at 40 to 80 °C.",
            "quote": "The dryer shall hold the inlet air at 40 to 80 °C.",
        },
        # Not on the page: dropped under its system id.
        {"id": None, "text": "The dryer flies.", "quote": "The dryer flies."},
        {
            "id": "",
            "text": "Product contact parts are made of SS 316L.",
            "quote": "Product contact parts\n are made of SS 316L.",
        },
        {
            "id": None,
            "text": "Compressed air: 6 bar, oil-free",
            "quote": "Compressed air | 6 bar, oil-free",
        },
    ],
}


class FakeLLM:
    @property
    def model(self) -> str:
        return "scripted"

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        return [Response(json.dumps(self._answer(r)), "scripted", 1, 1) for r in requests]

    def _answer(self, r: Request) -> dict[str, Any]:
        if r.prompt.name == "segment":
            page = int(r.user.split(", page ", 1)[1].split(".", 1)[0])
            return {"requirements": SEGMENTS[page]}
        if r.prompt.name == "extract":
            blank = dict.fromkeys(("min", "max", "number", "unit", "text"))
            return {"kind": "none", **blank, "allowed": [], "quote": ""}
        if r.prompt.name == "link":
            return {
                "steps": [],
                "rows": [],
                "site_only": False,
                "transport_sensitive": False,
                "area": None,
            }
        raise AssertionError(r.prompt.name)


def _corpus(tmp_path: Path) -> Corpus:
    doc = CorpusDocument("URS-X", 0, "urs", "born_digital", "en", tmp_path / "u.pdf", "abc")
    cache = IngestCache(tmp_path / "ingest")
    pages = (Page(1, NUMBERED), Page(2, PROSE))
    cache.put(Ingested("abc", PDF_VERSION, "fake", pages, (0.0, 0.0), 0.0, None))
    return Corpus(tmp_path, "X", (doc,), cache=cache)


def test_unnumbered_requirements_get_a_system_id_and_keep_their_quote(tmp_path: Path) -> None:
    t = trace(_corpus(tmp_path), FakeLLM())

    assert [(r.id, r.citation.page, r.citation.quote) for r in t.requirements] == [
        ("R-01", 1, "R-01 The press runs"),
        ("R-02", 1, "Guards are interlocked."),
        ("URS-X-p2-01", 2, "The dryer shall hold the inlet air at 40 to 80 °C."),
        ("URS-X-p2-03", 2, "Product contact parts\n are made of SS 316L."),
        ("URS-X-p2-04", 2, "Compressed air | 6 bar, oil-free"),
    ]
    assert [(d.id, d.reason) for d in t.dropped] == [("URS-X-p2-02", "quote not on page")]


def test_system_ids_are_stable_across_runs(tmp_path: Path) -> None:
    first = [r.id for r in trace(_corpus(tmp_path / "a"), FakeLLM()).requirements]
    second = [r.id for r in trace(_corpus(tmp_path / "b"), FakeLLM()).requirements]
    assert first == second
