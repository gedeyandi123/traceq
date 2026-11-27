"""The frozen copy of a Protocol started from the Protocol Draft: version 2, separation of
duties and stale approval, over HTTP with a real Postgres and the demo issuer (spec #375,
ticket S4a2; ADR 0012, amended 26 November 2026).

The fixture is that of ``tests/test_draft_to_protocol_api.py``: the draft's ``OQ-02`` is traced
to ``002`` only, ``OQ-26`` to ``026`` and ``030``, ``OQ-40`` to none, ``OQ-50`` was dropped by the
citation check. ``make_ready`` there is the checklist done; here ``OQ-26`` is first mapped to
``026`` by a person.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from test_assembled_protocol_api import read, rows
from test_draft_to_protocol_api import (
    R002,
    R026,
    R030,
    RUN_2,
    accept_step,
    decide_coverage,
    draft_run,
    make_ready,
    of_kind,
    put_mapping,
    revision_1,
    start_from_draft,
    step_proposal,
)
from test_execution_completion_api import _pass_value
from test_proposals_api import (
    RUN_ID,
    bearer,
    configured,
    decide,
    import_run,
    place,
    proposals,
    token,
)
from test_protocol_approval_api import both_roles, persona_token
from test_protocol_submission_api import canonical_sha256
from test_written_test_steps_api import STEP, edit, trail

from traceq.assembly.approval import authors
from traceq.assembly.submission import (
    Author,
    ProtocolCopy,
    ProtocolCopyV2,
    hash_of,
    parse_copy,
)
from traceq.execution.completion import ExecutionCopy
from traceq.execution.completion import hash_of as execution_hash_of


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


@pytest.fixture
def protocol(client: TestClient, decider: dict[str, str]) -> Any:
    """The run imported, every Coverage row decided, its Protocol started from the draft."""
    import_run(client, decider)
    decide_coverage(client, decider)
    return start_from_draft(client, decider)


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    """The persona who holds only the approving role."""
    return persona_token(demo_issuer, "dewi")


@pytest.fixture
def other(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Someone else who may decide and approve."""
    return both_roles(demo_issuer, "test-0099", "Eka Pratama")


def ready(client: TestClient, headers: dict[str, str], protocol: Any) -> None:
    """The checklist done, with ``OQ-26`` mapped to ``026`` by ``headers``."""
    put_mapping(client, headers, protocol, "OQ-26", R026)
    make_ready(client, headers, protocol)
    ps = proposals(client, headers)
    edit(client, headers, protocol, place(ps, "test_step", R030), STEP)
    assert [c for c in read(client, headers)["checklist"] if c["count"]] == []


def post_submit(client: TestClient, headers: dict[str, str], protocol: Any, rev: int | None) -> Any:
    body: dict[str, Any] = {"expected_draft_hash": read(client, headers)["draft_hash"]}
    if rev is not None:
        body["expected_latest_draft_rev"] = rev
    return client.post(f"/protocols/{protocol['id']}/submit", headers=headers, json=body)


def post_approve(
    client: TestClient, headers: dict[str, str], protocol: Any, view: Any, rev: int | None
) -> Any:
    body: dict[str, Any] = {
        "submission_event_id": view["submission"]["event_id"],
        "hash": view["submission"]["hash"],
    }
    if rev is not None:
        body["expected_latest_draft_rev"] = rev
    return client.post(f"/protocols/{protocol['id']}/approve", headers=headers, json=body)


def submitted(client: TestClient, headers: dict[str, str], protocol: Any) -> Any:
    r = post_submit(client, headers, protocol, 0)
    assert r.status_code == 200, r.text
    return r.json()


# --- The version 2 copy ---------------------------------------------------------------


