"""Approving or returning a submitted Protocol, over HTTP with a real Postgres and the demo
issuer (spec #247, "Submission, freezing and approval", "Identity and demo"; ADR 0012
"Freezing and approval", "Statuses"; ticket #253).

The fixture run and ``make_ready`` are those of ``tests/test_protocol_submission_api.py``. No
demo persona holds both the deciding and the approving role, so the rules on the Preparer and
on authors are tested with tokens the demo issuer's key signs for people holding both.
"""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from test_assembled_protocol_api import read
from test_missed_numbers_api import COMPLETENESS, N003
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
from test_protocol_submission_api import R002, R026, canonical_sha256, make_ready, submit
from test_test_step_proposals import add_drafted_run
from test_written_test_steps_api import STEP, trail, write

from traceq.identity import APPROVING_ROLE, DECIDING_ROLE, EXECUTING_ROLE


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


def persona_token(issuer: DemoIssuer, username: str) -> dict[str, str]:
    r = httpx.post(f"{issuer.url}/demo/token", json={"username": username})
    r.raise_for_status()
    return bearer(r.json()["access_token"])


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    """The fourth demo persona, who holds only the approving role."""
    return persona_token(demo_issuer, "dewi")


def both_roles(issuer: DemoIssuer, subject: str, name: str) -> dict[str, str]:
    """A token for someone holding both roles, which no demo persona does, signed as the demo
    issuer signs its own."""
    kid = httpx.get(f"{issuer.url}/jwks").json()["keys"][0]["kid"]
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": issuer.url,
        "sub": subject,
        "aud": issuer.audience,
        "iat": now,
        "auth_time": int(now.timestamp()),
        "jti": uuid.uuid4().hex,
        "exp": now + timedelta(minutes=5),
        "name": name,
        "roles": [DECIDING_ROLE, APPROVING_ROLE],
    }
    return bearer(jwt.encode(claims, issuer.key, algorithm="RS256", headers={"kid": kid}))


