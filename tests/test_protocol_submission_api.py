"""Submitting a Protocol: the blocking checklist, the frozen copy and its hash, over HTTP with a
real Postgres and the demo issuer (spec #247, "Submission, freezing and approval"; ADR 0012
"Freezing and approval"; ticket #252).

The fixture run is the one of ``tests/test_assembled_protocol_api.py`` (``002`` proposed
``partial`` with a range-AC draft, ``026`` ``site_only`` without a draft, ``030`` with no class
and a draft without an AC), with the ``completeness.json`` of
``tests/test_missed_numbers_api.py`` (``003`` and ``004`` missed in ``URS-TP201`` rev 0).
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_assembled_protocol_api import read, rows
from test_missed_numbers_api import COMPLETENESS, N003, N004, URS
from test_missed_numbers_api import answer as dispose
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
from test_test_step_proposals import add_drafted_run
from test_written_test_steps_api import STEP, edit, write

from traceq.audit import entries
from traceq.db import engine, transaction

R002, R026, R030 = "URS-TP201-002", "URS-TP201-026", "URS-TP201-030"


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    add_drafted_run(path)
    (path / RUN_ID / "completeness.json").write_text(json.dumps(COMPLETENESS), encoding="utf-8")
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
    import_run(client, decider)
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert r.status_code == 201, r.text
    return r.json()


def checklist(view: Any) -> dict[str, tuple[int, list[str], list[str]]]:
    return {
        c["check"]: (c["count"], c["requirements"], [n["number"] for n in c["numbers"]])
        for c in view["checklist"]
    }


def make_ready(client: TestClient, headers: dict[str, str], protocol: Any) -> None:
    """Nothing blocks: ``002`` accepted with its draft, ``026`` with a written Test Step,
    ``030`` edited to ``gap`` with its draft edited to a range, both missed numbers decided."""
    ps = proposals(client, headers)
    decide(client, headers, place(ps, "coverage", R002), decision="accepted")
    decide(client, headers, place(ps, "coverage", R026), decision="accepted")
    decide(
        client, headers, place(ps, "coverage", R030), decision="edited", coverage="gap", reason="r"
    )
    decide(client, headers, place(ps, "test_step", R002), decision="accepted")
    write(client, headers, protocol, R026, STEP)
    edit(client, headers, protocol, place(ps, "test_step", R030), STEP)
    dispose(client, headers, protocol, number=N003)
    dispose(client, headers, protocol, number=N004, kind="not_tested_here")


def submit_url(protocol: Any) -> str:
    return f"/protocols/{protocol['id']}/submit"


def submit(client: TestClient, headers: dict[str, str], protocol: Any) -> Any:
    r = client.post(submit_url(protocol), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def canonical_sha256(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def frozen_rows(view: Any) -> dict[str, Any]:
    return {r["requirement"]: r for r in view["submission"]["frozen_copy"]["rows"]}


def return_to_draft(dbs: Databases, protocol: Any) -> None:
    """Returning is a later ticket (#253): the event is added as the application would."""
    with engine(dbs.app).begin() as c:
        c.execute(
            text(
                "INSERT INTO protocol_events (protocol_id, event, reason, subject, issuer, name)"
                " VALUES (:p, 'returned', 'fix it', 's', 'i', 'n')"
            ),
            {"p": protocol["id"]},
        )


# --- The checklist --------------------------------------------------------------------


def test_a_new_protocol_lists_every_check_with_its_count_and_rows(
    client: TestClient, reader: dict[str, str], protocol: Any
) -> None:
    got = read(client, reader)
    assert [c["check"] for c in got["checklist"]] == [
        "coverage_undecided",
        "draft_undecided",
        "no_test_step",
        "acceptance_not_shaped",
        "missed_undecided",
    ]
    assert checklist(got) == {
        "coverage_undecided": (3, [R002, R026, R030], []),
        "draft_undecided": (0, [], []),
        "no_test_step": (0, [], []),
        "acceptance_not_shaped": (0, [], []),
        "missed_undecided": (2, [], [N003, N004]),
    }
    assert got["checklist"][4]["numbers"][0] == {"doc": URS, "rev": 0, "number": N003}
    assert (got["submission"], got["submissions"]) == (None, [])


def test_decided_coverage_shows_undecided_drafts_and_missing_test_steps(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "coverage", R002), decision="accepted")
    decide(client, decider, place(ps, "coverage", R026), decision="accepted")
    decide(
        client, decider, place(ps, "coverage", R030), decision="edited", coverage="gap", reason="r"
    )
    got = read(client, decider)
    assert checklist(got)["draft_undecided"] == (2, [R002, R030], [])
    assert checklist(got)["no_test_step"] == (3, [R002, R026, R030], [])
    assert rows(got)[R002]["blockers"] == ["draft_undecided", "no_test_step"]

    # A drafted AC to be set by a human, accepted as drafted, still blocks.
    decide(client, decider, place(ps, "test_step", R030), decision="accepted")
    got = read(client, decider)
    assert checklist(got)["acceptance_not_shaped"] == (1, [R030], [])
    assert rows(got)[R030]["blockers"] == ["acceptance_not_shaped"]


