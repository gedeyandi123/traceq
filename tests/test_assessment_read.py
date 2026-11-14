"""Coverage condition 1 from the Vendor Assessment in the corpus (ticket #55, spec #29).

The LLM reads which areas the assessment rates ``Ya`` and its date, each with a quote; the
citation check drops what the page does not print; the link call names the area of each
requirement; the decision table decides. The LLM here is a scripted fake.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from traceq.ai import Request, Response
from traceq.documents import Corpus
from traceq.traceability import Citation, Dropped
from traceq.traceability.assessment import Assessment, read_vendor_assessment
from traceq.traceability.coverage import Protocol
from traceq.traceability.evidence import (
    StepFact,
    VendorFacts,
    # StepFact holds the parsed model answer, which has no public type (test_review_units).
    _Value,  # pyright: ignore[reportPrivateUsage]
    link,
)
from traceq.traceability.values import Range
from traceq_dataset import render

ROOT = Path(__file__).parents[1]
MECHANICAL = "Mekanik (mechanical)"
CONTROL = "Sistem kendali dan perangkat lunak (control system/software)"

Answer = Callable[[Request], dict[str, Any]]


class FakeLLM:
    def __init__(self, **answers: Answer) -> None:
        self.answers = answers
        self.sent: list[Request] = []

    @property
    def model(self) -> str:
        return "scripted"

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.sent += requests
        return [
            Response(json.dumps(self.answers[r.prompt.name](r)), "scripted", 1, 1) for r in requests
        ]


def _pages(r: Request) -> dict[int, str]:
    return {int(m[1]): m[2] for m in re.finditer(r'<page n="(\d+)">\n(.*?)\n</page>', r.user, re.S)}


ROW = re.compile(r"^(?P<area>.+\)) (?P<mark>Ya|Tidak) .*$")


def read_rows(r: Request) -> dict[str, Any]:
    """Reads every area row as printed, and the issue date."""
    areas = [
        {
            "area": m["area"],
            "mark": m["mark"],
            "relied": m["mark"] == "Ya",
            "page": n,
            "quote": m[0],
        }
        for n, text in _pages(r).items()
        for line in text.splitlines()
        if (m := ROW.match(line))
    ]
    date = next(
        {"date": m[1], "page": n, "quote": m[0]}
        for n, text in _pages(r).items()
        for line in text.splitlines()
        if (m := re.match(r"^Tanggal berlaku (\S+)$", line))
    )
    return {"assessed_on": date, "areas": areas}


@pytest.fixture(scope="module")
def corpora(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Corpus]:
    out: dict[str, Corpus] = {}
    for name in ("tp201", "tp202"):
        dist = tmp_path_factory.mktemp(name)
        assert render.main([str(ROOT / "world" / f"{name}.yaml"), "--out", str(dist)]) == 0
        out[name] = Corpus.load(next(dist.glob("t0-*")))
    return out


def _read(corpus: Corpus, answer: Answer = read_rows) -> tuple[Assessment | None, list[Dropped]]:
    dropped: list[Dropped] = []
    return read_vendor_assessment(corpus, FakeLLM(vendor_assessment=answer), dropped), dropped


# --- Reading the assessment --------------------------------------------------------------


def test_tp201_assessment_relies_on_every_area_with_citations(corpora: dict[str, Corpus]) -> None:
    assessment, dropped = _read(corpora["tp201"])

    assert dropped == []
    assert assessment is not None
    assert assessment.doc == "VA-2025-011"
    assert [(a.name, a.relied) for a in assessment.areas] == [
        (MECHANICAL, True),
        (CONTROL, True),
        ("Integritas data (data integrity)", True),
        ("Dokumentasi (documentation)", True),
    ]
    assert all(a.citation.doc == "VA-2025-011" and a.citation.page == 1 for a in assessment.areas)
    assert assessment.assessed_on == dt.date(2025, 11, 13)
    assert assessment.date_citation is not None
    assert "13/11/2025" in assessment.date_citation.quote


def test_tp202_assessment_has_limited_scope(corpora: dict[str, Corpus]) -> None:
    assessment, _ = _read(corpora["tp202"])

    assert assessment is not None
    assert assessment.decision.scope == {MECHANICAL, "Dokumentasi (documentation)"}


def test_an_area_the_page_does_not_print_is_dropped(corpora: dict[str, Corpus]) -> None:
    def answer(r: Request) -> dict[str, Any]:
        a = read_rows(r)
        # Rated Ya, but the page prints Tidak: the mark is not in the quote.
        control = next(x for x in a["areas"] if x["area"] == CONTROL)
        control |= {"mark": "Ya", "relied": True}
        a["areas"].append(
            {"area": "Pembersihan", "mark": "Ya", "relied": True, "page": 1, "quote": "Ya"}
        )
        return a

    assessment, dropped = _read(corpora["tp202"], answer)

    assert assessment is not None
    assert CONTROL not in assessment.decision.scope
    assert "Pembersihan" not in {a.name for a in assessment.areas}
    assert {d.id for d in dropped} == {f"VA-2025-008 {CONTROL}", "VA-2025-008 Pembersihan"}


def test_no_assessment_in_the_corpus(corpora: dict[str, Corpus]) -> None:
    corpus = corpora["tp201"]
    without = dataclasses.replace(
        corpus, documents=tuple(d for d in corpus.documents if d.type != "vendor_assessment")
    )
    assessment, dropped = _read(without)
    assert assessment is None and dropped == []


# --- Condition 1 in the link step --------------------------------------------------------

SPEED = Range(min=20, max=70, unit="rpm")
FAT = Protocol("FAT-X", 0, "FAT", dt.date(2026, 1, 22), dt.date(2026, 2, 1))


def _facts() -> VendorFacts:
    step = StepFact(
        FAT,
        "FAT-01",
        "Turret speed",
        "20–70 rpm",
        "20–70 rpm",
        "pass",
        Citation("FAT-X", 0, 1, "FAT-01 Turret speed 20–70 rpm Pass"),
        "en",
        _Value(kind="range", min=20, max=70, number=None, unit="rpm", text=None, present=None),
    )
    return VendorFacts(steps=[step])


def _link(area: str | None) -> Answer:
    def answer(r: Request) -> dict[str, Any]:
        return {
            "steps": ["FAT-X/FAT-01"],
            "rows": [],
            "site_only": False,
            "transport_sensitive": False,
            "area": area,
        }

    return answer


def _linked(assessment: Assessment | None, area: str | None) -> tuple[Any, list[Dropped], FakeLLM]:
    dropped: list[Dropped] = []
    llm = FakeLLM(link=_link(area), transport=_link(area))
    requirements = [("URS-X-001", "Turret speed 20-70 rpm", SPEED)]
    out = link(requirements, _facts(), "u", llm, dropped, assessment)
    return out["URS-X-001"], dropped, llm


def test_an_area_outside_the_tp202_scope_is_not_covered_by_vendor(
    corpora: dict[str, Corpus],
) -> None:
    assessment, _ = _read(corpora["tp202"])
    assert assessment is not None

    control, _, llm = _linked(assessment, CONTROL)
    assert control.coverage.coverage == "partial"
    reason = f"FAT-01: condition 1: scope {CONTROL!r} not in vendor assessment"
    assert control.coverage.reason == reason
    assert control.area is not None and control.area.relied is False
    assert "Tidak" in control.area.citation.quote
    # The model is offered every area the assessment prints, not their rating.
    offered = json.loads(llm.sent[0].user)["areas"]
    assert offered == [a.name for a in assessment.areas] and "Tidak" not in " ".join(offered)

    mechanical, _, _ = _linked(assessment, MECHANICAL)
    assert (mechanical.coverage.coverage, mechanical.coverage.reason) == (
        "covered_by_vendor",
        "proved by FAT-X",
    )
    assert mechanical.area is not None and "Ya" in mechanical.area.citation.quote


def test_condition_1_fails_without_an_assessment() -> None:
    linked, _, llm = _linked(None, None)
    assert (linked.coverage.coverage, linked.coverage.reason) == (
        "partial",
        "FAT-01: condition 1: no Vendor Assessment",
    )
    assert json.loads(llm.sent[0].user)["areas"] == []


def test_an_area_the_assessment_does_not_print_is_dropped(corpora: dict[str, Corpus]) -> None:
    assessment, _ = _read(corpora["tp202"])
    linked, dropped, _ = _linked(assessment, "Pembersihan")
    assert linked.facts.scope is None and linked.area is None
    assert linked.coverage.reason == "FAT-01: condition 1: no assessed area named"
    assert dropped == [Dropped("link", "URS-X-001 Pembersihan", "unknown area")]