@pytest.fixture
def other(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Someone else who may both decide and approve."""
    return both_roles(demo_issuer, "test-0099", "Eka Pratama")


@pytest.fixture
def protocol(client: TestClient, decider: dict[str, str]) -> Any:
    import_run(client, decider)
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert r.status_code == 201, r.text
    return r.json()


def approve_url(protocol: Any) -> str:
    return f"/protocols/{protocol['id']}/approve"


def return_url(protocol: Any) -> str:
    return f"/protocols/{protocol['id']}/return"


def read_by(view: Any) -> dict[str, Any]:
    """What the Approver read: the current submission's event id and hash."""
    s = view["submission"]
    return {"submission_event_id": s["event_id"], "hash": s["hash"]}


def approve(client: TestClient, headers: dict[str, str], protocol: Any, body: Any) -> Any:
    r = client.post(approve_url(protocol), headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def send_back(client: TestClient, headers: dict[str, str], protocol: Any, reason: str) -> Any:
    r = client.post(return_url(protocol), headers=headers, json={"reason": reason})
    assert r.status_code == 200, r.text
    return r.json()


def submitted(client: TestClient, decider: dict[str, str], protocol: Any) -> Any:
    make_ready(client, decider, protocol)
    return submit(client, decider, protocol)


# --- Identity -------------------------------------------------------------------------


def test_the_fourth_persona_holds_only_the_approving_role(demo_issuer: DemoIssuer) -> None:
    personas = {p["username"]: p for p in httpx.get(f"{demo_issuer.url}/demo/personas").json()}
    assert personas["dewi"]["roles"] == [APPROVING_ROLE]
    assert personas["ayu"]["roles"] == [DECIDING_ROLE, EXECUTING_ROLE]
    assert personas["bima"]["roles"] == [DECIDING_ROLE, EXECUTING_ROLE]
    assert personas["citra"]["roles"] == []
    assert not any(
        DECIDING_ROLE in p["roles"] and APPROVING_ROLE in p["roles"] for p in personas.values()
    )


# --- Approving ------------------------------------------------------------------------


def test_the_approver_approves_the_submission_they_read(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    view = submitted(client, decider, protocol)
    got = approve(client, approver, protocol, read_by(view))
    assert got["status"] == "approved"
    assert [e["event"] for e in got["events"]] == ["started", "submitted", "approved"]
    assert got["events"][-1]["name"] == "Dewi Anggraini Lestari"
    # The page still shows the copy that was approved, and the approval follows it.
    assert got["submission"]["hash"] == view["submission"]["hash"]
    assert got["submission"]["outcome"]["event"] == "approved"
    assert got["rows"] is None
    last = trail(fresh_database, "protocol")[-1]
    assert (last.action, last.record_id) == ("protocol approved", str(protocol["id"]))
    assert last.old_value == {"status": "submitted"}
    assert last.new_value["status"] == "approved"
    assert last.new_value["event_id"] == got["events"][-1]["id"]
    assert last.new_value["submission_event_id"] == view["submission"]["event_id"]
    assert last.new_value["hash"] == view["submission"]["hash"]
    assert isinstance(last.new_value["signature_id"], int)


def test_approving_needs_a_token_and_the_approving_role(
    client: TestClient,
    decider: dict[str, str],
    reader: dict[str, str],
    protocol: Any,
) -> None:
    body = read_by(submitted(client, decider, protocol))
    assert client.post(approve_url(protocol), json=body).status_code == 401
    # The Preparer holds the deciding role only: refused on the role, as in the demo.
    assert client.post(approve_url(protocol), headers=decider, json=body).status_code == 403
    assert client.post(approve_url(protocol), headers=reader, json=body).status_code == 403
    assert read(client, reader)["status"] == "submitted"


def test_approving_an_unknown_protocol_is_404(client: TestClient, approver: dict[str, str]) -> None:
    r = client.post(
        "/protocols/999/approve",
        headers=approver,
        json={"submission_event_id": 1, "hash": "0" * 64},
    )
    assert r.status_code == 404


def test_only_a_submitted_protocol_can_be_approved(
    client: TestClient, approver: dict[str, str], protocol: Any
) -> None:
    r = client.post(
        approve_url(protocol),
        headers=approver,
        json={"submission_event_id": protocol["events"][0]["id"], "hash": "0" * 64},
    )
    assert r.status_code == 409
    assert "draft" in r.json()["detail"]


def test_a_wrong_hash_or_a_stale_submission_is_refused(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    approver: dict[str, str],
    reader: dict[str, str],
    protocol: Any,
) -> None:
    first = read_by(submitted(client, decider, protocol))
    r = client.post(approve_url(protocol), headers=approver, json={**first, "hash": "f" * 64})
    assert r.status_code == 409
    assert "hash" in r.json()["detail"]
    # Returned and resubmitted unchanged: the same hash, a new submission event.
    send_back(client, approver, protocol, "check the instrument")
    again = read_by(submit(client, bearer(token(demo_issuer, decider=True)), protocol))
    assert again["hash"] == first["hash"]
    assert again["submission_event_id"] != first["submission_event_id"]
    r = client.post(approve_url(protocol), headers=approver, json=first)
    assert r.status_code == 409
    assert "submission" in r.json()["detail"]
    assert read(client, reader)["status"] == "submitted"
    assert approve(client, approver, protocol, again)["status"] == "approved"


def test_the_preparer_may_not_approve_even_holding_the_approving_role(
    client: TestClient, demo_issuer: DemoIssuer, decider: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    # The decider persona's own subject, now holding both roles.
    preparer = both_roles(demo_issuer, "demo-0002", "Bima Arya Nugraha")
    view = submit(client, preparer, protocol)
    r = client.post(approve_url(protocol), headers=preparer, json=read_by(view))
    assert r.status_code == 409
    assert "Preparer" in r.json()["detail"]


def test_the_author_of_a_coverage_decision_in_force_may_not_approve(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    ps = proposals(client, decider)
    decide(client, other, place(ps, "coverage", R026), decision="accepted", reason="again")
    view = submit(client, decider, protocol)
    r = client.post(approve_url(protocol), headers=other, json=read_by(view))
    assert r.status_code == 409
    assert "Eka Pratama" in r.json()["detail"]


def test_the_author_of_a_rejected_draft_on_a_written_row_may_not_approve(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    ps = proposals(client, decider)
    decide(client, other, place(ps, "test_step", R002), decision="rejected", reason="wrong")
    write(client, decider, protocol, R002, STEP)
    view = submit(client, decider, protocol)
    r = client.post(approve_url(protocol), headers=other, json=read_by(view))
    assert r.status_code == 409


def test_the_author_of_a_disposition_in_force_may_not_approve(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    dispose(client, other, protocol, number=N003, kind="not_tested_here")
    view = submit(client, decider, protocol)
    r = client.post(approve_url(protocol), headers=other, json=read_by(view))
    assert r.status_code == 409


def test_the_author_of_a_replaced_disposition_may_not_approve(
    client: TestClient,
    decider: dict[str, str],
    other: dict[str, str],
    protocol: Any,
) -> None:
    """Like a written Test Step, a disposition is versioned per Protocol and the copy freezes
    every version: anyone who wrote one did not approve (owner decision on #256, ticket #263)."""
    make_ready(client, decider, protocol)
    dispose(client, other, protocol, number=N003, kind="not_tested_here")
    dispose(client, decider, protocol, number=N003)
    view = submit(client, decider, protocol)
    r = client.post(approve_url(protocol), headers=other, json=read_by(view))
    assert r.status_code == 409
    assert "Eka Pratama" in r.json()["detail"]


def test_the_copy_freezes_every_version_of_a_disposition_and_its_hash_covers_them(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    dispose(client, other, protocol, number=N003, kind="not_tested_here", justification="IQ.")
    sub = submit(client, decider, protocol)["submission"]
    [n003, _] = sub["frozen_copy"]["urs"][0]["missed"]
    got = [
        (d["version"], d["kind"], d["justification"], d["author"]["name"])
        for d in n003["dispositions"]
    ]
    assert got == [
        (
            1,
            "not_a_requirement",
            "It numbers the document's heading, not a requirement.",
            "Ayu Kartika Sari",
        ),
        (2, "not_tested_here", "IQ.", "Eka Pratama"),
    ]
    assert all(d["at"] for d in n003["dispositions"])
    assert n003["disposition"] == n003["dispositions"][-1]
    assert sub["hash"] == canonical_sha256(sub["frozen_copy"])
    without = json.loads(json.dumps(sub["frozen_copy"]))
    without["urs"][0]["missed"][0]["dispositions"] = without["urs"][0]["missed"][0]["dispositions"][
        1:
    ]
    assert canonical_sha256(without) != sub["hash"]


def test_the_author_of_any_written_version_may_not_approve(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    make_ready(client, decider, protocol)
    write(client, other, protocol, R026, {**STEP, "description": "Version 2."})
    write(client, decider, protocol, R026, STEP)
    view = submit(client, decider, protocol)
    assert view["submission"]["frozen_copy"]["rows"][1]["test_step"]["version"] == 3
    r = client.post(approve_url(protocol), headers=other, json=read_by(view))
    assert r.status_code == 409


def test_the_check_reads_the_copy_only(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    """A decision recorded after submission is in force live but not in the copy."""
    view = submitted(client, decider, protocol)
    ps = proposals(client, decider)
    decide(client, other, place(ps, "coverage", R026), decision="accepted", reason="later")
    assert approve(client, other, protocol, read_by(view))["status"] == "approved"


def test_no_protocol_is_started_once_one_is_approved(
    client: TestClient, decider: dict[str, str], approver: dict[str, str], protocol: Any
) -> None:
    approve(client, approver, protocol, read_by(submitted(client, decider, protocol)))
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=decider)
    assert r.status_code == 409
    assert "approved" in r.json()["detail"]
    assert "not yet supported" in r.json()["detail"]


def test_an_approved_protocol_cannot_be_withdrawn_returned_or_written(
    client: TestClient, decider: dict[str, str], approver: dict[str, str], protocol: Any
) -> None:
    approve(client, approver, protocol, read_by(submitted(client, decider, protocol)))
    pid = protocol["id"]
    r = client.post(f"/protocols/{pid}/withdraw", headers=decider, json={"reason": "r"})
    assert r.status_code == 409
    assert (
        client.post(return_url(protocol), headers=approver, json={"reason": "r"}).status_code == 409
    )
    r = client.post(
        f"/protocols/{pid}/test-steps/{R026}", headers=decider, json={"test_step": STEP}
    )
    assert r.status_code == 409


def test_approval_is_stated_as_a_recorded_status_not_an_electronic_signature(
    runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases
) -> None:
    schema = configured(runs, demo_issuer, fresh_database).openapi()
    operation = schema["paths"]["/protocols/{protocol_id}/approve"]["post"]
    assert "not an Electronic Signature" in operation["description"]
    assert "ADR 0007" in operation["description"]


# --- Returning ------------------------------------------------------------------------


def test_a_return_sends_it_back_to_draft_with_its_reason_and_keeps_the_copy(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    view = submitted(client, decider, protocol)
    got = send_back(client, approver, protocol, "  The tachometer is not calibrated.  ")
    assert got["status"] == "draft"
    assert got["events"][-1]["event"] == "returned"
    assert got["events"][-1]["reason"] == "The tachometer is not calibrated."
    # Live rows again; the returned copy stays readable, with the return that followed it.
    assert got["rows"] is not None
    assert got["submission"] is None
    [earlier] = got["submissions"]
    assert earlier["hash"] == view["submission"]["hash"]
    assert earlier["outcome"]["event"] == "returned"
    assert earlier["outcome"]["reason"] == "The tachometer is not calibrated."
    last = trail(fresh_database, "protocol")[-1]
    assert (last.action, last.reason) == ("protocol returned", "The tachometer is not calibrated.")
    assert last.old_value == {"status": "submitted"}
    assert last.new_value == {
        "status": "draft",
        "event_id": got["events"][-1]["id"],
        "submission_event_id": view["submission"]["event_id"],
    }
    # Written Test Steps are accepted again.
    write(client, decider, protocol, R026, STEP)


def test_returning_needs_the_approving_role_a_reason_and_submitted_status(
    client: TestClient,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
) -> None:
    body = {"reason": "r"}
    assert client.post(return_url(protocol), headers=approver, json=body).status_code == 409
    submitted(client, decider, protocol)
    assert client.post(return_url(protocol), json=body).status_code == 401
    assert client.post(return_url(protocol), headers=decider, json=body).status_code == 403
    r = client.post(return_url(protocol), headers=approver, json={"reason": "  "})
    assert r.status_code == 422
    assert client.post("/protocols/999/return", headers=approver, json=body).status_code == 404


def test_every_copy_stays_readable_after_two_returns(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    approver: dict[str, str],
    reader: dict[str, str],
    protocol: Any,
) -> None:
    submitted(client, decider, protocol)
    send_back(client, approver, protocol, "first")
    write(client, decider, protocol, R026, {**STEP, "description": "Changed."})
    submit(client, bearer(token(demo_issuer, decider=True)), protocol)
    send_back(client, approver, protocol, "second")
    view = submit(client, bearer(token(demo_issuer, decider=True)), protocol)
    got = read(client, reader)
    assert [x["outcome"] and x["outcome"]["reason"] for x in got["submissions"]] == [
        "first",
        "second",
        None,
    ]
    assert got["submissions"][0]["hash"] != got["submissions"][1]["hash"]
    assert got["submission"]["event_id"] == view["submission"]["event_id"]


def test_approve_and_return_at_once_cannot_both_succeed(
    client: TestClient, decider: dict[str, str], approver: dict[str, str], protocol: Any
) -> None:
    body = read_by(submitted(client, decider, protocol))

    def act(i: int) -> int:
        if i == 0:
            return client.post(approve_url(protocol), headers=approver, json=body).status_code
        return client.post(return_url(protocol), headers=approver, json={"reason": "r"}).status_code

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(act, range(2)))
    assert codes == [200, 409]
    events = [e["event"] for e in read(client, decider)["events"]]
    assert events[:2] == ["started", "submitted"]
    assert len(events) == 3
