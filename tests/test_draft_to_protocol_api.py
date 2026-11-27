"""A Protocol started from the reviewed Protocol Draft: pinning, one source per row, draft Test
Steps that map to none or several requirements, and the submission rules, over HTTP with a real
Postgres and the demo issuer (spec #375, ticket S4a1; ADR 0012, amended 26 November 2026).

The fixture is the run of ``tests/test_protocol_submission_api.py`` (``002`` proposed
``partial`` with a TraceQ-drafted Test Step, ``026`` ``site_only``, ``030`` with no class and a
draft without an AC, ``003`` and ``004`` missed) with the ``protocol_draft.json`` of a Review
Package run: ``OQ-02`` traced to ``002`` only, ``OQ-26`` traced to ``026`` and ``030``, ``OQ-40``
traced to none, ``OQ-50`` whose reading the citation check dropped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_assembled_protocol_api import read, rows, withdraw
from test_missed_numbers_api import COMPLETENESS, N003, N004
from test_missed_numbers_api import answer as dispose
from test_proposals_api import (
    RUN_ID,
    add_run,
    bearer,
    configured,
    decide,
    import_run,
    place,
    proposals,
    token,
)
from test_test_step_proposals import add_drafted_run
from test_written_test_steps_api import STEP, edit, write

from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.runs.schemas import ProtocolDraft

R002, R026, R030 = "URS-TP201-002", "URS-TP201-026", "URS-TP201-030"
RUN_2 = "20261125T090000Z-decade"
DRAFT = {"doc": "OQ-TP201", "rev": 0}
URS = {"doc": "URS-TP201", "rev": 0}


def _cite(doc: dict[str, Any], page: int, quote: str) -> dict[str, Any]:
    return {**doc, "page": page, "quote": quote}


def _limit(**bounds: Any) -> dict[str, Any]:
    return {"type": "range", "unit": "kN", **bounds}


def _traced(requirement: str) -> dict[str, Any]:
    return {
        "requirement": requirement,
        "urs_limit": _limit(min=10),
        "citation": _cite(URS, 1, "Gaya tekan minimal 10 kN."),
        "not_parsed": None,
        "compared": True,
        "deviates": False,
        "not_compared": None,
        "comparators": [],
    }


def _step(
    step: str, requirements: list[str], printed: str, ac: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "id": step,
        "requirements": requirements,
        "description": f"Uji {step}",
        "method": f"Metode {step}: ukur dan catat.",
        "instrument": "Load cell LC-1",
        "acceptance": {
            "printed": printed,
            "value": ac,
            "citation": _cite(DRAFT, 2, f"{step} {printed}"),
        },
        "traced": [_traced(r) for r in requirements],
        "compared": True,
        "not_compared": None,
    }


def _finding(step: str, requirement: str, ac_min: float) -> dict[str, Any]:
    return {
        "type": "ac_deviates_from_urs",
        "layer": "rule",
        "test_step": step,
        "row": None,
        "requirement": requirement,
        "detail": f"{step} accepts at least {ac_min:g} kN, which {requirement} rejects.",
        "ac": _limit(min=ac_min),
        "urs_limit": _limit(min=10),
        "citations": [_cite(DRAFT, 2, f"{step} minimal {ac_min:g} kN"), _cite(URS, 1, "min 10 kN")],
    }


def protocol_draft(rev: int = 0) -> dict[str, Any]:
    return {
        "package": "TP-201-OQ-draft",
        "document": {"doc_id": DRAFT["doc"], "rev": rev, "sha256": f"{rev + 10:02x}" * 32},
        "test_steps": [
            _step("OQ-02", [R002], "minimal 5 kN", _limit(min=5)),
            _step("OQ-26", [R026, R030], "minimal 10 kN", _limit(min=10)),
            _step(
                "OQ-40", [], "Ra < 0,8 µm", {**_limit(max=0.8), "unit": "µm", "max_exclusive": True}
            ),
            {
                "id": "OQ-50",
                "requirements": [],
                "acceptance": None,
                "not_read": "the quote is not on the page",
                "traced": [],
                "compared": False,
                "not_compared": None,
            },
        ],
        "trace_rows": [],
        "findings": [_finding("OQ-02", R002, 5)],
    }


type Edit = Callable[[dict[str, Any]], None]


def draft_run(runs: Path, run_id: str = RUN_ID, edit_draft: Edit | None = None) -> str:
    """The fixture run as a Review Package run with its TraceQ drafts and missed numbers."""
    if not (runs / run_id).exists():
        add_run(runs, run_id)
    add_drafted_run(runs, run_id)
    (runs / run_id / "completeness.json").write_text(json.dumps(COMPLETENESS), encoding="utf-8")
    draft = protocol_draft()
    if edit_draft:
        edit_draft(draft)
    ProtocolDraft.model_validate(draft)  # as a run writes it
    (runs / run_id / "protocol_draft.json").write_text(
        json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_id


def revision_1(draft: dict[str, Any]) -> None:
    draft["document"].update(rev=1, sha256="cd" * 32)
    draft["findings"] = []  # the finding is resolved


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    draft_run(path)
    return path


@pytest.fixture
def client(runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases) -> TestClient:
    return TestClient(configured(runs, demo_issuer, fresh_database))


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=True))


def start_from_draft(client: TestClient, headers: dict[str, str], run_id: str = RUN_ID) -> Any:
    r = client.post(f"/runs/{run_id}/protocol", headers=headers, json={"from_draft": True})
    assert r.status_code == 201, r.text
    return r.json()


def decide_coverage(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    ps = proposals(client, headers)
    decide(client, headers, place(ps, "coverage", R002), decision="accepted")
    decide(client, headers, place(ps, "coverage", R026), decision="accepted")
    decide(
        client, headers, place(ps, "coverage", R030), decision="edited", coverage="gap", reason="r"
    )
    return ps


@pytest.fixture
def protocol(client: TestClient, decider: dict[str, str]) -> Any:
    """The run imported, every Coverage row decided, its Protocol started from the draft."""
    import_run(client, decider)
    decide_coverage(client, decider)
    return start_from_draft(client, decider)


def of_kind(ps: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [p for p in ps if p["kind"] == kind]


def step_proposal(ps: list[dict[str, Any]], kind: str, step: str) -> Any:
    """The draft Test Step (or criterion) Proposal of ``step``: found by its place among the
    draft's Test Steps (the dropped one has no criterion)."""
    order = ["OQ-02", "OQ-26", "OQ-40", "OQ-50"]
    if kind == "draft_criterion":
        order = order[:3]
    return of_kind(ps, kind)[order.index(step)]


