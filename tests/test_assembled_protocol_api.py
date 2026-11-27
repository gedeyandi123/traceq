"""Starting, reading and withdrawing the Protocol assembled in TraceQ, over HTTP with a real
Postgres and the demo issuer (spec #247, "The Protocol and its rows"; ADR 0012; ticket #249).

Each test copies the fixture run of ``tests/test_proposals_api.py`` with the ``drafts.json`` of
``tests/test_test_step_proposals.py``: three requirements (``002`` proposed ``partial`` with two
FAT steps, ``026`` ``site_only``, ``030`` with no class) and drafts for ``002`` and ``030``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_proposals_api import (
    OTHER_RUN,
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

from traceq.audit import entries
from traceq.db import engine, transaction


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
def imported(client: TestClient, decider: dict[str, str]) -> str:
    import_run(client, decider)
    return RUN_ID


def start(client: TestClient, headers: dict[str, str], run_id: str = RUN_ID) -> Any:
    r = client.post(f"/runs/{run_id}/protocol", headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def read(client: TestClient, headers: dict[str, str], run_id: str = RUN_ID) -> Any:
    r = client.get(f"/runs/{run_id}/protocol", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def withdraw(client: TestClient, headers: dict[str, str], protocol: Any, reason: str) -> Any:
    r = client.post(
        f"/protocols/{protocol['id']}/withdraw", headers=headers, json={"reason": reason}
    )
    assert r.status_code == 200, r.text
    return r.json()


def rows(view: Any) -> dict[str, Any]:
    return {r["requirement"]: r for r in view["rows"]}


# --- Start ----------------------------------------------------------------------------


def test_starting_needs_a_token_and_the_deciding_role(
    client: TestClient, reader: dict[str, str], imported: str
) -> None:
    assert client.post(f"/runs/{RUN_ID}/protocol").status_code == 401
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=reader)
    assert r.status_code == 403
    assert "deciding role" in r.json()["detail"]


def test_a_run_not_imported_has_no_protocol_to_start_or_read(
    client: TestClient, decider: dict[str, str]
) -> None:
    assert client.post(f"/runs/{RUN_ID}/protocol", headers=decider).status_code == 404
    assert client.get(f"/runs/{RUN_ID}/protocol", headers=decider).status_code == 404
    assert client.post("/runs/nope/protocol", headers=decider).status_code == 404


def test_a_started_protocol_is_in_draft_status_with_its_audit_trail_entry(
    client: TestClient, decider: dict[str, str], imported: str, fresh_database: Databases
) -> None:
    assert client.get(f"/runs/{RUN_ID}/protocol", headers=decider).status_code == 404
    got = start(client, decider)
    assert (got["equipment"], got["run_id"], got["status"]) == ("TP-201", RUN_ID, "draft")
    assert [(e["event"], e["status"], e["name"], e["reason"]) for e in got["events"]] == [
        ("started", "draft", "Ayu Kartika Sari", None)
    ]
    assert read(client, decider) == got
    with transaction(engine(fresh_database.app)) as s:
        trail = entries(s)
    assert [(e.action, e.record_type, e.record_id) for e in trail][2:] == [
        ("protocol started", "protocol", str(got["id"]))
    ]
    assert trail[-1].new_value == {
        "protocol_id": got["id"],
        "equipment": "TP-201",
        "run_id": RUN_ID,
        "event_id": got["events"][0]["id"],
        "status": "draft",
    }


def test_a_second_open_protocol_of_the_equipment_is_refused(
    client: TestClient, runs: Path, decider: dict[str, str], imported: str
) -> None:
    first = start(client, decider)
    add_drafted_run(runs, OTHER_RUN)
    import_run(client, decider, OTHER_RUN)
    for run_id in (RUN_ID, OTHER_RUN):
        r = client.post(f"/runs/{run_id}/protocol", headers=decider)
        assert r.status_code == 409
        assert f"Protocol {first['id']} of TP-201 is open" in r.json()["detail"]
    # The other run's Protocol is not started.
    assert client.get(f"/runs/{OTHER_RUN}/protocol", headers=decider).status_code == 404


def test_another_equipment_may_have_its_own_open_protocol(
    client: TestClient, runs: Path, decider: dict[str, str], imported: str
) -> None:
    def other(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        meta["corpus"]["equipment"] = "TP-999"

    start(client, decider)
    add_run(runs, OTHER_RUN, other)
    add_drafted_run(runs, OTHER_RUN)
    import_run(client, decider, OTHER_RUN)
    assert start(client, decider, OTHER_RUN)["equipment"] == "TP-999"


def test_two_starts_at_once_give_one_protocol(
    client: TestClient, decider: dict[str, str], imported: str
) -> None:
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(
            pool.map(
                lambda _: client.post(f"/runs/{RUN_ID}/protocol", headers=decider).status_code,
                range(2),
            )
        )
    assert codes == [201, 409]


# Starting once a Protocol is approved: tests/test_protocol_approval_api.py.


def test_a_run_imported_before_its_drafts_became_proposals_cannot_start_one(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    """Its folder has ``drafts.json`` but it holds no ``test_step`` Proposal: no backfill."""
    add_run(runs, OTHER_RUN)
    import_run(client, decider, OTHER_RUN)
    add_drafted_run(runs, OTHER_RUN)
    r = client.post(f"/runs/{OTHER_RUN}/protocol", headers=decider)
    assert r.status_code == 409
    assert "drafts.json" in r.json()["detail"]


def test_a_run_without_drafts_json_can_start_one(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    add_run(runs, OTHER_RUN)
    import_run(client, decider, OTHER_RUN)
    got = start(client, decider, OTHER_RUN)
    assert all(r["drafts"] == [] for r in got["rows"])


# --- Read -----------------------------------------------------------------------------


def test_any_signed_in_role_reads_the_protocol(
    client: TestClient, decider: dict[str, str], reader: dict[str, str], imported: str
) -> None:
    got = start(client, decider)
    assert client.get(f"/runs/{RUN_ID}/protocol").status_code == 401
    assert read(client, reader) == got


def test_one_row_per_requirement_in_requirement_order_with_its_text_and_citation(
    client: TestClient, decider: dict[str, str], imported: str
) -> None:
    got = start(client, decider)
    assert [r["requirement"] for r in got["rows"]] == [
        "URS-TP201-002",
        "URS-TP201-026",
        "URS-TP201-030",
    ]
    first = got["rows"][0]
    assert first["text"] == "Kecepatan turret dapat diatur 20-70 rpm."
    assert first["source"] == {
        "doc": "URS-TP201",
        "rev": 0,
        "page": 1,
        "quote": "Kecepatan turret dapat diatur 20-70 rpm.",
    }
    assert [(d["draft"]["id"], d["proposal"]["state"]) for d in first["drafts"]] == [
        ("TS-URS-TP201-002", "undecided")
    ]
    assert rows(got)["URS-TP201-026"]["drafts"] == []


def test_undecided_coverage_blocks_and_leaves_the_kind_unknown(
    client: TestClient, decider: dict[str, str], imported: str
) -> None:
    got = rows(start(client, decider))
    for r in got.values():
        assert (r["kind"], r["decided_class"], r["coverage"]["state"]) == (
            "undecided",
            None,
            "undecided",
        )
        assert r["blockers"] == ["coverage_undecided"]
        assert r["test_step"] is None


def test_decided_coverage_gives_a_test_step_row_blocking_until_its_draft_is_accepted(
    client: TestClient, decider: dict[str, str], imported: str
) -> None:
    start(client, decider)
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "coverage", "URS-TP201-002"), decision="accepted")
    decide(client, decider, place(ps, "coverage", "URS-TP201-026"), decision="accepted")
    got = rows(read(client, decider))
    assert (got["URS-TP201-002"]["kind"], got["URS-TP201-002"]["decided_class"]) == (
        "test_step",
        "partial",
    )
    # Its draft is not decided yet, and the row has no Test Step.
    assert got["URS-TP201-002"]["blockers"] == ["draft_undecided", "no_test_step"]
    # No draft at all: the row still needs a Test Step.
    assert (got["URS-TP201-026"]["kind"], got["URS-TP201-026"]["blockers"]) == (
        "test_step",
        ["no_test_step"],
    )

    decide(client, decider, place(ps, "test_step", "URS-TP201-002"), decision="accepted")
    row = rows(read(client, decider))["URS-TP201-002"]
    assert row["blockers"] == []
    assert row["test_step"] == {
        "origin": "accepted_draft",
        "proposal_id": place(ps, "test_step", "URS-TP201-002")["id"],
        "version": None,
        "description": "Verifies URS-TP201-002 on site.",
        "method": "Set the turret to 20 rpm and to 70 rpm and read the tachometer.",
        "instrument": "TACH-07 Digital tachometer",
        "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        "acceptance_flag": None,
        "stage": None,
        "witness_required": False,
        "source": "traceq_drafted",
    }


def test_a_rejected_draft_leaves_the_row_without_a_test_step(
    client: TestClient, decider: dict[str, str], imported: str
) -> None:
    start(client, decider)
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "coverage", "URS-TP201-002"), decision="accepted")
    decide(
        client,
        decider,
        place(ps, "test_step", "URS-TP201-002"),
        decision="rejected",
        reason="the wrong range",
    )
    row = rows(read(client, decider))["URS-TP201-002"]
    assert (row["kind"], row["test_step"], row["blockers"]) == ("test_step", None, ["no_test_step"])
    assert row["drafts"][0]["proposal"]["decisions"][0]["decision"] == "rejected"


def test_covered_by_vendor_is_a_vendor_reference_until_its_draft_is_accepted(
    client: TestClient, decider: dict[str, str], imported: str
) -> None:
    start(client, decider)
    ps = proposals(client, decider)
    coverage = place(ps, "coverage", "URS-TP201-002")
    decide(
        client,
        decider,
        coverage,
        decision="edited",
        coverage="covered_by_vendor",
        reason="both FAT steps pass at the limits",
    )
    row = rows(read(client, decider))["URS-TP201-002"]
    assert (row["kind"], row["decided_class"], row["blockers"]) == (
        "vendor_reference",
        "covered_by_vendor",
        [],
    )
    assert [(e["doc"], e["rev"], e["step"]) for e in row["evidence"]] == [
        ("FAT-TP201-M", 0, "FAT-M-02"),
        ("FAT-TP201-M", 0, "FAT-M-05"),
    ]
    # Its draft needs no decision; accepting it anyway tests the requirement again on site.
    decide(client, decider, place(ps, "test_step", "URS-TP201-002"), decision="accepted")
    row = rows(read(client, decider))["URS-TP201-002"]
    assert (row["kind"], row["blockers"]) == ("test_step", [])
    assert row["test_step"]["origin"] == "accepted_draft"


def test_coverage_changed_since_it_was_decided_blocks(
    client: TestClient, runs: Path, decider: dict[str, str], imported: str
) -> None:
    def reread(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        matrix["requirements"][1]["reason"] = "Another reason for the class."

    decide(
        client,
        decider,
        place(proposals(client, decider), "coverage", "URS-TP201-026"),
        decision="accepted",
    )
    add_run(runs, OTHER_RUN, reread)
    add_drafted_run(runs, OTHER_RUN)
    import_run(client, decider, OTHER_RUN)
    row = rows(start(client, decider, OTHER_RUN))["URS-TP201-026"]
    assert (row["kind"], row["coverage"]["state"], row["decided_class"]) == (
        "undecided",
        "changed",
        None,
    )
    assert row["blockers"] == ["coverage_undecided"]


# --- Withdraw -------------------------------------------------------------------------


def test_withdrawing_needs_the_deciding_role_and_a_reason(
    client: TestClient, decider: dict[str, str], reader: dict[str, str], imported: str
) -> None:
    got = start(client, decider)
    url = f"/protocols/{got['id']}/withdraw"
    assert client.post(url, json={"reason": "r"}).status_code == 401
    assert client.post(url, headers=reader, json={"reason": "r"}).status_code == 403
    assert client.post(url, headers=decider, json={"reason": "  "}).status_code == 422
    assert client.post(url, headers=decider, json={}).status_code == 422
    assert (
        client.post("/protocols/999999/withdraw", headers=decider, json={"reason": "r"}).status_code
        == 404
    )
    assert read(client, decider)["status"] == "draft"


def test_a_withdrawn_protocol_frees_the_equipment_for_a_new_one(
    client: TestClient, decider: dict[str, str], imported: str, fresh_database: Databases
) -> None:
    first = start(client, decider)
    got = withdraw(client, decider, first, "a newer run reads the URS revision 1")
    assert got["status"] == "withdrawn"
    assert got["rows"] is None
    assert [(e["event"], e["status"], e["reason"]) for e in got["events"]] == [
        ("started", "draft", None),
        ("withdrawn", "withdrawn", "a newer run reads the URS revision 1"),
    ]
    # Withdrawn once: refused again, with the reason in words.
    r = client.post(f"/protocols/{first['id']}/withdraw", headers=decider, json={"reason": "again"})
    assert r.status_code == 409
    assert "withdrawn" in r.json()["detail"]

    second = start(client, decider)
    assert second["id"] != first["id"]
    assert read(client, decider)["id"] == second["id"]
    with transaction(engine(fresh_database.app)) as s:
        trail = [e for e in entries(s) if e.record_type == "protocol"]
    assert [(e.action, e.record_id, e.reason) for e in trail] == [
        ("protocol started", str(first["id"]), None),
        ("protocol withdrawn", str(first["id"]), "a newer run reads the URS revision 1"),
        ("protocol started", str(second["id"]), None),
    ]
    assert trail[1].old_value == {"status": "draft"}
    assert trail[1].new_value == {"status": "withdrawn", "event_id": got["events"][1]["id"]}


@pytest.mark.parametrize("event", ["submitted", "approved"])
def test_only_a_protocol_in_draft_status_can_be_withdrawn(
    client: TestClient,
    decider: dict[str, str],
    imported: str,
    fresh_database: Databases,
    event: str,
) -> None:
    """The event is added directly (a placeholder copy for ``submitted``): submitting itself is
    tested in ``tests/test_protocol_submission_api.py``, approving in
    ``tests/test_protocol_approval_api.py``."""
    got = start(client, decider)
    with engine(fresh_database.app).begin() as c:
        c.execute(
            text(
                "INSERT INTO protocol_events (protocol_id, event, subject, issuer, name,"
                " frozen_copy, copy_hash) VALUES (:p, :e, 's', 'i', 'n',"
                " CASE WHEN :e = 'submitted' THEN '{}'::jsonb END,"
                " CASE WHEN :e = 'submitted' THEN repeat('0', 64) END)"
            ),
            {"p": got["id"], "e": event},
        )
    r = client.post(f"/protocols/{got['id']}/withdraw", headers=decider, json={"reason": "r"})
    assert r.status_code == 409
    assert event in r.json()["detail"]


# --- Append-only ----------------------------------------------------------------------

REFUSING = (
    "UPDATE assembled_protocols SET run_id = run_id",
    "DELETE FROM assembled_protocols",
    "TRUNCATE assembled_protocols CASCADE",
    "UPDATE protocol_events SET reason = 'rewritten'",
    "DELETE FROM protocol_events",
    "TRUNCATE protocol_events CASCADE",
)


@pytest.mark.parametrize("statement", REFUSING)
def test_the_protocol_tables_are_append_only(
    client: TestClient,
    decider: dict[str, str],
    imported: str,
    fresh_database: Databases,
    statement: str,
) -> None:
    start(client, decider)
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        engine(fresh_database.app).begin() as c,
    ):
        c.execute(text(statement))
    with pytest.raises(DBAPIError, match="append-only"), engine(fresh_database.owner).begin() as c:
        c.execute(text(statement))
    assert read(client, decider)["status"] == "draft"


def test_an_event_takes_the_database_clock_and_a_withdrawal_needs_its_reason(
    client: TestClient, decider: dict[str, str], imported: str, fresh_database: Databases
) -> None:
    got = start(client, decider)
    insert = text(
        "INSERT INTO protocol_events (protocol_id, event, subject, issuer, name)"
        " VALUES (:p, 'withdrawn', 's', 'i', 'n')"
    )
    with pytest.raises(DBAPIError), engine(fresh_database.app).begin() as c:
        c.execute(insert, {"p": got["id"]})
    with engine(fresh_database.app).connect() as c:
        at = c.execute(text("SELECT at FROM protocol_events")).scalar_one()
    assert at == datetime.fromisoformat(got["events"][0]["at"])
    assert at > datetime(2020, 1, 1, tzinfo=UTC)