def test_an_accepted_draft_with_a_free_text_ac_blocks(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def text_ac(data: dict[str, Any]) -> None:
        data["test_steps"][0]["acceptance"] = {"type": "text", "value": "turret runs smoothly"}

    add_drafted_run(runs, RUN_ID, text_ac)
    import_run(client, decider)
    client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "coverage", R002), decision="accepted")
    decide(client, decider, place(ps, "test_step", R002), decision="accepted")
    assert checklist(read(client, decider))["acceptance_not_shaped"] == (1, [R002], [])


def test_a_vendor_reference_does_not_need_its_draft_decided(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ps = proposals(client, decider)
    decide(
        client,
        decider,
        place(ps, "coverage", R002),
        decision="edited",
        coverage="covered_by_vendor",
        reason="both FAT steps pass at the limits",
    )
    got = read(client, decider)
    assert R002 not in checklist(got)["draft_undecided"][1]
    assert rows(got)[R002]["blockers"] == []


# --- Submitting -----------------------------------------------------------------------


def test_submitting_needs_a_token_the_deciding_role_and_a_known_protocol(
    client: TestClient, decider: dict[str, str], reader: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    assert client.post(submit_url(protocol)).status_code == 401
    r = client.post(submit_url(protocol), headers=reader)
    assert r.status_code == 403
    assert "deciding role" in r.json()["detail"]
    assert client.post("/protocols/999999/submit", headers=decider).status_code == 404
    assert read(client, decider)["status"] == "draft"


def test_submitting_is_refused_while_a_check_blocks(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    r = client.post(submit_url(protocol), headers=decider)
    assert r.status_code == 409
    assert "coverage_undecided (3)" in r.json()["detail"]
    assert "missed_undecided (2)" in r.json()["detail"]

    make_ready(client, decider, protocol)
    # Its accepted draft rejected: the row has no Test Step again.
    ps = proposals(client, decider)
    decide(client, decider, place(ps, "test_step", R002), decision="rejected", reason="wrong range")
    r = client.post(submit_url(protocol), headers=decider)
    assert r.status_code == 409
    assert "no_test_step (1)" in r.json()["detail"]
    assert read(client, decider)["status"] == "draft"
    with transaction(engine(fresh_database.app)) as s:
        assert not [e for e in entries(s) if e.action == "protocol submitted"]


def test_a_submitted_protocol_shows_its_frozen_copy_and_hash(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    make_ready(client, decider, protocol)
    got = submit(client, decider, protocol)
    assert got["status"] == "submitted"
    assert [e["event"] for e in got["events"]] == ["started", "submitted"]
    assert (got["rows"], got["urs"], got["checklist"]) == (None, None, None)
    sub = got["submission"]
    assert sub["event_id"] == got["events"][1]["id"]
    assert sub["hash"] == canonical_sha256(sub["frozen_copy"])
    assert got["submissions"] == [sub]
    assert read(client, reader) == got

    with transaction(engine(fresh_database.app)) as s:
        trail = [e for e in entries(s) if e.record_type == "protocol"]
    assert [(e.action, e.record_id) for e in trail] == [
        ("protocol started", str(protocol["id"])),
        ("protocol submitted", str(protocol["id"])),
    ]
    assert trail[1].old_value == {"status": "draft"}
    assert trail[1].new_value == {
        "status": "submitted",
        "event_id": sub["event_id"],
        "hash": sub["hash"],
    }


def test_the_copy_holds_every_row_its_decisions_and_authors(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    ps = proposals(client, decider)
    got = submit(client, decider, protocol)
    copy = got["submission"]["frozen_copy"]
    person = {k: got["events"][0][k] for k in ("subject", "issuer", "name")}
    assert (copy["protocol_id"], copy["equipment"], copy["run_id"]) == (
        protocol["id"],
        "TP-201",
        RUN_ID,
    )
    assert copy["preparer"] == person
    frozen = frozen_rows(got)
    assert list(frozen) == [R002, R026, R030]

    r002 = frozen[R002]
    assert (r002["kind"], r002["coverage"]["coverage_class"]) == ("test_step", "partial")
    assert r002["coverage"]["decision"]["decision"] == "accepted"
    assert r002["coverage"]["decision"]["author"] == person
    assert r002["source"]["doc"] == "URS-TP201"
    step = r002["test_step"]
    assert (step["origin"], step["proposal_id"], step["decision"]["decision"]) == (
        "accepted_draft",
        place(ps, "test_step", R002)["id"],
        "accepted",
    )
    assert step["acceptance"] == {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"}
    assert [(d["draft_id"], d["decision"]["decision"]) for d in r002["drafts"]] == [
        ("TS-URS-TP201-002", "accepted")
    ]

    r026 = frozen[R026]
    assert (r026["test_step"]["origin"], r026["test_step"]["version"]) == ("written", 1)
    assert r026["drafts"] == []
    assert [(v["version"], v["removed"], v["author"]) for v in r026["written"]] == [
        (1, False, person)
    ]

    r030 = frozen[R030]
    assert (r030["coverage"]["coverage_class"], r030["coverage"]["decision"]["decision"]) == (
        "gap",
        "edited",
    )
    assert r030["test_step"]["origin"] == "written"
    assert r030["test_step"]["proposal_id"] == place(ps, "test_step", R030)["id"]
    assert r030["drafts"][0]["decision"]["decision"] == "edited"
    assert r030["written"][0]["decision_id"] == r030["drafts"][0]["decision"]["id"]

    (urs, annex) = copy["urs"]
    assert [
        (m["number"], m["disposition"]["kind"], m["disposition"]["author"]) for m in urs["missed"]
    ] == [
        (N003, "not_a_requirement", person),
        (N004, "not_tested_here", person),
    ]
    assert urs["unquoted"] == COMPLETENESS["urs"][0]["unquoted"]
    assert (annex["numbers"], annex["missed"]) == ("not_applicable", [])


def test_the_copy_keeps_a_vendor_reference_with_its_evidence_and_a_rejected_draft(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    ps = proposals(client, decider)
    draft = place(ps, "test_step", R002)
    decide(client, decider, draft, decision="rejected", reason="the vendor proved it")
    decide(
        client,
        decider,
        place(ps, "coverage", R002),
        decision="edited",
        coverage="covered_by_vendor",
        reason="both FAT steps pass at the limits",
    )
    r002 = frozen_rows(submit(client, decider, protocol))[R002]
    assert (r002["kind"], r002["test_step"]) == ("vendor_reference", None)
    assert [(e["doc"], e["step"]) for e in r002["evidence"]] == [
        ("FAT-TP201-M", "FAT-M-02"),
        ("FAT-TP201-M", "FAT-M-05"),
    ]
    assert r002["drafts"][0]["decision"]["decision"] == "rejected"
    assert r002["drafts"][0]["decision"]["reason"] == "the vendor proved it"


def test_while_submitted_written_steps_and_dispositions_are_refused(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    submit(client, decider, protocol)
    base = f"/protocols/{protocol['id']}"
    r = client.post(f"{base}/test-steps/{R026}", headers=decider, json={"test_step": STEP})
    assert r.status_code == 409
    r = client.post(
        f"{base}/missed-numbers",
        headers=decider,
        json={
            "doc": URS,
            "rev": 0,
            "number": N003,
            "kind": "not_tested_here",
            "justification": "j",
        },
    )
    assert r.status_code == 409
    draft = place(proposals(client, decider), "test_step", R030)
    r = client.post(
        f"{base}/drafts/{draft['id']}/edit",
        headers=decider,
        json={"reason": "r", "test_step": STEP},
    )
    assert r.status_code == 409
    # Submitted once: refused again.
    r = client.post(submit_url(protocol), headers=decider)
    assert r.status_code == 409
    assert "submitted" in r.json()["detail"]


def test_a_decision_recorded_after_submission_does_not_change_the_copy(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    before = submit(client, decider, protocol)["submission"]
    decide(
        client,
        decider,
        place(proposals(client, decider), "test_step", R002),
        decision="rejected",
        reason="decisions are shared: another run's review",
    )
    after = read(client, decider)["submission"]
    assert after == before
    assert after["hash"] == canonical_sha256(after["frozen_copy"])


def test_the_hash_is_stable_and_changes_with_a_row(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    make_ready(client, decider, protocol)
    first = submit(client, decider, protocol)["submission"]
    return_to_draft(fresh_database, protocol)
    assert read(client, decider)["submission"] is None

    # Resubmitted unchanged: the same hash, a new event.
    second = submit(client, decider, protocol)
    assert second["submission"]["hash"] == first["hash"]
    assert second["submission"]["event_id"] != first["event_id"]
    assert [s["event_id"] for s in second["submissions"]] == [
        first["event_id"],
        second["submission"]["event_id"],
    ]

    return_to_draft(fresh_database, protocol)
    write(client, decider, protocol, R026, {**STEP, "method": "Read the tachometer twice."})
    third = submit(client, decider, protocol)["submission"]
    assert third["hash"] != first["hash"]
    assert [v["version"] for v in frozen_rows(read(client, decider))[R026]["written"]] == [1, 2]


def test_two_submissions_at_once_give_one(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(
            pool.map(
                lambda _: client.post(submit_url(protocol), headers=decider).status_code,
                range(2),
            )
        )
    assert codes == [200, 409]
    assert [e["event"] for e in read(client, decider)["events"]] == ["started", "submitted"]


def test_only_a_submitted_event_holds_a_copy(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    insert = text(
        "INSERT INTO protocol_events (protocol_id, event, subject, issuer, name, frozen_copy,"
        " copy_hash) VALUES (:p, :e, 's', 'i', 'n', CAST(:c AS jsonb), :h)"
    )
    for event, copy, hashed in (
        ("submitted", None, None),
        ("approved", "{}", "0" * 64),
        ("submitted", "{}", "not a hash"),
    ):
        with pytest.raises(IntegrityError), engine(fresh_database.app).begin() as c:
            c.execute(insert, {"p": protocol["id"], "e": event, "c": copy, "h": hashed})
