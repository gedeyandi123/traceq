"""Findings on a Protocol Draft as Proposals, their decisions, and the Protocol Draft route,
over HTTP with a real Postgres and the demo issuer (spec #196, "Proposals and decisions" and
"API and screen"; ticket #209).

Each test copies the fixture run of ``tests/test_proposals_api.py`` and adds a
``protocol_draft.json`` as a Review Package run writes it, changed where the test needs.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from test_proposals_api import (
    OTHER_RUN,
    RUN_ID,
    add_run,
    bearer,
    configured,
    decide,
    import_run,
    proposals,
    refused,
    token,
)

from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.runs.schemas import ProtocolDraft

URS = {"doc": "URS-TP201", "rev": 1}
DRAFT = {"doc": "OQ-TP201", "rev": 0}


def _cite(doc: dict[str, Any], page: int, quote: str) -> dict[str, Any]:
    return {**doc, "page": page, "quote": quote}


def _limit(**bounds: Any) -> dict[str, Any]:
    return {"type": "range", "unit": "dB(A)", **bounds}


def _step(step: str, requirements: list[str], printed: str, ac: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": step,
        "requirements": requirements,
        "acceptance": {
            "printed": printed,
            "value": ac,
            "citation": _cite(DRAFT, 2, f"{step} Kebisingan {printed}"),
        },
        "traced": [
            {
                "requirement": r,
                "urs_limit": _limit(max=60),
                "citation": _cite(URS, 3, "Kebisingan maksimal 60 dB(A)."),
                "not_parsed": None,
                "compared": True,
                "deviates": True,
                "not_compared": None,
                "comparators": [],
            }
            for r in requirements
        ],
        "compared": True,
        "not_compared": None,
    }


def _deviates(step: str, requirement: str, ac_max: float) -> dict[str, Any]:
    return {
        "type": "ac_deviates_from_urs",
        "layer": "rule",
        "test_step": step,
        "row": None,
        "requirement": requirement,
        "detail": (
            f"{step} accepts at most {ac_max:g} dB(A), which {requirement} rejects:"
            " it requires at most 60 dB(A)."
        ),
        "ac": _limit(max=ac_max),
        "urs_limit": _limit(max=60),
        "citations": [
            _cite(DRAFT, 2, f"{step} Kebisingan maks. {ac_max:g} dB(A)"),
            _cite(URS, 3, "Kebisingan maksimal 60 dB(A)."),
        ],
    }


def protocol_draft() -> dict[str, Any]:
    """OQ-03 traces to two requirements and deviates from both; URS-TP201-027's row names a
    Test Step the draft does not hold."""
    return {
        "package": "TP-201-OQ-draft",
        "document": {"doc_id": DRAFT["doc"], "rev": DRAFT["rev"], "sha256": "ab" * 32},
        "test_steps": [
            _step("OQ-03", ["URS-TP201-003", "URS-TP201-004"], "maks. 65 dB(A)", _limit(max=65))
        ],
        "trace_rows": [
            {
                "requirement": "URS-TP201-027",
                "test_steps": ["OQ-27"],
                "citation": _cite(DRAFT, 8, "URS-TP201-027 OQ-27"),
            }
        ],
        "findings": [
            _deviates("OQ-03", "URS-TP201-003", 65),
            _deviates("OQ-03", "URS-TP201-004", 65),
            {
                "type": "requirement_not_tested",
                "layer": "rule",
                "test_step": None,
                "row": "URS-TP201-027",
                "requirement": "URS-TP201-027",
                "detail": (
                    "The traceability table lists URS-TP201-027 under OQ-27, but the draft"
                    " has no such Test Step: the requirement is not tested."
                ),
                "ac": None,
                "urs_limit": None,
                "citations": [_cite(DRAFT, 8, "URS-TP201-027 OQ-27")],
            },
        ],
    }


type DraftEdit = Callable[[dict[str, Any]], None]


def add_package_run(runs: Path, run_id: str = RUN_ID, edit: DraftEdit | None = None) -> str:
    """The fixture run as a Review Package run: ``edit`` changes its ``protocol_draft.json``."""
    if not (runs / run_id).exists():
        add_run(runs, run_id)
    draft = protocol_draft()
    if edit:
        edit(draft)
    ProtocolDraft.model_validate(draft)  # as a run writes it
    text = json.dumps(draft, ensure_ascii=False, indent=2)
    (runs / run_id / "protocol_draft.json").write_text(text, encoding="utf-8")
    return run_id


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    add_package_run(path)
    return path


@pytest.fixture
def client(runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases) -> TestClient:
    return TestClient(configured(runs, demo_issuer, fresh_database))


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=False))


def drafted(ps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in ps if p["kind"] == "draft"]


def view(client: TestClient, headers: dict[str, str], run_id: str = RUN_ID) -> Any:
    r = client.get(f"/runs/{run_id}/protocol-draft", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- Import -------------------------------------------------------------------------


def test_draft_findings_are_imported_after_the_equipment_proposals_which_keep_their_keys(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    add_run(runs, OTHER_RUN)  # the same run without its Protocol Draft
    assert import_run(client, decider)["proposals"] == 9
    import_run(client, decider, OTHER_RUN)
    got = proposals(client, decider)
    equipment = proposals(client, decider, OTHER_RUN)
    assert got[: len(equipment)] == equipment
    assert [(p["kind"], p["position"], p["requirement"]) for p in got[len(equipment) :]] == [
        ("draft", 0, None),
        ("draft", 1, None),
        ("draft", 2, None),
    ]
    # One Test Step traced to two requirements gives two Proposals.
    assert len({p["id"] for p in drafted(got)}) == 3


def _quote_length(draft: dict[str, Any]) -> None:
    """A re-run whose quotes differ only in length: values, detail and ids unchanged."""
    for f in draft["findings"]:
        for c in f["citations"]:
            c["quote"] = f"Tabel 2. {c['quote']} (lihat lampiran)"
    for s in draft["test_steps"]:
        s["acceptance"]["citation"]["quote"] += " diukur 1 m dari mesin"


def test_a_quote_length_change_keeps_identity_content_and_decision(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    first = drafted(proposals(client, decider))
    made = decide(client, decider, first[0], decision="accepted")
    add_package_run(runs, OTHER_RUN, _quote_length)
    import_run(client, decider, OTHER_RUN)
    second = drafted(proposals(client, decider, OTHER_RUN))
    assert [(p["id"], p["content_hash"]) for p in second] == [
        (p["id"], p["content_hash"]) for p in first
    ]
    assert second[0]["state"] == "decided" and second[0]["decisions"] == [made]


def test_a_changed_compared_value_asks_again(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def looser(draft: dict[str, Any]) -> None:
        f = draft["findings"][0]
        f["ac"]["max"] = 70
        f["detail"] = f["detail"].replace("65", "70")

    import_run(client, decider)
    first = drafted(proposals(client, decider))
    made = decide(client, decider, first[0], decision="rejected", reason="65 is the site limit")
    add_package_run(runs, OTHER_RUN, looser)
    import_run(client, decider, OTHER_RUN)
    second = drafted(proposals(client, decider, OTHER_RUN))
    assert [p["id"] for p in second] == [p["id"] for p in first]
    assert second[0]["content_hash"] != first[0]["content_hash"]
    assert (second[0]["state"], second[0]["previous"]) == ("changed", made)
    assert second[1]["content_hash"] == first[1]["content_hash"]


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d["document"].update(doc_id="OQ-TP201-B"),
        lambda d: d["findings"][0].update(test_step="OQ-04"),
        lambda d: d["findings"][0].update(requirement="URS-TP201-005"),
        lambda d: d["findings"][2].update(row="URS-TP201-028", requirement="URS-TP201-028"),
    ],
    ids=["document", "test step", "requirement", "row"],
)
def test_another_draft_revision_step_requirement_or_row_is_another_proposal(
    client: TestClient, runs: Path, decider: dict[str, str], edit: DraftEdit
) -> None:
    import_run(client, decider)
    first = drafted(proposals(client, decider))
    changed = copy.deepcopy(protocol_draft())
    edit(changed)
    moved = {
        i
        for i, (a, b) in enumerate(
            zip(protocol_draft()["findings"], changed["findings"], strict=True)
        )
        if a != b
    } or {0, 1, 2}  # a new document or revision moves every finding
    add_package_run(runs, OTHER_RUN, edit)
    import_run(client, decider, OTHER_RUN)
    second = drafted(proposals(client, decider, OTHER_RUN))
    for i, (a, b) in enumerate(zip(first, second, strict=True)):
        assert (a["id"] == b["id"]) is (i not in moved), i


# --- Decisions ----------------------------------------------------------------------


def test_a_draft_finding_is_accepted_without_a_reason_or_rejected_with_one(
    client: TestClient, decider: dict[str, str], fresh_database: Databases
) -> None:
    import_run(client, decider)
    deviates, twin, untested = drafted(proposals(client, decider))
    assert refused(client, decider, twin, decision="rejected") == 422
    assert refused(client, decider, twin, decision="rejected", reason="  ") == 422
    assert refused(client, decider, twin, decision="edited", coverage="gap", reason="r") == 422
    accepted = decide(client, decider, deviates, decision="accepted")
    rejected = decide(client, decider, untested, decision="rejected", reason="tested in PQ")
    assert (accepted["decision"], accepted["reason"]) == ("accepted", None)
    assert (rejected["decision"], rejected["reason"]) == ("rejected", "tested in PQ")
    # Accepting creates no task or revision: the Audit Trail holds the decisions only.
    with transaction(engine(fresh_database.app)) as s:
        trail = entries(s)
    assert [(e.action, e.record_type) for e in trail] == [
        ("run imported", "run"),
        ("review round opened", "review_round"),
        ("decision recorded", "proposal"),
        ("decision recorded", "proposal"),
    ]
    assert trail[-1].reason == "tested in PQ"
    assert trail[-1].record_id == str(untested["id"])


def test_draft_findings_are_counted_apart_from_the_equipment_check_findings(
    client: TestClient, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    before = client.get(f"/runs/{RUN_ID}/decision-counts", headers=decider).json()
    decide(client, decider, drafted(proposals(client, decider))[0], decision="accepted")
    after = client.get(f"/runs/{RUN_ID}/decision-counts", headers=decider).json()
    assert before["check"] == after["check"] and after["check"]["total"] == 2
    assert (after["draft"]["total"], after["draft"]["accepted"]) == (3, 1)


# --- The Protocol Draft route -------------------------------------------------------


def test_the_route_returns_rows_findings_and_decisions_to_both_roles(
    client: TestClient, decider: dict[str, str], reader: dict[str, str]
) -> None:
    before = view(client, reader)
    assert before["imported"] is False
    assert [f["proposal"] for f in before["findings"]] == [None, None, None]
    import_run(client, decider)
    ps = drafted(proposals(client, decider))
    made = decide(client, decider, ps[2], decision="rejected", reason="tested in PQ")
    # A reader sees the decisions but cannot make them.
    assert refused(client, reader, ps[0], decision="accepted") == 403
    got = view(client, reader)
    assert got == view(client, decider)
    assert got["imported"] is True
    assert (got["run_id"], got["package"], got["document"]["doc_id"]) == (
        RUN_ID,
        "TP-201-OQ-draft",
        "OQ-TP201",
    )
    assert [s["id"] for s in got["test_steps"]] == ["OQ-03"]
    assert [r["requirement"] for r in got["trace_rows"]] == ["URS-TP201-027"]
    assert [
        (f["finding"]["type"], f["finding"]["test_step"] or f["finding"]["row"])
        for f in got["findings"]
    ] == [
        ("ac_deviates_from_urs", "OQ-03"),
        ("ac_deviates_from_urs", "OQ-03"),
        ("requirement_not_tested", "URS-TP201-027"),
    ]
    assert [f["proposal"]["id"] for f in got["findings"]] == [p["id"] for p in ps]
    assert [f["proposal"]["state"] for f in got["findings"]] == [
        "undecided",
        "undecided",
        "decided",
    ]
    assert got["findings"][2]["proposal"]["decisions"] == [made]


def _with_unread_step_and_vendor_documents(draft: dict[str, Any]) -> None:
    unread = {
        "id": "OQ-02",
        "requirements": [],
        "acceptance": None,
        "not_read": "quote check",
        "traced": [],
        "compared": False,
        "not_compared": None,
    }
    draft["test_steps"].insert(0, unread)
    draft["vendor_documents"] = [
        {"doc": "DS-TP201", "rev": 0, "kind": "datasheet"},
        {"doc": "SAT-TP201", "rev": 0, "kind": "SAT"},
    ]


def test_the_route_lists_a_step_not_read_and_the_vendor_documents(
    client: TestClient, runs: Path, reader: dict[str, str]
) -> None:
    """Story 7: a Test Step whose reading was dropped is listed in draft order, not read,
    with the reason. Story 6: the vendor documents each Test Step shows a fact or "none" for."""
    add_package_run(runs, edit=_with_unread_step_and_vendor_documents)
    got = view(client, reader)
    assert [s["id"] for s in got["test_steps"]] == ["OQ-02", "OQ-03"]
    unread = got["test_steps"][0]
    assert (unread["not_read"], unread["acceptance"]) == ("quote check", None)
    assert [(d["doc"], d["kind"]) for d in got["vendor_documents"]] == [
        ("DS-TP201", "datasheet"),
        ("SAT-TP201", "SAT"),
    ]


def test_the_route_needs_a_token_and_a_review_package_run(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    assert client.get(f"/runs/{RUN_ID}/protocol-draft").status_code == 401
    add_run(runs, OTHER_RUN)
    assert client.get(f"/runs/{OTHER_RUN}/protocol-draft", headers=decider).status_code == 404
    assert client.get("/runs/nope/protocol-draft", headers=decider).status_code == 404
    (runs / OTHER_RUN / "protocol_draft.json").write_text("{}", encoding="utf-8")
    assert client.get(f"/runs/{OTHER_RUN}/protocol-draft", headers=decider).status_code == 422
    assert client.post(f"/runs/{OTHER_RUN}/import", headers=decider).status_code == 422
