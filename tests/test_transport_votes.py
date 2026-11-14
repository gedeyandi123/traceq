"""Votes on ``transport_sensitive`` before a FAT-only ``covered_by_vendor`` (#88).

The ``link`` answer's ``transport_sensitive`` bit is noisy. When it alone lets FAT steps
cover a requirement, the same request is asked again until there are ``TRANSPORT_VOTES``
answers; any ``true`` makes the requirement transport-sensitive.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from traceq.ai import Budget, PriceTable, Recorder, Request, Response
from traceq.ai.cost import Price
from traceq.ai.port import sha256
from traceq.traceability import Citation, Dropped
from traceq.traceability.assessment import Area, Assessment
from traceq.traceability.coverage import Protocol
from traceq.traceability.evidence import (
    TRANSPORT_VOTES,
    StepFact,
    VendorFacts,
    # StepFact holds the parsed model answer, which has no public type (test_review_units).
    _Value,  # pyright: ignore[reportPrivateUsage]
    link,
)
from traceq.traceability.prompts import LINK
from traceq.traceability.values import Range

AREA = "Mechanical"
SPEED = Range(min=20, max=70, unit="rpm")
FAT = Protocol("FAT-X", 0, "FAT", dt.date(2026, 1, 22), dt.date(2026, 2, 1))
SAT = Protocol("SAT-X", 0, "SAT", dt.date(2026, 3, 1), dt.date(2026, 3, 10))
CONDITION_4 = "condition 4: transport-sensitive and not retested at SAT (CPOB 12.24)"
ASSESSMENT = Assessment("VA-X", 0, "va", (Area(AREA, True, Citation("VA-X", 0, 1, f"{AREA} Ya")),))


def _step(protocol: Protocol, step: str) -> StepFact:
    return StepFact(
        protocol,
        step,
        "Turret speed",
        "20–70 rpm",
        "20–70 rpm",
        "pass",
        Citation(protocol.doc, 0, 1, f"{step} Turret speed 20–70 rpm Pass"),
        "en",
        _Value(kind="range", min=20, max=70, number=None, unit="rpm", text=None, present=None),
    )


FACTS = VendorFacts(steps=[_step(FAT, "FAT-01"), _step(SAT, "SAT-01")])


def _answer(sensitive: bool, steps: Sequence[str] = ("FAT-X/FAT-01",)) -> str:
    return json.dumps(
        {
            "steps": list(steps),
            "rows": [],
            "site_only": False,
            "transport_sensitive": sensitive,
            "area": AREA,
        }
    )


class Scripted:
    """Answers each requirement's ``link`` request by its sample index."""

    model = "scripted"

    def __init__(self, script: dict[str, list[str]]) -> None:
        self.script = script
        self.batches: list[list[Request]] = []

    def complete(self, requests: Sequence[Request]) -> list[Response]:
        self.batches.append(list(requests))
        out: list[Response] = []
        for r in requests:
            rid = json.loads(r.user)["requirement"]["id"]
            out.append(Response(self.script[rid][r.sample], "scripted", 1, 1))
        return out


def _run(script: dict[str, list[str]]) -> tuple[dict[str, Any], list[Dropped], Scripted]:
    llm = Scripted(script)
    dropped: list[Dropped] = []
    requirements = [(rid, f"{rid} turret speed 20-70 rpm", SPEED) for rid in script]
    return link(requirements, FACTS, "u", llm, dropped, ASSESSMENT), dropped, llm


def test_three_votes_in_all() -> None:
    assert TRANSPORT_VOTES == 3


def test_one_true_vote_makes_the_requirement_transport_sensitive() -> None:
    out, dropped, llm = _run({"R": [_answer(False), _answer(False), _answer(True)]})
    r = out["R"]
    assert (r.coverage.coverage, r.coverage.reason) == ("partial", CONDITION_4)
    assert r.facts.transport_sensitive is True
    assert dropped == []
    assert len(llm.batches) == 2
    first, votes = llm.batches
    assert [v.sample for v in votes] == [1, 2]
    assert all(v.user == first[0].user and v.doc_sha256 == first[0].doc_sha256 for v in votes)