def test_a_draft_protocol_is_frozen_as_a_version_2_copy_with_its_hash(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ready(client, decider, protocol)
    hash_read = read(client, decider)["draft_hash"]
    assert hash_read is not None
    view = submitted(client, decider, protocol)
    copy = view["submission"]["frozen_copy"]
    assert copy["schema_version"] == 2
    assert view["submission"]["hash"] == canonical_sha256(copy)
    assert copy["source"] == {
        "doc": "OQ-TP201",
        "rev": 0,
        "sha256": "0a" * 32,
        "run_id": RUN_ID,
    }
    # The Preparer's hash is the copy's, without the Preparer.
    without = {k: v for k, v in copy.items() if k != "preparer"}
    assert hash_read == canonical_sha256(without)
    assert view["submission"]["outcome"] is None


def test_each_row_records_its_source_stage_and_the_decisions_it_rests_on(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ready(client, decider, protocol)
    copy = submitted(client, decider, protocol)["submission"]["frozen_copy"]
    details = {d["requirement"]: d for d in copy["row_details"]}
    assert [r["requirement"] for r in copy["rows"]] == list(details)  # same order
    # 002: the draft's own step, accepted with its criterion; 026: written by hand after the
    # draft's step was rejected; 030: TraceQ's drafted step, edited.
    assert details[R002]["source"] == "draft"
    assert details[R026]["source"] == "traceq_written"
    assert details[R030]["source"] == "traceq_drafted"
    accepted = details[R002]["candidates"][0]
    assert accepted["step"] == "OQ-02"
    assert accepted["step_decision"]["decision"] == "accepted"
    assert accepted["step_decision"]["author"]["name"] == "Ayu Kartika Sari"
    assert details[R002]["criterion_decision"]["decision"] == "accepted"
    stages = {r["requirement"]: r["test_step"]["stage"] for r in copy["rows"]}
    assert stages == {R002: "OQ", R026: "OQ", R030: "OQ"}


def test_every_finding_decision_mapping_and_dropped_step_is_recorded_with_its_author(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ready(client, decider, protocol)
    copy = submitted(client, decider, protocol)["submission"]["frozen_copy"]
    [finding] = copy["findings"]
    assert (finding["type"], finding["requirement"], finding["test_step"]) == (
        "ac_deviates_from_urs",
        R002,
        "OQ-02",
    )
    [decision] = finding["decisions"]
    assert (decision["decision"], decision["reason"]) == ("rejected", "not a defect")
    assert decision["author"]["name"] == "Ayu Kartika Sari"
    steps = {s["step"]: s for s in copy["draft_steps"]}
    assert list(steps) == ["OQ-02", "OQ-26", "OQ-40", "OQ-50"]
    assert [
        (m["version"], m["requirement"], m["author"]["name"]) for m in steps["OQ-26"]["mappings"]
    ] == [(1, R026, "Ayu Kartika Sari")]
    assert steps["OQ-26"]["requirement"] == R026
    assert steps["OQ-50"]["not_read"] == "the quote is not on the page"
    assert steps["OQ-50"]["requirement"] is None
    assert steps["OQ-50"]["decisions"][0]["decision"] == "rejected"


def test_a_decision_on_a_finding_tied_to_no_row_is_recorded_too(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ready(client, decider, protocol)
    copy = submitted(client, decider, protocol)["submission"]["frozen_copy"]
    parsed = parse_copy(copy)
    assert isinstance(parsed, ProtocolCopyV2)
    # The Approver check reads findings of the copy, not only those of its rows.
    stray = {**copy["findings"][0], "requirement": "URS-NONE", "proposal_id": 9999}
    who = {"subject": "x-1", "issuer": _issuer(copy), "name": "Xe"}
    stray["decisions"] = [{**copy["findings"][0]["decisions"][0], "author": who}]
    extended = parse_copy({**copy, "findings": [*copy["findings"], stray]})
    assert Author(subject="x-1", issuer=_issuer(copy), name="Xe") in authors(extended)


def _issuer(copy: dict[str, Any]) -> str:
    return str(copy["preparer"]["issuer"])


# --- Version 1 copies are untouched ---------------------------------------------------

STORED_V1: dict[str, Any] = {
    "protocol_id": 7,
    "equipment": "TP-201",
    "run_id": "20260101T000000Z-aaaaaaa",
    "preparer": {"subject": "u-1", "issuer": "https://issuer.example", "name": "Ayu"},
    "rows": [],
    "urs": None,
}


def test_a_stored_version_1_copy_loads_through_the_version_1_model_and_keeps_its_hash() -> None:
    parsed = parse_copy(STORED_V1)
    assert type(parsed) is ProtocolCopy
    assert hash_of(parsed) == canonical_sha256(STORED_V1)
    assert hash_of(parsed) == _golden_v1_hash()
    # It is not a version 2 copy: no discriminator appears in what it dumps.
    assert "schema_version" not in parsed.model_dump(mode="json")


def _golden_v1_hash() -> str:
    """The hash of ``STORED_V1`` as the canonical JSON of its bytes gives it, written down
    here byte for byte so a change of the version 1 model shows."""
    import hashlib

    raw = (
        '{"equipment":"TP-201","preparer":{"issuer":"https://issuer.example","name":"Ayu",'
        '"subject":"u-1"},"protocol_id":7,"rows":[],"run_id":"20260101T000000Z-aaaaaaa",'
        '"urs":null}'
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_a_version_2_copy_is_told_by_its_discriminator_not_by_its_shape() -> None:
    assert type(parse_copy({**STORED_V1, "schema_version": 2, **_v2_extras()})) is ProtocolCopyV2


def _v2_extras() -> dict[str, Any]:
    return {
        "source": {"doc": "OQ-TP201", "rev": 0, "sha256": "ab" * 32, "run_id": "r"},
        "row_details": [],
        "draft_steps": [],
        "findings": [],
    }


# --- Separation of duties -------------------------------------------------------------


def test_someone_who_took_no_part_approves_and_the_latest_draft_revision_is_recorded(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    ready(client, decider, protocol)
    view = submitted(client, decider, protocol)
    r = post_approve(client, approver, protocol, view, 0)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["status"] == "approved"
    assert [e["latest_draft_rev"] for e in got["events"]] == [None, 0, 0]
    last = trail(fresh_database, "protocol")[-1]
    assert (last.action, last.new_value["latest_draft_rev"]) == ("protocol approved", 0)


def test_the_preparer_may_not_approve(
    client: TestClient, demo_issuer: DemoIssuer, protocol: Any
) -> None:
    both = both_roles(demo_issuer, "test-0098", "Fajar Nugroho")
    ready(client, both, protocol)
    view = submitted(client, both, protocol)
    r = post_approve(client, both, protocol, view, 0)
    assert r.status_code == 409
    assert "Preparer" in r.json()["detail"]


def test_someone_who_decided_a_finding_may_not_approve(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    import_finding = of_kind(proposals(client, decider), "draft")[0]
    decide(client, other, import_finding, decision="rejected", reason="not a defect")
    # Ayu does the rest; the finding stays rejected by Eka.
    put_mapping(client, decider, protocol, "OQ-26", R026)
    ps = proposals(client, decider)
    for s in ("OQ-26", "OQ-40", "OQ-50"):
        decide(client, decider, step_proposal(ps, "draft_step", s), decision="rejected", reason="r")
    _finish_without_finding(client, decider, protocol)
    view = submitted(client, decider, protocol)
    r = post_approve(client, other, protocol, view, 0)
    assert r.status_code == 409, r.text
    assert "decision on a finding" in r.json()["detail"]


def test_someone_who_mapped_a_draft_step_may_not_approve(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    assert put_mapping(client, other, protocol, "OQ-26", R026).status_code == 200
    make_ready(client, decider, protocol)
    ps = proposals(client, decider)
    edit(client, decider, protocol, place(ps, "test_step", R030), STEP)
    view = submitted(client, decider, protocol)
    r = post_approve(client, other, protocol, view, 0)
    assert r.status_code == 409, r.text
    assert "draft step mapping" in r.json()["detail"]


def _finish_without_finding(client: TestClient, headers: dict[str, str], protocol: Any) -> None:
    """What ``make_ready`` does, except for the finding and the draft steps already decided."""
    from test_assembled_protocol_api import read as read_
    from test_draft_to_protocol_api import set_stage
    from test_missed_numbers_api import N003, N004
    from test_missed_numbers_api import answer as dispose
    from test_written_test_steps_api import write

    ps = proposals(client, headers)
    decide(client, headers, step_proposal(ps, "draft_step", "OQ-02"), decision="accepted")
    decide(client, headers, step_proposal(ps, "draft_criterion", "OQ-02"), decision="accepted")
    decide(client, headers, place(ps, "test_step", R030), decision="accepted")
    write(client, headers, protocol, R026, STEP)
    for requirement in (R002, R026, R030):
        set_stage(client, headers, protocol, requirement, "OQ")
    dispose(client, headers, protocol, number=N003)
    dispose(client, headers, protocol, number=N004, kind="not_tested_here")
    ps = proposals(client, headers)
    edit(client, headers, protocol, place(ps, "test_step", R030), STEP)
    assert [c for c in read_(client, headers)["checklist"] if c["count"]] == []


# --- Stale approval -------------------------------------------------------------------


def test_submit_and_approve_refuse_a_stale_draft_revision_and_need_the_one_the_caller_read(
    client: TestClient,
    runs: Path,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
) -> None:
    ready(client, decider, protocol)
    assert read(client, decider)["latest_draft_rev"] == 0
    # A revision arrives after the Preparer opened the page.
    draft_run(runs, RUN_2, revision_1)
    import_run(client, decider, RUN_2)
    got = read(client, decider)
    assert (got["source"]["rev"], got["latest_draft_rev"]) == (0, 1)
    stale = post_submit(client, decider, protocol, 0)
    assert stale.status_code == 409
    assert "newer revision" in stale.json()["detail"]
    assert post_submit(client, decider, protocol, None).status_code == 422
    assert read(client, decider)["status"] == "draft"
    # Reloaded: the Preparer read revision 1 (the Protocol stays pinned to revision 0).
    view = post_submit(client, decider, protocol, 1).json()
    assert view["status"] == "submitted"
    assert [e["latest_draft_rev"] for e in view["events"]] == [None, 1]
    # Another revision arrives while the Approver reads.
    draft_run(runs, "20261126T090000Z-decade", _revision(2))
    import_run(client, decider, "20261126T090000Z-decade")
    assert post_approve(client, approver, protocol, view, 1).status_code == 409
    assert post_approve(client, approver, protocol, view, None).status_code == 422
    assert read(client, approver)["status"] == "submitted"
    done = post_approve(client, approver, protocol, view, 2)
    assert done.status_code == 200, done.text
    assert done.json()["events"][-1]["latest_draft_rev"] == 2


def _revision(rev: int) -> Any:
    def edit_draft(draft: dict[str, Any]) -> None:
        draft["document"].update(rev=rev, sha256=f"{rev + 10:02x}" * 32)
        draft["findings"] = []

    return edit_draft


def test_a_protocol_not_started_from_the_draft_ignores_the_expected_revision(
    client: TestClient, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    decide_coverage(client, decider)
    got = client.post(f"/runs/{RUN_ID}/protocol", headers=decider).json()
    assert got["latest_draft_rev"] is None
    assert got["source"] is None


# --- Nits of the previous slice -------------------------------------------------------


def test_an_acceptance_older_than_a_remap_does_not_block_accepting_another_step(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    put_mapping(client, decider, protocol, "OQ-26", R030)
    accept_step(client, decider, "OQ-26")
    put_mapping(client, decider, protocol, "OQ-26", R026)  # the old acceptance is stale now
    put_mapping(client, decider, protocol, "OQ-40", R026)
    ps = proposals(client, decider)
    decide(client, decider, step_proposal(ps, "draft_step", "OQ-40"), decision="accepted")


def test_mapping_a_step_to_the_requirement_it_already_stands_for_changes_nothing(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    first = put_mapping(client, decider, protocol, "OQ-26", R030).json()
    accept_step(client, decider, "OQ-26")
    again = put_mapping(client, decider, protocol, "OQ-26", R030)
    assert again.status_code == 200
    e = {x["step"]["id"]: x for x in again.json()["draft_steps"]}["OQ-26"]
    assert [m["version"] for m in e["mappings"]] == [1]
    assert e["mappings"] == {x["step"]["id"]: x for x in first["draft_steps"]}["OQ-26"]["mappings"]
    # The decision made on the mapping still holds: it was not asked again.
    assert any(c["accepted"] for c in rows(again.json())[R030]["candidates"])
    assert [a.action for a in trail(fresh_database, "protocol_draft_mapping")] == [
        "draft step mapped"
    ]


def test_the_authors_of_a_copy_include_the_candidates_decisions(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ready(client, decider, protocol)
    copy = parse_copy(submitted(client, decider, protocol)["submission"]["frozen_copy"])
    names = {a.name for a in authors(copy)}
    assert names == {"Ayu Kartika Sari"}


def _pass_all_rows(client: TestClient, headers: dict[str, str], ex: dict[str, Any]) -> None:
    """One passing attempt on every test step; a draft's range may have only one bound."""
    for row in ex["rows"]:
        if row["kind"] != "test_step":
            continue
        step = row["test_step"]
        acceptance = step["acceptance"]
        if acceptance["type"] == "range" and None in (acceptance["min"], acceptance["max"]):
            low, high = acceptance["min"], acceptance["max"]
            value: dict[str, Any] = {
                "type": "number",
                "value": low + 1 if high is None else high - 1,
            }
        else:
            value = _pass_value(acceptance)
        payload: dict[str, Any] = {"outcome_kind": "value", "value": value, "evidence": ["LOG-001"]}
        if step["instrument"]:
            payload["instruments"] = [
                {"identifier": step["instrument"], "calibration_due_date": "2099-12-31"}
            ]
        r = client.post(
            f"/executions/{ex['id']}/rows/{row['requirement']}/attempts",
            headers=headers,
            json=payload,
        )
        assert r.status_code == 201, r.text


# --- The whole path, the way the browser drives it --------------------------------------


def test_the_path_from_the_draft_to_a_started_execution(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
) -> None:
    """Start from the draft, map the step no requirement owned, decide, give the Stage, submit
    naming the revision read, approve as someone who took no part, and start the Execution
    from the approved copy (spec #375, ticket S4b)."""
    view = read(client, decider)
    assert view["source"]["rev"] == 0 and view["latest_draft_rev"] == 0
    assert any(not s["resolved"] for s in view["draft_steps"])
    ready(client, decider, protocol)
    view = read(client, decider)
    assert [s for s in view["draft_steps"] if not s["resolved"]] == []
    assert view["draft_hash"] is not None

    sub = submitted(client, decider, protocol)
    assert isinstance(parse_copy(sub["submission"]["frozen_copy"]), ProtocolCopyV2)
    approved = post_approve(client, approver, protocol, sub, view["latest_draft_rev"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    started = client.post(f"/protocols/{protocol['id']}/execution", headers=decider)
    assert started.status_code == 201, started.text
    assert {r["requirement"] for r in started.json()["rows"] if r["kind"] == "test_step"} >= {
        R002,
        R026,
        R030,
    }

    # Complete it, then read the frozen copy and check its hash (the run of a version 2
    # Protocol, end to end).
    ex = started.json()
    _pass_all_rows(client, decider, ex)
    done = client.post(f"/executions/{ex['id']}/complete", headers=decider)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "completed"
    frozen = body["frozen_copy"]
    assert frozen["protocol_id"] == protocol["id"]
    assert frozen["submission_hash"] == ex["submission_hash"]
    assert len(frozen["rows"]) == len(ex["rows"])
    assert execution_hash_of(ExecutionCopy.model_validate(frozen)) == body["copy_hash"]
    again = client.get(f"/runs/{RUN_ID}/execution", headers=decider).json()
    assert again["copy_hash"] == body["copy_hash"] and again["frozen_copy"] == frozen
