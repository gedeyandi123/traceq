"""Drafted Test Steps as Proposals of kind ``test_step``, imported from ``drafts.json``, and
their decisions, over HTTP with a real Postgres and the demo issuer (spec #247, "Drafted Test
Steps become Proposals"; ticket #248).

Each test copies the fixture run of ``tests/test_proposals_api.py`` and adds a ``drafts.json``
as a run writes it (``traceq.runs.drafts``), changed where the test needs.
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
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_proposals_api import (
    OTHER_RUN,
    RUN_ID,
    add_run,
    bearer,
    configured,
    counts,
    decide,
    import_run,
    place,
    proposals,
    refused,
    token,
)

from traceq.audit import entries
from traceq.db import engine, transaction

URS = {"doc": "URS-TP201", "rev": 0}


def _step(requirement: str, coverage: str | None, **change: Any) -> dict[str, Any]:
    step: dict[str, Any] = {
        "id": f"TS-{requirement}",
        "requirement": requirement,
        "requirement_text": f"The text of {requirement}.",
        "coverage": coverage,
        "saved_by_reuse": False,
        "description": f"Verifies {requirement} on site.",
        "method": "Set the turret to 20 rpm and to 70 rpm and read the tachometer.",
        "instrument": "TACH-07 Digital tachometer",
        "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        "acceptance_citation": {**URS, "page": 1, "quote": "dapat diatur 20-70 rpm"},
        "acceptance_flag": None,
        "layer": "ai",
        "source": dict(URS),
        "model": "claude-haiku-5-5",
        "prompt": "bbbbbbbbbbbb",
        "created": "2026-11-13T09:00:00+00:00",
        "reviewer_action": "pending",
    }
    return {**step, **change}


def drafted() -> dict[str, Any]:
    """Two drafts: one with an AC copied from a verified citation, one to be set by a human."""
    return {
        "vendor_reuse": True,
        "test_steps": [
            _step("URS-TP201-002", "partial"),
            _step(
                "URS-TP201-030",
                None,
                acceptance=None,
                acceptance_citation=None,
                acceptance_flag="to be set by a human: no acceptance criterion in the sources",
                instrument=None,
            ),
        ],
    }


type DraftsEdit = Callable[[dict[str, Any]], None]


def add_drafted_run(runs: Path, run_id: str = RUN_ID, edit: DraftsEdit | None = None) -> str:
    """The fixture run with a ``drafts.json``; ``edit`` changes it in place."""
    if not (runs / run_id).exists():
        add_run(runs, run_id)
    data = drafted()
    if edit:
        edit(data)
    (runs / run_id / "drafts.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_id


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    add_run(path)
    return path


@pytest.fixture
def client(runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases) -> TestClient:
    return TestClient(configured(runs, demo_issuer, fresh_database))


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def drafted_run(runs: Path) -> str:
    return add_drafted_run(runs)


def _zero() -> dict[str, int]:
    names = ("total", "undecided", "accepted", "edited", "rejected", "changed")
    return dict.fromkeys((*names, "decided_not_proposed"), 0)


# --- Import -------------------------------------------------------------------------


def test_import_adds_one_test_step_proposal_per_draft_after_the_other_kinds(
    client: TestClient, decider: dict[str, str], drafted_run: str
) -> None:
    assert import_run(client, decider)["proposals"] == 8
    got = proposals(client, decider)
    assert [(p["kind"], p["requirement"], p["position"], p["state"]) for p in got] == [
        ("coverage", "URS-TP201-002", None, "undecided"),
        ("coverage", "URS-TP201-026", None, "undecided"),
        ("coverage", "URS-TP201-030", None, "undecided"),
        ("check", None, 0, "undecided"),
        ("check", None, 1, "undecided"),
        ("ai", None, 0, "undecided"),
        ("test_step", "URS-TP201-002", None, "undecided"),
        ("test_step", "URS-TP201-030", None, "undecided"),
    ]
    assert len({p["id"] for p in got}) == 8


def test_a_run_without_drafts_json_adds_no_test_step_proposal(
    client: TestClient, decider: dict[str, str]
) -> None:
    assert import_run(client, decider)["proposals"] == 6
    assert all(p["kind"] != "test_step" for p in proposals(client, decider))


def test_drafts_json_leaves_the_other_kinds_unchanged(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    add_drafted_run(runs, OTHER_RUN)
    import_run(client, decider, OTHER_RUN)
    plain = {(p["kind"], p["requirement"] or p["position"]): p for p in proposals(client, decider)}
    with_drafts = {
        (p["kind"], p["requirement"] or p["position"]): p
        for p in proposals(client, decider, OTHER_RUN)
        if p["kind"] != "test_step"
    }
    assert with_drafts == plain


@pytest.mark.parametrize(
    ("change", "same"),
    [
        (lambda s: s.update(model="another-model", prompt="cccc", created="2026-11-20"), True),
        (lambda s: s.update(requirement_text="A paraphrase of the requirement."), True),
        (lambda s: s["acceptance_citation"].update(quote="diatur 20-70 rpm"), True),
        (lambda s: s.update(description="Checks the turret speed range on site."), False),
        (lambda s: s.update(method="Read the tachometer at 20 and 70 rpm."), False),
        (lambda s: s.update(instrument="TACH-08"), False),
        (lambda s: s["acceptance"].update(max=60.0), False),
        (lambda s: s["acceptance_citation"].update(page=2), False),
        (lambda s: s.update(acceptance_flag="to be set by a human: not verified"), False),
        (lambda s: s["source"].update(rev=1), False),
    ],
    ids=[
        "provenance",
        "requirement text",
        "AC quote",
        "description",
        "method",
        "instrument",
        "AC value",
        "AC page",
        "AC flag",
        "URS revision",
    ],
)
def test_what_a_decision_rests_on_changes_the_content_hash_not_the_identity(
    client: TestClient,
    runs: Path,
    decider: dict[str, str],
    drafted_run: str,
    change: Callable[[dict[str, Any]], None],
    same: bool,
) -> None:
    def edit(d: dict[str, Any]) -> None:
        change(d["test_steps"][0])

    import_run(client, decider)
    add_drafted_run(runs, OTHER_RUN, edit)
    import_run(client, decider, OTHER_RUN)
    first = place(proposals(client, decider), "test_step", "URS-TP201-002")
    second = place(proposals(client, decider, OTHER_RUN), "test_step", "URS-TP201-002")
    assert second["id"] == first["id"]
    assert (second["content_hash"] == first["content_hash"]) is same


def test_the_same_requirement_drafted_for_another_equipment_is_another_proposal(
    client: TestClient, runs: Path, decider: dict[str, str], drafted_run: str
) -> None:
    def other(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        meta["corpus"]["equipment"] = "TP-999"

    import_run(client, decider)
    add_run(runs, OTHER_RUN, other)
    add_drafted_run(runs, OTHER_RUN)
    import_run(client, decider, OTHER_RUN)
    first = place(proposals(client, decider), "test_step", "URS-TP201-002")
    second = place(proposals(client, decider, OTHER_RUN), "test_step", "URS-TP201-002")
    assert first["id"] != second["id"]


def test_a_broken_drafts_json_imports_nothing(
    client: TestClient, runs: Path, decider: dict[str, str], fresh_database: Databases
) -> None:
    add_drafted_run(runs, OTHER_RUN, lambda d: d["test_steps"][0].update(acceptance="20-70 rpm"))
    assert client.post(f"/runs/{OTHER_RUN}/import", headers=decider).status_code == 422
    assert client.get(f"/runs/{OTHER_RUN}/proposals", headers=decider).status_code == 404
    with transaction(engine(fresh_database.app)) as s:
        assert entries(s) == []


# --- Decisions ----------------------------------------------------------------------


def test_a_drafted_test_step_is_accepted_or_rejected_and_never_edited_here(
    client: TestClient, decider: dict[str, str], drafted_run: str
) -> None:
    import_run(client, decider)
    ps = proposals(client, decider)
    with_ac = place(ps, "test_step", "URS-TP201-002")
    no_ac = place(ps, "test_step", "URS-TP201-030")
    # Editing a draft is a later route (with its written Test Step), never this one.
    assert refused(client, decider, with_ac, decision="edited", reason="r") == 422
    assert refused(client, decider, with_ac, decision="edited", coverage="gap", reason="r") == 422
    assert refused(client, decider, with_ac, decision="accepted", coverage="gap") == 422
    # A Reason for Change as slice 1: needed to reject and to replace.
    assert refused(client, decider, no_ac, decision="rejected") == 422
    accepted = decide(client, decider, with_ac, decision="accepted")
    assert (accepted["decision"], accepted["coverage"]) == ("accepted", None)
    assert refused(client, decider, with_ac, decision="rejected") == 422
    decide(client, decider, with_ac, decision="rejected", reason="the range is the wrong one")
    decide(client, decider, no_ac, decision="rejected", reason="no AC: write it instead")
    now = proposals(client, decider)
    assert place(now, "test_step", "URS-TP201-002")["decisions"][0]["decision"] == "rejected"
    assert place(now, "test_step", "URS-TP201-030")["state"] == "decided"


def test_a_coverage_row_edited_without_a_class_is_still_refused(
    client: TestClient, decider: dict[str, str], drafted_run: str
) -> None:
    import_run(client, decider)
    row = place(proposals(client, decider), "coverage", "URS-TP201-026")
    assert refused(client, decider, row, decision="edited", reason="no class") == 422


def test_the_database_takes_a_class_only_on_edited(
    client: TestClient, decider: dict[str, str], drafted_run: str, fresh_database: Databases
) -> None:
    """``edited`` without a class is now possible in the table (a drafted Test Step edited by
    the later edit route); a class on any other verdict is still refused there."""
    import_run(client, decider)
    p = place(proposals(client, decider), "test_step", "URS-TP201-002")
    insert = text(
        "INSERT INTO proposal_decisions"
        " (proposal_id, run_id, content_hash, decision, coverage, reason, subject, issuer, name)"
        " VALUES (:p, :run, :h, :d, :c, 'r', 's', 'i', 'n')"
    )
    values = {"p": p["id"], "run": RUN_ID, "h": p["content_hash"]}
    with transaction(engine(fresh_database.app)) as s:
        s.execute(insert, {**values, "d": "edited", "c": None})
    with pytest.raises(IntegrityError), transaction(engine(fresh_database.app)) as s:
        s.execute(insert, {**values, "d": "accepted", "c": "gap"})


def test_counts_include_drafted_test_steps(
    client: TestClient, decider: dict[str, str], drafted_run: str
) -> None:
    import_run(client, decider)
    assert counts(client, decider)["test_step"] == {**_zero(), "total": 2, "undecided": 2}
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "test_step", "URS-TP201-002"), decision="accepted")
    decide(
        client,
        decider,
        place(ps, "test_step", "URS-TP201-030"),
        decision="rejected",
        reason="no AC",
    )
    got = counts(client, decider)
    assert got["test_step"] == {**_zero(), "total": 2, "accepted": 1, "rejected": 1}
    assert got["coverage"] == {**_zero(), "total": 3, "undecided": 3}


def test_a_run_without_drafts_counts_no_test_step(
    client: TestClient, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    assert counts(client, decider)["test_step"] == _zero()


def test_a_drafted_test_step_decided_on_one_run_is_decided_on_a_run_with_the_same_content(
    client: TestClient, runs: Path, decider: dict[str, str], drafted_run: str
) -> None:
    def reworded(d: dict[str, Any]) -> None:
        d["test_steps"] = copy.deepcopy(d["test_steps"])
        d["test_steps"][1]["description"] = "Checks the data recorder is fitted."

    import_run(client, decider)
    ps = proposals(client, decider)
    made = decide(client, decider, place(ps, "test_step", "URS-TP201-002"), decision="accepted")
    decide(client, decider, place(ps, "test_step", "URS-TP201-030"), decision="accepted")
    add_drafted_run(runs, OTHER_RUN, reworded)
    import_run(client, decider, OTHER_RUN)
    other = proposals(client, decider, OTHER_RUN)
    assert place(other, "test_step", "URS-TP201-002")["decisions"] == [made]
    assert place(other, "test_step", "URS-TP201-030")["state"] == "changed"
