"""Editing drafted Test Steps and writing Test Steps in a Protocol in Draft status, with every
version kept, over HTTP with a real Postgres and the demo issuer (spec #247, "Written Test
Steps", "Acceptance Criterion shapes", "Concurrency"; ADR 0012; ticket #250).

The fixture run is the one of ``tests/test_assembled_protocol_api.py``: three requirements
(``002`` proposed ``partial`` with two FAT steps, ``026`` ``site_only``, ``030`` with no class)
and drafts for ``002`` (a range AC copied from a citation) and ``030`` (no AC).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_assembled_protocol_api import read, rows, start, withdraw
from test_proposals_api import (
    RUN_ID,
    bearer,
    configured,
    counts,
    decide,
    import_run,
    place,
    proposals,
    token,
)
from test_test_step_proposals import add_drafted_run

from traceq.audit import entries
from traceq.db import engine, transaction

R002, R026, R030 = "URS-TP201-002", "URS-TP201-026", "URS-TP201-030"

STEP: dict[str, Any] = {
    "description": "Verifies the turret speed on site.",
    "method": "Set the turret to 20 rpm and to 70 rpm and read the tachometer.",
    "instrument": "TACH-07 Digital tachometer",
    "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
}


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    add_drafted_run(path)
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


@pytest.fixture
def protocol(client: TestClient, decider: dict[str, str]) -> Any:
    """An imported run with every Coverage row decided: ``002`` and ``026`` accepted as
    proposed, ``030`` edited to ``gap``, and its Protocol started."""
    import_run(client, decider)
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "coverage", R002), decision="accepted")
    decide(client, decider, place(ps, "coverage", R026), decision="accepted")
    decide(
        client, decider, place(ps, "coverage", R030), decision="edited", coverage="gap", reason="r"
    )
    return start(client, decider)


def write_url(protocol: Any, requirement: str) -> str:
    return f"/protocols/{protocol['id']}/test-steps/{requirement}"


def write(
    client: TestClient, headers: dict[str, str], protocol: Any, requirement: str, step: Any
) -> Any:
    r = client.post(write_url(protocol, requirement), headers=headers, json={"test_step": step})
    assert r.status_code == 201, r.text
    return r.json()


def edit_url(protocol: Any, proposal: dict[str, Any]) -> str:
    return f"/protocols/{protocol['id']}/drafts/{proposal['id']}/edit"


def edit(
    client: TestClient,
    headers: dict[str, str],
    protocol: Any,
    proposal: dict[str, Any],
    step: Any,
    reason: str = "the range is read at the turret, not the motor",
) -> Any:
    r = client.post(
        edit_url(protocol, proposal), headers=headers, json={"reason": reason, "test_step": step}
    )
    assert r.status_code == 201, r.text
    return r.json()


def draft_of(client: TestClient, headers: dict[str, str], requirement: str) -> dict[str, Any]:
    return place(proposals(client, headers), "test_step", requirement)


def trail(dbs: Databases, record_type: str) -> list[Any]:
    with transaction(engine(dbs.app)) as s:
        return [e for e in entries(s) if e.record_type == record_type]


# --- Writing --------------------------------------------------------------------------


def test_writing_needs_a_token_the_deciding_role_and_a_known_protocol_and_requirement(
    client: TestClient, decider: dict[str, str], reader: dict[str, str], protocol: Any
) -> None:
    url = write_url(protocol, R026)
    body = {"test_step": STEP}
    assert client.post(url, json=body).status_code == 401
    r = client.post(url, headers=reader, json=body)
    assert r.status_code == 403
    assert "deciding role" in r.json()["detail"]
    assert (
        client.post(f"/protocols/999999/test-steps/{R026}", headers=decider, json=body).status_code
        == 404
    )
    assert (
        client.post(write_url(protocol, "URS-TP201-999"), headers=decider, json=body).status_code
        == 404
    )
    assert rows(read(client, decider))[R026]["written"] == []


def test_a_written_test_step_is_the_rows_test_step_with_no_reason_for_change(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    assert rows(read(client, decider))[R026]["blockers"] == ["no_test_step"]
    got = rows(write(client, decider, protocol, R026, STEP))[R026]
    assert (got["kind"], got["blockers"]) == ("test_step", [])
    assert got["test_step"] == {
        "origin": "written",
        "proposal_id": None,
        "version": 1,
        "description": STEP["description"],
        "method": STEP["method"],
        "instrument": STEP["instrument"],
        "acceptance": STEP["acceptance"],
        "acceptance_flag": None,
        "stage": None,
        "witness_required": False,
    }
    [v] = got["written"]
    assert (v["version"], v["removed"], v["test_step"], v["name"]) == (
        1,
        False,
        STEP,
        "Ayu Kartika Sari",
    )
    assert (v["from_proposal_id"], v["decision_id"]) == (None, None)
    [entry] = trail(fresh_database, "written_test_step")
    assert (entry.action, entry.record_id, entry.reason, entry.old_value) == (
        "test step written",
        f"{protocol['id']}/{R026}",
        None,
        None,
    )
    assert entry.new_value == {
        "written_id": v["id"],
        "protocol_id": protocol["id"],
        "requirement": R026,
        "version": 1,
        "removed": False,
        "test_step": STEP,
        "from_proposal_id": None,
        "decision_id": None,
    }


def test_every_version_is_kept_with_who_when_and_its_old_and_new_content(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    write(client, decider, protocol, R026, STEP)
    second = {**STEP, "instrument": None, "acceptance": {"type": "present", "value": None}}
    row = rows(write(client, decider, protocol, R026, second))[R026]
    assert [(v["version"], v["test_step"]) for v in row["written"]] == [(1, STEP), (2, second)]
    assert row["written"][0]["at"] <= row["written"][1]["at"]
    assert (row["test_step"]["version"], row["test_step"]["acceptance"]) == (
        2,
        {"type": "present", "value": None},
    )
    entries_ = trail(fresh_database, "written_test_step")
    assert [e.action for e in entries_] == ["test step written", "test step written"]
    assert entries_[1].old_value is not None
    assert entries_[1].old_value["test_step"] == STEP
    assert entries_[1].new_value["version"] == 2


def test_a_removal_takes_the_written_test_step_back_and_a_later_version_writes_it_again(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    r = client.post(write_url(protocol, R026), headers=decider, json={"test_step": None})
    assert r.status_code == 409
    assert "no written Test Step to remove" in r.json()["detail"]
    write(client, decider, protocol, R026, STEP)
    row = rows(write(client, decider, protocol, R026, None))[R026]
    assert (row["kind"], row["test_step"], row["blockers"]) == ("test_step", None, ["no_test_step"])
    assert [(v["version"], v["removed"], v["test_step"]) for v in row["written"]] == [
        (1, False, STEP),
        (2, True, None),
    ]
    row = rows(write(client, decider, protocol, R026, STEP))[R026]
    assert (row["test_step"]["version"], row["blockers"]) == (3, [])
    assert [e.action for e in trail(fresh_database, "written_test_step")] == [
        "test step written",
        "test step removed",
        "test step written",
    ]


def test_an_empty_body_is_not_a_removal(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    write(client, decider, protocol, R026, STEP)
    assert client.post(write_url(protocol, R026), headers=decider, json={}).status_code == 422
    assert rows(read(client, decider))[R026]["test_step"]["version"] == 1


def test_a_vendor_reference_row_becomes_a_test_step_row_when_written_and_back_on_removal(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    decide(
        client,
        decider,
        place(proposals(client, decider), "coverage", R002),
        decision="edited",
        coverage="covered_by_vendor",
        reason="both FAT steps pass at the limits",
    )
    assert rows(read(client, decider))[R002]["kind"] == "vendor_reference"
    row = rows(write(client, decider, protocol, R002, STEP))[R002]
    assert (row["kind"], row["evidence"], row["test_step"]["origin"]) == (
        "test_step",
        [],
        "written",
    )
    row = rows(write(client, decider, protocol, R002, None))[R002]
    assert (row["kind"], row["test_step"], row["blockers"]) == ("vendor_reference", None, [])
    assert len(row["evidence"]) == 2


# --- Acceptance Criterion shapes ------------------------------------------------------


@pytest.mark.parametrize(
    "acceptance",
    [
        {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        {"type": "range", "max": 70.0, "unit": "rpm"},
        {"type": "range", "min": 20.0, "unit": "rpm"},
        {"type": "number", "value": 12.5, "unit": "kN"},
        {"type": "one_of", "allowed": ["open", "closed"]},
        {"type": "present"},
    ],
    ids=["range", "upper bound", "lower bound", "number", "one of", "present"],
)
def test_the_four_acceptance_criterion_shapes_are_accepted(
    client: TestClient, decider: dict[str, str], protocol: Any, acceptance: dict[str, Any]
) -> None:
    got = rows(write(client, decider, protocol, R026, {**STEP, "acceptance": acceptance}))[R026]
    assert {k: v for k, v in got["test_step"]["acceptance"].items() if v is not None} == {
        **{k: v for k, v in acceptance.items() if v is not None},
        "type": acceptance["type"],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"acceptance": {"type": "text", "value": "works as specified"}},
        {"acceptance": {"type": "present", "value": True}},
        {"acceptance": {"type": "range", "unit": "rpm"}},
        {"acceptance": {"type": "range", "min": 70.0, "max": 20.0, "unit": "rpm"}},
        {"acceptance": {"type": "number", "value": 1.0}},
        {"acceptance": {"type": "number", "value": 1.0, "unit": "  "}},
        {"acceptance": {"type": "range", "min": 20.0, "unit": ""}},
        {"acceptance": {"type": "one_of", "allowed": []}},
        {"acceptance": None},
        {"description": "  "},
        {"method": ""},
    ],
    ids=[
        "text",
        "present with a value",
        "range without bounds",
        "range upside down",
        "number without unit",
        "number with a blank unit",
        "range with a blank unit",
        "one of nothing",
        "no AC",
        "blank description",
        "blank method",
    ],
)
def test_anything_else_is_refused_when_writing(
    client: TestClient, decider: dict[str, str], protocol: Any, change: dict[str, Any]
) -> None:
    r = client.post(
        write_url(protocol, R026), headers=decider, json={"test_step": {**STEP, **change}}
    )
    assert r.status_code == 422, r.text
    assert rows(read(client, decider))[R026]["written"] == []


# --- One Test Step per row ------------------------------------------------------------


def test_accepting_a_draft_is_refused_while_a_written_test_step_exists(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    write(client, decider, protocol, R002, STEP)
    draft = draft_of(client, decider, R002)
    r = client.post(
        f"/runs/{RUN_ID}/proposals/{draft['id']}/decisions",
        headers=decider,
        json={"decision": "accepted"},
    )
    assert r.status_code == 409
    assert "written Test Step" in r.json()["detail"]
    # Rejecting it is not refused.
    decide(client, decider, draft, decision="rejected", reason="the written one replaces it")
    write(client, decider, protocol, R002, None)
    decide(client, decider, draft, decision="accepted", reason="the draft is right after all")
    row = rows(read(client, decider))[R002]
    assert (row["test_step"]["origin"], row["blockers"]) == ("accepted_draft", [])


def test_writing_is_refused_while_a_draft_of_the_requirement_is_accepted(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    draft = draft_of(client, decider, R002)
    decide(client, decider, draft, decision="accepted")
    r = client.post(write_url(protocol, R002), headers=decider, json={"test_step": STEP})
    assert r.status_code == 409
    assert "accepted" in r.json()["detail"]
    decide(client, decider, draft, decision="rejected", reason="a written one is clearer")
    row = rows(write(client, decider, protocol, R002, STEP))[R002]
    assert row["test_step"]["origin"] == "written"


def test_writing_and_accepting_at_once_give_one_test_step(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    draft = draft_of(client, decider, R002)
    calls = [
        lambda: client.post(write_url(protocol, R002), headers=decider, json={"test_step": STEP}),
        lambda: client.post(
            f"/runs/{RUN_ID}/proposals/{draft['id']}/decisions",
            headers=decider,
            json={"decision": "accepted"},
        ),
    ]
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(c.status_code for c in pool.map(lambda f: f(), calls))
    assert codes == [201, 409]
    row = rows(read(client, decider))[R002]
    accepted = row["drafts"][0]["proposal"]["state"] == "decided"
    assert accepted != (row["written"] != [])


# --- Editing a drafted Test Step ------------------------------------------------------


def test_editing_a_draft_records_the_edited_decision_and_version_1_in_one_request(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    draft = draft_of(client, decider, R030)
    step = {**STEP, "instrument": None, "acceptance": {"type": "number", "value": 5.0, "unit": "s"}}
    row = rows(edit(client, decider, protocol, draft, step))[R030]
    assert (row["kind"], row["blockers"]) == ("test_step", [])
    assert row["test_step"]["origin"] == "written"
    assert row["test_step"]["proposal_id"] == draft["id"]
    assert row["test_step"]["acceptance"] == {"type": "number", "value": 5.0, "unit": "s"}
    [decision] = row["drafts"][0]["proposal"]["decisions"]
    assert (decision["decision"], decision["coverage"], decision["reason"]) == (
        "edited",
        None,
        "the range is read at the turret, not the motor",
    )
    [v] = row["written"]
    assert (v["version"], v["from_proposal_id"], v["decision_id"], v["test_step"]) == (
        1,
        draft["id"],
        decision["id"],
        step,
    )
    with transaction(engine(fresh_database.app)) as s:
        actions = [(e.action, e.record_type) for e in entries(s)][-2:]
    assert actions == [
        ("decision recorded", "proposal"),
        ("test step written", "written_test_step"),
    ]
    assert counts(client, decider)["test_step"]["edited"] == 1


def test_editing_needs_a_reason_for_change_the_role_and_a_drafted_test_step_of_the_run(
    client: TestClient, decider: dict[str, str], reader: dict[str, str], protocol: Any
) -> None:
    draft = draft_of(client, decider, R030)
    url = edit_url(protocol, draft)
    assert client.post(url, json={"reason": "r", "test_step": STEP}).status_code == 401
    assert (
        client.post(url, headers=reader, json={"reason": "r", "test_step": STEP}).status_code == 403
    )
    r = client.post(url, headers=decider, json={"reason": "  ", "test_step": STEP})
    assert r.status_code == 422
    assert "Reason for Change" in r.json()["detail"]
    coverage = place(proposals(client, decider), "coverage", R030)
    assert (
        client.post(
            edit_url(protocol, coverage), headers=decider, json={"reason": "r", "test_step": STEP}
        ).status_code
        == 404
    )
    text_ac = {**STEP, "acceptance": {"type": "text", "value": "fine"}}
    assert (
        client.post(url, headers=decider, json={"reason": "r", "test_step": text_ac}).status_code
        == 422
    )
    row = rows(read(client, decider))[R030]
    assert (row["written"], row["drafts"][0]["proposal"]["state"]) == ([], "undecided")


def test_editing_replaces_an_accepted_decision_but_not_a_written_test_step(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    draft = draft_of(client, decider, R002)
    decide(client, decider, draft, decision="accepted")
    row = rows(edit(client, decider, protocol, draft, STEP))[R002]
    assert [d["decision"] for d in row["drafts"][0]["proposal"]["decisions"]] == [
        "edited",
        "accepted",
    ]
    r = client.post(
        edit_url(protocol, draft), headers=decider, json={"reason": "r", "test_step": STEP}
    )
    assert r.status_code == 409
    assert "change it instead" in r.json()["detail"]
    # The written Test Step is changed as any other, without a Reason for Change.
    row = rows(write(client, decider, protocol, R002, {**STEP, "instrument": None}))[R002]
    assert [v["version"] for v in row["written"]] == [1, 2]


def test_editing_is_refused_without_a_protocol_in_draft_status(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    draft = draft_of(client, decider, R030)
    withdraw(client, decider, protocol, "a newer run")
    r = client.post(
        edit_url(protocol, draft), headers=decider, json={"reason": "r", "test_step": STEP}
    )
    assert r.status_code == 409
    assert "Draft status" in r.json()["detail"]
    assert draft_of(client, decider, R030)["state"] == "undecided"


@pytest.mark.parametrize("event", ["submitted", "approved", "withdrawn"])
def test_writes_are_refused_unless_the_protocol_is_in_draft_status(
    client: TestClient,
    decider: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
    event: str,
) -> None:
    """The event is added directly (a placeholder copy for ``submitted``): submitting itself is
    tested in ``tests/test_protocol_submission_api.py``, approving in
    ``tests/test_protocol_approval_api.py``."""
    with engine(fresh_database.app).begin() as c:
        c.execute(
            text(
                "INSERT INTO protocol_events (protocol_id, event, reason, subject, issuer, name,"
                " frozen_copy, copy_hash) VALUES (:p, :e, 'r', 's', 'i', 'n',"
                " CASE WHEN :e = 'submitted' THEN '{}'::jsonb END,"
                " CASE WHEN :e = 'submitted' THEN repeat('0', 64) END)"
            ),
            {"p": protocol["id"], "e": event},
        )
    r = client.post(write_url(protocol, R026), headers=decider, json={"test_step": STEP})
    assert r.status_code == 409
    assert event in r.json()["detail"]
    draft = draft_of(client, decider, R030)
    r = client.post(
        edit_url(protocol, draft), headers=decider, json={"reason": "r", "test_step": STEP}
    )
    assert r.status_code == 409


# --- Prefill --------------------------------------------------------------------------


def test_the_form_starts_from_the_draft_its_ac_only_in_one_of_the_four_shapes(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    got = rows(read(client, decider))
    assert got[R002]["prefill"] == {
        "origin": "draft",
        "description": "Verifies URS-TP201-002 on site.",
        "method": "Set the turret to 20 rpm and to 70 rpm and read the tachometer.",
        "instrument": "TACH-07 Digital tachometer",
        "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
    }
    assert (got[R030]["prefill"]["origin"], got[R030]["prefill"]["acceptance"]) == ("draft", None)
    assert got[R026]["prefill"] is None
    got = rows(write(client, decider, protocol, R026, STEP))
    assert got[R026]["prefill"] == {"origin": "written", **STEP}


def test_after_a_withdrawal_the_form_starts_from_the_withdrawn_protocols_latest_version(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    write(client, decider, protocol, R026, STEP)
    later = {**STEP, "instrument": None}
    write(client, decider, protocol, R026, later)
    edit(client, decider, protocol, draft_of(client, decider, R030), STEP)
    write(client, decider, protocol, R030, None)
    withdraw(client, decider, protocol, "a newer run reads the URS revision 1")
    second = start(client, decider)
    got = rows(second)
    # Nothing carries over: the rows have no Test Step until someone saves one.
    assert (got[R026]["written"], got[R026]["test_step"]) == ([], None)
    assert got[R026]["prefill"] == {"origin": "withdrawn", **later}
    # Removed there: the form falls back to the draft. Its draft stays decided edited.
    assert got[R030]["prefill"]["origin"] == "draft"
    assert got[R030]["drafts"][0]["proposal"]["decisions"][0]["decision"] == "edited"
    assert got[R030]["blockers"] == ["no_test_step"]
    row = rows(write(client, decider, second, R026, later))[R026]
    assert [v["version"] for v in row["written"]] == [1]


# --- Append-only ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE written_test_steps SET method = 'rewritten'",
        "DELETE FROM written_test_steps",
        "TRUNCATE written_test_steps",
    ],
)
def test_written_test_steps_are_append_only(
    client: TestClient,
    decider: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
    statement: str,
) -> None:
    write(client, decider, protocol, R026, STEP)
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        engine(fresh_database.app).begin() as c,
    ):
        c.execute(text(statement))
    with pytest.raises(DBAPIError, match="append-only"), engine(fresh_database.owner).begin() as c:
        c.execute(text(statement))
    assert rows(read(client, decider))[R026]["test_step"]["method"] == STEP["method"]


def test_accepting_a_second_draft_on_the_same_requirement_is_refused(
    tmp_path: Path, demo_issuer: DemoIssuer, fresh_database: Databases
) -> None:
    from test_test_step_proposals import _step

    path = tmp_path / "runs_two_drafts"
    path.mkdir()
    add_drafted_run(
        path,
        edit=lambda d: d["test_steps"].append(
            _step(R002, "partial", id="TS-URS-TP201-002-ALT", description="Alternative draft.")
        ),
    )
    c = TestClient(configured(path, demo_issuer, fresh_database))
    h = bearer(token(demo_issuer, decider=True))
    import_run(c, h)
    ps = [p for p in proposals(c, h) if p["kind"] == "test_step" and p["requirement"] == R002]
    assert len(ps) == 2
    decide(c, h, ps[0], decision="accepted")
    r2 = c.post(
        f"/runs/{RUN_ID}/proposals/{ps[1]['id']}/decisions",
        headers=h,
        json={"decision": "accepted"},
    )
    assert r2.status_code == 409
    assert "another drafted Test Step" in r2.json()["detail"]