def listing(view: Any) -> dict[str, Any]:
    return {e["step"]["id"]: e for e in view["draft_steps"]}


def checks(view: Any) -> dict[str, tuple[int, list[str], list[str]]]:
    return {c["check"]: (c["count"], c["requirements"], c["steps"]) for c in view["checklist"]}


def put_mapping(
    client: TestClient, headers: dict[str, str], protocol: Any, step: str, requirement: str
) -> Any:
    return client.put(
        f"/protocols/{protocol['id']}/draft-steps/{step}/mapping",
        headers=headers,
        json={"requirement": requirement},
    )


def set_stage(
    client: TestClient, headers: dict[str, str], protocol: Any, requirement: str, stage: str
) -> None:
    r = client.put(
        f"/protocols/{protocol['id']}/rows/{requirement}/attributes",
        headers=headers,
        json={"stage": stage, "witness_required": False},
    )
    assert r.status_code == 200, r.text


def reason(
    client: TestClient, headers: dict[str, str], protocol: Any, finding: dict[str, Any], why: str
) -> Any:
    return client.post(
        f"/protocols/{protocol['id']}/findings/{finding['id']}/reason",
        headers=headers,
        json={"reason": why},
    )


# --- Import ---------------------------------------------------------------------------


def test_each_draft_test_step_and_its_criterion_is_a_proposal_with_the_requirement_it_maps_to(
    client: TestClient, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    ps = proposals(client, decider)
    steps, criteria = of_kind(ps, "draft_step"), of_kind(ps, "draft_criterion")
    assert [p["requirement"] for p in steps] == [R002, None, None, None]
    # The dropped step has no criterion to decide.
    assert [p["requirement"] for p in criteria] == [R002, None, None]
    assert all(p["state"] == "undecided" for p in steps + criteria)


def test_a_run_without_a_draft_cannot_start_a_protocol_from_one(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    add_run(runs, RUN_2)
    import_run(client, decider, RUN_2)
    r = client.post(f"/runs/{RUN_2}/protocol", headers=decider, json={"from_draft": True})
    assert r.status_code == 409
    assert "read no Protocol Draft" in r.json()["detail"]


# --- Pinning --------------------------------------------------------------------------


def test_a_protocol_is_pinned_to_its_run_and_the_draft_document_revision_and_hash(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    assert protocol["source"] == {"doc": "OQ-TP201", "rev": 0, "sha256": "0a" * 32}
    assert protocol["run_id"] == RUN_ID
    assert read(client, decider)["source"] == protocol["source"]
    with transaction(engine(fresh_database.app)) as s:
        trail = entries(s)
    assert trail[-1].new_value["draft"] == protocol["source"]  # type: ignore[index]


def test_a_protocol_started_the_old_way_has_no_source_and_no_draft_checks(
    client: TestClient, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    decide_coverage(client, decider)
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert r.status_code == 201, r.text
    got = r.json()
    assert (got["source"], got["draft_steps"]) == (None, None)
    assert [c["check"] for c in got["checklist"]] == [
        "coverage_undecided",
        "draft_undecided",
        "no_test_step",
        "acceptance_not_shaped",
        "missed_undecided",
    ]
    assert {r["step_source"] for r in got["rows"]} == {None}


def test_a_later_revision_never_clears_a_warning_on_a_protocol_pinned_to_revision_0(
    client: TestClient, runs: Path, decider: dict[str, str], protocol: Any
) -> None:
    before = read(client, decider)
    finding = before["rows"][0]["findings"][0]
    assert finding["finding"]["type"] == "ac_deviates_from_urs"
    draft_run(runs, RUN_2, revision_1)  # revision 1 resolves the finding
    import_run(client, decider, RUN_2)
    after = read(client, decider)
    # Nothing re-syncs: only the latest revision the Equipment has read moves.
    assert (before["latest_draft_rev"], after["latest_draft_rev"]) == (0, 1)
    assert {**after, "latest_draft_rev": 0} == before
    assert after["source"]["rev"] == 0
    assert after["rows"][0]["findings"][0]["finding"] == finding["finding"]
    assert "finding_undecided" in {b for r in after["rows"] for b in r["blockers"]}
    # The remedy: withdraw it and start a new Protocol from the latest revision.
    withdraw(client, decider, protocol, "revision 1 arrived")
    second = start_from_draft(client, decider, RUN_2)
    assert second["source"]["rev"] == 1
    assert all(r["findings"] == [] for r in second["rows"])


# --- Draft steps that map to none or several ------------------------------------------


def test_a_step_that_maps_to_none_or_several_or_was_dropped_is_listed_and_unusable(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    got = read(client, decider)
    steps = listing(got)
    assert list(steps) == ["OQ-02", "OQ-26", "OQ-40", "OQ-50"]
    assert {k: (v["requirement"], v["resolved"]) for k, v in steps.items()} == {
        "OQ-02": (R002, True),
        "OQ-26": (None, False),
        "OQ-40": (None, False),
        "OQ-50": (None, False),
    }
    assert steps["OQ-50"]["step"]["not_read"] == "the quote is not on the page"
    assert checks(got)["draft_step_unresolved"] == (3, [], ["OQ-26", "OQ-40", "OQ-50"])
    # Neither 026 nor 030 has a draft step to start from.
    assert rows(got)[R026]["candidates"] == [] and rows(got)[R030]["candidates"] == []


def test_a_human_maps_one_requirement_and_it_is_recorded_with_its_author(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    r = put_mapping(client, decider, protocol, "OQ-26", R030)
    assert r.status_code == 200, r.text
    got = r.json()
    e = listing(got)["OQ-26"]
    assert (e["requirement"], e["resolved"]) == (R030, True)
    assert [(m["version"], m["requirement"], m["name"]) for m in e["mappings"]] == [
        (1, R030, "Ayu Kartika Sari")
    ]
    row = rows(got)[R030]
    assert [c["step"]["id"] for c in row["candidates"]] == ["OQ-26"]
    assert row["candidates"][0]["mapping"]["requirement"] == R030
    assert checks(got)["draft_step_unresolved"][2] == ["OQ-40", "OQ-50"]
    # Mapped again, the latest counts and both versions stay.
    again = put_mapping(client, decider, protocol, "OQ-26", R026).json()
    assert [m["requirement"] for m in listing(again)["OQ-26"]["mappings"]] == [R030, R026]
    assert rows(again)[R030]["candidates"] == []
    assert [c["step"]["id"] for c in rows(again)[R026]["candidates"]] == ["OQ-26"]
    with transaction(engine(fresh_database.app)) as s:
        actions = [e.action for e in entries(s)]
    assert actions.count("draft step mapped") == 2


def test_a_step_the_table_maps_to_exactly_one_requirement_is_not_remapped(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    r = put_mapping(client, decider, protocol, "OQ-02", R030)
    assert r.status_code == 409
    assert "nothing to map" in r.json()["detail"]
    assert put_mapping(client, decider, protocol, "OQ-99", R030).status_code == 404
    assert put_mapping(client, decider, protocol, "OQ-26", "URS-TP201-999").status_code == 404


def test_a_mapping_is_the_deciders_and_does_not_carry_over_to_a_later_protocol(
    client: TestClient, runs: Path, decider: dict[str, str], protocol: Any, demo_issuer: DemoIssuer
) -> None:
    reader = bearer(token(demo_issuer, decider=False))
    assert put_mapping(client, reader, protocol, "OQ-26", R030).status_code == 403
    put_mapping(client, decider, protocol, "OQ-26", R030)
    withdraw(client, decider, protocol, "again")
    second = start_from_draft(client, decider)
    assert listing(second)["OQ-26"]["mappings"] == []
    assert listing(second)["OQ-26"]["requirement"] is None


def test_rejecting_an_unusable_step_resolves_it_without_a_row(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    decide(
        client,
        decider,
        step_proposal(ps, "draft_step", "OQ-40"),
        decision="rejected",
        reason="a PQ step",
    )
    got = read(client, decider)
    assert listing(got)["OQ-40"]["resolved"] is True
    assert checks(got)["draft_step_unresolved"][2] == ["OQ-26", "OQ-50"]


def test_a_step_that_could_not_be_read_is_edited_never_accepted(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    put_mapping(client, decider, protocol, "OQ-50", R030)
    ps = proposals(client, decider)
    url = f"/runs/{RUN_ID}/proposals/{step_proposal(ps, 'draft_step', 'OQ-50')['id']}/decisions"
    r = client.post(url, headers=decider, json={"decision": "accepted"})
    assert r.status_code == 409
    assert "could not be read" in r.json()["detail"]


# --- One source per row ---------------------------------------------------------------


def test_a_requirement_the_draft_covers_takes_its_test_step_from_the_draft_not_from_traceq(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    got = read(client, decider)
    covered, other = rows(got)[R002], rows(got)[R030]
    assert [c["step"]["id"] for c in covered["candidates"]] == ["OQ-02"]
    assert covered["drafts"] == []  # TraceQ's own draft for 002 is not offered
    assert [d["draft"]["id"] for d in other["drafts"]] == ["TS-URS-TP201-030"]
    ps = proposals(client, decider)
    own = place(ps, "test_step", R002)
    r = client.post(
        f"/runs/{RUN_ID}/proposals/{own['id']}/decisions",
        headers=decider,
        json={"decision": "accepted"},
    )
    assert r.status_code == 409
    assert "Protocol Draft covers" in r.json()["detail"]


def test_an_accepted_draft_step_is_the_rows_test_step_with_its_source_recorded(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    decide(client, decider, step_proposal(ps, "draft_step", "OQ-02"), decision="accepted")
    mid = rows(read(client, decider))[R002]
    assert "draft_undecided" in mid["blockers"]  # its criterion is still to be decided
    decide(client, decider, step_proposal(ps, "draft_criterion", "OQ-02"), decision="accepted")
    row = rows(read(client, decider))[R002]
    assert "draft_undecided" not in row["blockers"] and "no_test_step" not in row["blockers"]
    assert row["step_source"] == "draft"
    assert row["test_step"]["source"] == "draft"
    assert row["test_step"]["acceptance"] == {
        "type": "range",
        "min": 5.0,
        "max": None,
        "unit": "kN",
    }
    assert row["test_step"]["description"] == "Uji OQ-02"
    assert row["candidates"][0]["accepted"] is True


def test_a_requirement_the_draft_does_not_cover_keeps_traceqs_source(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "test_step", R030), decision="accepted")
    write(client, decider, protocol, R026, STEP)
    got = rows(read(client, decider))
    assert got[R030]["step_source"] == "traceq_drafted"
    assert got[R026]["step_source"] == "traceq_written"


def test_accepting_a_draft_step_and_writing_one_by_hand_cannot_both_succeed(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    decide(client, decider, step_proposal(ps, "draft_step", "OQ-02"), decision="accepted")
    r = client.post(
        f"/protocols/{protocol['id']}/test-steps/{R002}", headers=decider, json={"test_step": STEP}
    )
    assert r.status_code == 409
    assert "accepted" in r.json()["detail"]


def test_writing_by_hand_then_accepting_a_draft_step_for_the_same_requirement_is_refused(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    write(client, decider, protocol, R002, STEP)
    ps = proposals(client, decider)
    url = f"/runs/{RUN_ID}/proposals/{step_proposal(ps, 'draft_step', 'OQ-02')['id']}/decisions"
    r = client.post(url, headers=decider, json={"decision": "accepted"})
    assert r.status_code == 409
    assert "written Test Step" in r.json()["detail"]


def test_a_concurrent_accept_and_write_on_one_requirement_cannot_both_succeed(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    accept = f"/runs/{RUN_ID}/proposals/{step_proposal(ps, 'draft_step', 'OQ-02')['id']}/decisions"
    write_url = f"/protocols/{protocol['id']}/test-steps/{R002}"

    def accepting() -> int:
        return client.post(accept, headers=decider, json={"decision": "accepted"}).status_code

    def writing() -> int:
        return client.post(write_url, headers=decider, json={"test_step": STEP}).status_code

    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(accepting), pool.submit(writing)
        got = sorted([first.result(), second.result()])
    assert got == [201, 409]


def test_editing_a_draft_step_writes_a_test_step_whose_source_is_the_draft(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    own = step_proposal(ps, "draft_step", "OQ-02")
    edit(client, decider, protocol, own, STEP)
    row = rows(read(client, decider))[R002]
    assert (row["step_source"], row["test_step"]["origin"]) == ("draft", "written")
    assert row["changed"] is True
    assert "draft_undecided" not in row["blockers"]


def test_a_withdrawn_protocols_edit_never_decides_the_step_in_a_new_protocol(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    own = step_proposal(ps, "draft_step", "OQ-02")
    edit(client, decider, protocol, own, STEP)
    withdraw(client, decider, protocol, "wrong Protocol")
    second = start_from_draft(client, decider)
    again = proposals(client, decider)
    # The decision exists on the same content (shared), yet it decides nothing here.
    assert step_proposal(again, "draft_step", "OQ-02")["state"] == "decided"
    row = rows(second)[R002]
    assert "draft_undecided" in row["blockers"] and "no_test_step" in row["blockers"]
    assert row["test_step"] is None
    # Editing it again in this Protocol decides it.
    edit(client, decider, second, own, STEP)
    after = rows(read(client, decider))[R002]
    assert "draft_undecided" not in after["blockers"] and after["step_source"] == "draft"


# --- Exact shapes ---------------------------------------------------------------------


def test_an_exclusive_bound_is_a_shape_of_its_own_never_an_inclusive_range(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    put_mapping(client, decider, protocol, "OQ-40", R030)
    ps = proposals(client, decider)
    decide(client, decider, step_proposal(ps, "draft_step", "OQ-40"), decision="accepted")
    decide(client, decider, step_proposal(ps, "draft_criterion", "OQ-40"), decision="accepted")
    row = rows(read(client, decider))[R030]
    assert row["test_step"]["acceptance"] == {
        "type": "exclusive_range",
        "min": None,
        "max": 0.8,
        "min_exclusive": False,
        "max_exclusive": True,
        "unit": "µm",
    }
    assert "acceptance_not_shaped" not in row["blockers"]


# --- Submission rules -----------------------------------------------------------------


def test_an_undecided_finding_blocks_and_an_accepted_one_on_an_unchanged_row_needs_a_reason(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    got = read(client, decider)
    assert checks(got)["finding_undecided"] == (1, [R002], [])
    finding = of_kind(proposals(client, decider), "draft")[0]
    decide(client, decider, finding, decision="accepted")
    got = read(client, decider)
    assert checks(got)["finding_undecided"][0] == 0
    assert checks(got)["finding_reason_missing"] == (1, [R002], [])
    assert reason(client, decider, protocol, finding, "  ").status_code == 422
    r = reason(client, decider, protocol, finding, "fixed in revision 1, accepted until then")
    assert r.status_code == 201, r.text
    done = r.json()
    assert checks(done)["finding_reason_missing"][0] == 0
    only = done["rows"][0]["findings"][0]["reasons"]
    assert [(x["version"], x["reason"], x["name"]) for x in only] == [
        (1, "fixed in revision 1, accepted until then", "Ayu Kartika Sari")
    ]


def test_a_rejected_finding_needs_no_reason_and_none_can_be_given(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    finding = of_kind(proposals(client, decider), "draft")[0]
    decide(client, decider, finding, decision="rejected", reason="the draft is right")
    assert checks(read(client, decider))["finding_reason_missing"][0] == 0
    r = reason(client, decider, protocol, finding, "because")
    assert r.status_code == 409


def test_an_accepted_finding_on_a_row_whose_test_step_was_edited_needs_no_reason(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    decide(client, decider, of_kind(ps, "draft")[0], decision="accepted")
    assert checks(read(client, decider))["finding_reason_missing"][0] == 1
    edit(client, decider, protocol, step_proposal(ps, "draft_step", "OQ-02"), STEP)
    got = read(client, decider)
    assert checks(got)["finding_reason_missing"][0] == 0
    assert rows(got)[R002]["changed"] is True


R002_AS_DRAFTED: dict[str, Any] = {
    "description": "Uji OQ-02",
    "method": "Metode OQ-02: ukur dan catat.",
    "instrument": "Load cell LC-1",
    "acceptance": {"type": "range", "min": 5.0, "unit": "kN"},
}


def test_saving_the_test_step_unchanged_does_not_clear_the_need_for_a_reason(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    decide(client, decider, of_kind(proposals(client, decider), "draft")[0], decision="accepted")
    assert checks(read(client, decider))["finding_reason_missing"][0] == 1
    # Saved exactly as the draft has it (also with blanks around the text and an empty
    # instrument read as none): nothing changed, so the reason is still needed.
    padded = {**R002_AS_DRAFTED, "description": " Uji OQ-02 ", "instrument": " Load cell LC-1 "}
    for same in (R002_AS_DRAFTED, padded):
        write(client, decider, protocol, R002, same)
        got = read(client, decider)
        assert rows(got)[R002]["step_source"] == "traceq_written"
        assert checks(got)["finding_reason_missing"][0] == 1
    # Any difference in the Test Step or its Acceptance Criterion counts as a change ...
    for different in (
        {**R002_AS_DRAFTED, "method": "Metode lain."},
        {**R002_AS_DRAFTED, "acceptance": {"type": "range", "min": 6.0, "unit": "kN"}},
        {**R002_AS_DRAFTED, "instrument": None},
    ):
        write(client, decider, protocol, R002, different)
        assert checks(read(client, decider))["finding_reason_missing"][0] == 0
        # ... and saving it back as the draft has it asks for the reason again.
        write(client, decider, protocol, R002, R002_AS_DRAFTED)
        assert checks(read(client, decider))["finding_reason_missing"][0] == 1


def test_a_test_step_row_needs_its_stage_before_submission(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    write(client, decider, protocol, R026, STEP)
    assert checks(read(client, decider))["stage_missing"] == (1, [R026], [])
    set_stage(client, decider, protocol, R026, "OQ")
    assert checks(read(client, decider))["stage_missing"][0] == 0


def test_the_old_way_does_not_ask_for_a_stage(client: TestClient, decider: dict[str, str]) -> None:
    import_run(client, decider)
    decide_coverage(client, decider)
    got = client.post(f"/runs/{RUN_ID}/protocol", headers=decider).json()
    write(client, decider, got, R026, STEP)
    assert "stage_missing" not in {c["check"] for c in read(client, decider)["checklist"]}


def make_ready(client: TestClient, headers: dict[str, str], protocol: Any) -> None:
    """Everything the checklist asks for is done."""
    ps = proposals(client, headers)
    decide(client, headers, step_proposal(ps, "draft_step", "OQ-02"), decision="accepted")
    decide(client, headers, step_proposal(ps, "draft_criterion", "OQ-02"), decision="accepted")
    decide(client, headers, of_kind(ps, "draft")[0], decision="rejected", reason="not a defect")
    for s in ("OQ-26", "OQ-40", "OQ-50"):
        decide(
            client,
            headers,
            step_proposal(ps, "draft_step", s),
            decision="rejected",
            reason="not for this Protocol",
        )
    decide(client, headers, place(ps, "test_step", R030), decision="accepted")
    write(client, headers, protocol, R026, STEP)
    for requirement in (R002, R026, R030):
        set_stage(client, headers, protocol, requirement, "OQ")
    dispose(client, headers, protocol, number=N003)
    dispose(client, headers, protocol, number=N004, kind="not_tested_here")


def test_every_check_clear_submits_a_version_2_copy(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    got = read(client, decider)
    assert any(c["count"] for c in got["checklist"])
    make_ready(client, decider, protocol)
    # TraceQ's own draft for 030 has no criterion: edit it so every row is shaped.
    ps = proposals(client, decider)
    edit(client, decider, protocol, place(ps, "test_step", R030), STEP)
    got = read(client, decider)
    assert [c for c in got["checklist"] if c["count"]] == [], got["checklist"]
    assert got["draft_hash"] is not None
    r = client.post(
        f"/protocols/{protocol['id']}/submit",
        headers=decider,
        json={"expected_draft_hash": got["draft_hash"], "expected_latest_draft_rev": 0},
    )
    assert r.status_code == 200, r.text
    assert r.json()["submission"]["frozen_copy"]["schema_version"] == 2


def test_submit_names_the_draft_checks_that_block(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    r = client.post(
        f"/protocols/{protocol['id']}/submit",
        headers=decider,
        json={"expected_draft_hash": "0" * 64, "expected_latest_draft_rev": 0},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "finding_undecided (1)" in detail and "draft_step_unresolved (3)" in detail


# --- Concurrency and the database -------------------------------------------------------


def test_the_new_tables_refuse_update_and_delete(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    put_mapping(client, decider, protocol, "OQ-26", R030)
    for sql in (
        "UPDATE protocol_draft_mappings SET requirement = 'x'",
        "DELETE FROM protocol_draft_mappings",
        "UPDATE assembled_protocols SET draft_rev = 9",
    ):
        with (
            pytest.raises(DBAPIError),
            transaction(engine(fresh_database.owner)) as s,
        ):
            s.execute(text(sql))


def test_the_pin_is_all_or_nothing(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    insert = (
        "INSERT INTO assembled_protocols (equipment, run_id, draft_doc)"
        " VALUES ('TP-201', :run, 'OQ-TP201')"
    )
    with pytest.raises(DBAPIError), transaction(engine(fresh_database.owner)) as s:
        s.execute(text(insert), {"run": RUN_ID})


# --- A decision binds to the requirement mapping ----------------------------------------


def accept_step(client: TestClient, headers: dict[str, str], step: str, **again: str) -> None:
    ps = proposals(client, headers)
    decide(client, headers, step_proposal(ps, "draft_step", step), decision="accepted", **again)
    decide(
        client, headers, step_proposal(ps, "draft_criterion", step), decision="accepted", **again
    )


def candidate(view: Any, requirement: str, step: str) -> Any:
    return next((c for c in rows(view)[requirement]["candidates"] if c["step"]["id"] == step), None)


def test_a_remap_after_accepting_makes_the_step_undecided_again(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    put_mapping(client, decider, protocol, "OQ-26", R030)
    accept_step(client, decider, "OQ-26")
    assert candidate(read(client, decider), R030, "OQ-26")["accepted"] is True
    got = put_mapping(client, decider, protocol, "OQ-26", R026).json()
    moved = candidate(got, R026, "OQ-26")
    assert (moved["ready"], moved["accepted"]) == (False, False)
    assert "draft_undecided" in rows(got)[R026]["blockers"]
    # Deciding it again on the new mapping counts; remapping back does not revive the
    # older decision.
    accept_step(client, decider, "OQ-26", reason="decided on the new mapping")
    assert candidate(read(client, decider), R026, "OQ-26")["accepted"] is True
    put_mapping(client, decider, protocol, "OQ-26", R030)
    back = candidate(read(client, decider), R030, "OQ-26")
    assert (back["ready"], back["accepted"]) == (False, False)


def test_a_step_mapped_differently_in_a_later_protocol_arrives_undecided(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    put_mapping(client, decider, protocol, "OQ-26", R030)
    accept_step(client, decider, "OQ-26")
    withdraw(client, decider, protocol, "again")
    second = start_from_draft(client, decider)
    got = put_mapping(client, decider, second, "OQ-26", R026).json()
    assert candidate(got, R026, "OQ-26")["accepted"] is False
    assert candidate(got, R026, "OQ-26")["ready"] is False


def test_a_reason_written_for_an_earlier_acceptance_does_not_count(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    finding = of_kind(proposals(client, decider), "draft")[0]
    decide(client, decider, finding, decision="accepted")
    reason(client, decider, protocol, finding, "accepted for now")
    assert checks(read(client, decider))["finding_reason_missing"][0] == 0
    decide(client, decider, finding, decision="rejected", reason="changed my mind")
    decide(client, decider, finding, decision="accepted", reason="after all")
    assert checks(read(client, decider))["finding_reason_missing"][0] == 1
    reason(client, decider, protocol, finding, "accepted again, with a reason")
    assert checks(read(client, decider))["finding_reason_missing"][0] == 0