def test_all_votes_false_keeps_covered_by_vendor() -> None:
    out, _, llm = _run({"R": [_answer(False)] * 3})
    assert (out["R"].coverage.coverage, out["R"].coverage.reason) == (
        "covered_by_vendor",
        "proved by FAT-X",
    )
    assert out["R"].facts.transport_sensitive is False
    assert [len(b) for b in llm.batches] == [1, 2]


def test_only_the_bit_is_taken_from_a_vote() -> None:
    out, _, _ = _run({"R": [_answer(False), _answer(False, ["SAT-X/SAT-01"]), _answer(False, [])]})
    assert [s.id for s in out["R"].steps] == ["FAT-X/FAT-01"]
    assert out["R"].coverage.coverage == "covered_by_vendor"


def test_no_vote_when_sat_qualifies_or_the_class_is_not_covered_by_vendor() -> None:
    out, _, llm = _run(
        {
            "sat": [_answer(False, ["FAT-X/FAT-01", "SAT-X/SAT-01"])],
            "partial": [_answer(True)],
            "gap": [_answer(False, [])],
            "fat-a": [_answer(False)] * 3,
            "fat-b": [_answer(False)] * 3,
        }
    )
    assert out["sat"].coverage.coverage == "covered_by_vendor"
    assert out["partial"].coverage.coverage == "partial"
    assert out["gap"].coverage.coverage == "gap"
    assert len(llm.batches) == 2
    voted = [(json.loads(r.user)["requirement"]["id"], r.sample) for r in llm.batches[1]]
    assert voted == [("fat-a", 1), ("fat-a", 2), ("fat-b", 1), ("fat-b", 2)]


def test_no_vote_batch_when_nothing_needs_one() -> None:
    _, _, llm = _run({"partial": [_answer(True)]})
    assert len(llm.batches) == 1


def test_an_unparsable_vote_counts_as_true_and_is_dropped() -> None:
    out, dropped, _ = _run({"R": [_answer(False), "not json", _answer(False)]})
    assert (out["R"].coverage.coverage, out["R"].coverage.reason) == ("partial", CONDITION_4)
    assert dropped == [Dropped("link", "R vote 1", "bad answer")]


# --- Recording keys ----------------------------------------------------------------------


def _key_before_votes(rec: Recorder, r: Request) -> str:
    """The recording key as it was before #88: every existing recording uses it."""
    return sha256(
        json.dumps(
            {
                "doc": r.doc_sha256,
                "pipeline": rec.pipeline_version,
                "prompt": r.prompt.hash,
                "model": rec.model,
                "input": r.input_hash,
            },
            sort_keys=True,
        )
    )


def test_the_first_answer_keeps_its_key_and_each_vote_has_its_own(tmp_path: Path) -> None:
    rec = Recorder(tmp_path, "m", "1")
    first = Request(LINK, "u", "d")
    assert first.sample == 0
    assert rec.key(first) == _key_before_votes(rec, first)
    keys = {rec.key(Request(LINK, "u", "d", sample=i)) for i in range(TRANSPORT_VOTES)}
    assert len(keys) == TRANSPORT_VOTES


def test_a_vote_records_its_sample_index(tmp_path: Path) -> None:
    class Echo:
        model = "m"

        def complete(self, requests: Sequence[Request]) -> list[Response]:
            return [Response(r.user, "m", 1, 1) for r in requests]

    prices = PriceTable(batch_discount=0.5, models={"m": Price(1.0, 1.0)})
    rec = Recorder(tmp_path, "m", "1", live=Echo(), budget=Budget(1.0, prices))
    vote = Request(LINK, "u", "d", sample=2)
    rec.complete([vote])
    saved = json.loads((tmp_path / f"{rec.key(vote)}.json").read_text(encoding="utf-8"))
    assert saved["sample"] == 2
    first = Request(LINK, "u", "d")
    rec.complete([first])
    saved = json.loads((tmp_path / f"{rec.key(first)}.json").read_text(encoding="utf-8"))
    assert "sample" not in saved
