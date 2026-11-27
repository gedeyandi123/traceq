"""The frozen copy of a Protocol started from the Protocol Draft: version 2, separation of
duties and stale approval, over HTTP with a real Postgres and the demo issuer (spec #375,
ticket S4a2; ADR 0012, amended 26 November 2026).

The fixture is that of ``tests/test_draft_to_protocol_api.py``: the draft's ``OQ-02`` is traced
to ``002`` only, ``OQ-26`` to ``026`` and ``030``, ``OQ-40`` to none, ``OQ-50`` was dropped by the
citation check. ``make_ready`` there is the checklist done; here ``OQ-26`` is first mapped to
``026`` by a person.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_assembled_protocol_api import read, rows, withdraw
from test_draft_to_protocol_api import (
    DRAFT,
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
    set_stage,
    start_from_draft,
    step_proposal,
)
from test_execution_completion_api import _pass_value
from test_missed_numbers_api import N003, N004
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
from test_protocol_approval_api import both_roles, persona_token
from test_protocol_submission_api import canonical_sha256
from test_written_test_steps_api import STEP, edit, trail, write

from traceq.assembly.approval import authors
from traceq.assembly.submission import (
    Author,
    FrozenDecision,
    ProtocolCopy,
    ProtocolCopyV2,
    hash_of,
    parse_copy,
)
from traceq.audit import Actor
from traceq.db import engine, transaction
from traceq.db.locks import lock_equipment
from traceq.execution.completion import ExecutionCopy
from traceq.execution.completion import hash_of as execution_hash_of
from traceq.uploads import store


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


def post_submit(
    client: TestClient,
    headers: dict[str, str],
    protocol: Any,
    rev: int | None,
    run_id: str = RUN_ID,
) -> Any:
    body: dict[str, Any] = {"expected_draft_hash": read(client, headers, run_id)["draft_hash"]}
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


# --- Provenance of a decision ---------------------------------------------------------


def _decisions_in(node: Any) -> list[dict[str, Any]]:
    """Every decision of a copy, wherever it sits: an object with a verdict and an author."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "decision" in node and "author" in node and isinstance(node["decision"], str):
            found.append(node)
        for value in node.values():
            found.extend(_decisions_in(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_decisions_in(value))
    return found


def test_every_decision_of_a_version_2_copy_records_its_run_content_and_draft_revision(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    ready(client, decider, protocol)
    copy = submitted(client, decider, protocol)["submission"]["frozen_copy"]
    found = _decisions_in(copy)
    assert len(found) == 16  # Coverage, Test Steps, candidates, findings, draft steps, criteria
    for d in found:
        got = d["provenance"]
        assert got["run_id"] == RUN_ID, d
        assert re.fullmatch(r"[0-9a-f]{64}", got["content_hash"]), d
        assert got["draft_rev"] == 0, d
    # What it names is the content the decision was made on.
    ps = {p["id"]: p for p in proposals(client, decider)}
    [finding] = copy["findings"]
    [decision] = finding["decisions"]
    assert decision["provenance"]["content_hash"] == ps[finding["proposal_id"]]["content_hash"]


def _revision_1_one_page_later(draft: dict[str, Any]) -> None:
    """Revision 1 prints everything the same, one page later."""
    draft["document"].update(rev=1, sha256="cd" * 32)
    for f in draft["findings"]:
        for c in f["citations"]:
            if c["doc"] == DRAFT["doc"]:
                c["page"] += 1
    for step in draft["test_steps"]:
        if step["acceptance"] is not None:
            step["acceptance"]["citation"]["page"] += 1


def test_a_decision_made_on_another_run_and_revision_says_so_and_names_the_same_finding(
    client: TestClient, runs: Path, decider: dict[str, str], protocol: Any
) -> None:
    ready(client, decider, protocol)  # decides the finding on the run of revision 0
    draft_run(runs, RUN_2, _revision_1_one_page_later)
    import_run(client, decider, RUN_2)
    # Revision 1 arrived: the Protocol of revision 0 is withdrawn, one of revision 1 started.
    withdraw(client, decider, protocol, "revision 1 arrived")
    second = start_from_draft(client, decider, RUN_2)
    again = of_kind(proposals(client, decider, RUN_2), "draft")[0]
    decide(client, decider, again, RUN_2, decision="rejected", reason="also on revision 1")
    for requirement in (R026, R030):
        write(client, decider, second, requirement, STEP)
    for requirement in (R002, R026, R030):
        set_stage(client, decider, second, requirement, "OQ")
    dispose(client, decider, second, number=N003)
    dispose(client, decider, second, number=N004, kind="not_tested_here")
    pending = [c for c in read(client, decider, RUN_2)["checklist"] if c["count"]]
    assert pending == [], pending
    view = post_submit(client, decider, second, 1, RUN_2)
    assert view.status_code == 200, view.text
    copy = view.json()["submission"]["frozen_copy"]
    assert copy["source"]["rev"] == 1
    [finding] = copy["findings"]
    assert finding["proposal_id"] == again["id"]  # the same finding, one page later
    newest, oldest = (d["provenance"] for d in finding["decisions"])
    assert (newest["run_id"], newest["draft_rev"]) == (RUN_2, 1)
    assert (oldest["run_id"], oldest["draft_rev"]) == (RUN_ID, 0)
    assert newest["content_hash"] == oldest["content_hash"] == again["content_hash"]


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


V1_WITH_ROWS = Path(__file__).parent / "fixtures" / "frozen_copy_v1_rows.json"
V1_WITH_ROWS_HASH = "8cf92a48f26253e4af152766f066030544cc19132154f36f264a489c5566c57b"
"""``V1_WITH_ROWS`` as the version 1 model of ticket #393 (before the version 2 provenance)
dumped it: two rows (a Vendor Reference and a Test Step row with its written versions, drafts,
step attributes and decisions), a URS with a missed number and its disposition. Its hash is
written down here, not computed from a model, so a change of any version 1 model shows."""


def test_a_stored_version_1_copy_with_rows_loads_and_keeps_its_hash_byte_for_byte() -> None:
    raw = json.loads(V1_WITH_ROWS.read_text(encoding="utf-8"))
    assert canonical_sha256(raw) == V1_WITH_ROWS_HASH
    parsed = parse_copy(raw)
    assert type(parsed) is ProtocolCopy
    assert parsed.model_dump(mode="json") == raw  # nothing added, nothing dropped
    assert hash_of(parsed) == V1_WITH_ROWS_HASH
    # Its decisions are version 1 decisions: none of the provenance of a version 2 decision.
    decisions = _decisions_in(raw)
    assert len(decisions) == 4
    assert all("provenance" not in d for d in decisions)
    assert type(parsed.rows[0].coverage.decision) is FrozenDecision
    # The same bytes are not a version 2 copy.
    assert "schema_version" not in raw


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


def test_a_protocol_pinned_to_an_older_revision_cannot_be_submitted(
    client: TestClient,
    runs: Path,
    decider: dict[str, str],
    protocol: Any,
) -> None:
    ready(client, decider, protocol)
    assert read(client, decider)["latest_draft_rev"] == 0
    # A revision arrives after the Preparer opened the page.
    draft_run(runs, RUN_2, revision_1)
    import_run(client, decider, RUN_2)
    got = read(client, decider)
    assert (got["source"]["rev"], got["latest_draft_rev"]) == (0, 1)
    # Whatever revision the caller names, even the latest: the Protocol is behind it.
    for read_rev in (0, 1):
        refused = post_submit(client, decider, protocol, read_rev)
        assert refused.status_code == 409
        assert refused.headers["X-TraceQ-Conflict"] == "pinned_behind"
        assert "pinned to revision 0" in refused.json()["detail"]
        assert "start a new Protocol" in refused.json()["detail"]
    assert post_submit(client, decider, protocol, None).status_code == 422
    assert read(client, decider)["status"] == "draft"
    # The remedy: withdraw it and start again from the latest revision.
    withdraw(client, decider, protocol, "revision 1 arrived")
    again = start_from_draft(client, decider, RUN_2)
    assert (again["source"]["rev"], again["latest_draft_rev"]) == (1, 1)


def test_a_submitted_protocol_pinned_to_an_older_revision_cannot_be_approved_but_can_be_returned(
    client: TestClient,
    runs: Path,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
) -> None:
    ready(client, decider, protocol)
    findings = [r["findings"] for r in read(client, decider)["rows"]]
    view = post_submit(client, decider, protocol, 0).json()
    assert view["status"] == "submitted"
    # Revision 1 arrives while the Approver reads.
    draft_run(runs, RUN_2, revision_1)
    import_run(client, decider, RUN_2)
    for read_rev in (0, 1):
        refused = post_approve(client, approver, protocol, view, read_rev)
        assert refused.status_code == 409
        assert "pinned to revision 0" in refused.json()["detail"]
    assert post_approve(client, approver, protocol, view, None).status_code == 422
    assert read(client, approver)["status"] == "submitted"
    # Return to Draft: the Protocol stays pinned to revision 0; nothing re-syncs.
    r = client.post(
        f"/protocols/{protocol['id']}/return", headers=approver, json={"reason": "rev 1 arrived"}
    )
    assert r.status_code == 200, r.text
    back = r.json()
    assert back["status"] == "draft"
    assert back["source"] == view["source"]
    assert back["source"]["rev"] == 0 and back["latest_draft_rev"] == 1
    assert [row["findings"] for row in back["rows"]] == findings
    assert post_submit(client, decider, protocol, 1).status_code == 409
    # Withdrawn, a Protocol from the latest revision is the way on.
    withdraw(client, decider, protocol, "restart from revision 1")
    assert start_from_draft(client, decider, RUN_2)["source"]["rev"] == 1


def test_a_protocol_pinned_to_the_latest_revision_is_signed_only_with_the_revision_read(
    client: TestClient,
    runs: Path,
    decider: dict[str, str],
    protocol: Any,
) -> None:
    # A Protocol pinned to revision 1, the latest; a client that read revision 0 is stale.
    draft_run(runs, RUN_2, revision_1)
    import_run(client, decider, RUN_2)
    withdraw(client, decider, protocol, "revision 1 arrived")
    second = start_from_draft(client, decider, RUN_2)
    assert (second["source"]["rev"], second["latest_draft_rev"]) == (1, 1)
    body: dict[str, Any] = {"expected_draft_hash": "0" * 64, "expected_latest_draft_rev": 0}
    stale = client.post(f"/protocols/{second['id']}/submit", headers=decider, json=body)
    assert stale.status_code == 409
    assert stale.headers["X-TraceQ-Conflict"] == "stale_draft"
    assert (
        "newer revision of the Protocol Draft arrived (revision 1, you read 0)"
        in (stale.json()["detail"])
    )
    body.pop("expected_latest_draft_rev")
    missing = client.post(f"/protocols/{second['id']}/submit", headers=decider, json=body)
    assert missing.status_code == 422


def test_a_pinned_behind_refusal_wins_over_a_stale_read_and_carries_its_own_code(
    client: TestClient,
    runs: Path,
    decider: dict[str, str],
    approver: dict[str, str],
    protocol: Any,
) -> None:
    ready(client, decider, protocol)
    view = post_submit(client, decider, protocol, 0).json()
    draft_run(runs, RUN_2, revision_1)
    import_run(client, decider, RUN_2)
    # Both apply (pinned to 0 behind 1, and the caller read 0 or 7): the pin message wins.
    for read_rev in (0, 7):
        refused = post_approve(client, approver, protocol, view, read_rev)
        assert refused.status_code == 409
        assert refused.headers["X-TraceQ-Conflict"] == "pinned_behind"
        assert "pinned to revision 0" in refused.json()["detail"]
        assert "newer revision" not in refused.json()["detail"]


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


# --- The stale-draft check is race-free (spec #375, ticket #393) ----------------------


def _queue_upload(
    fresh_database: Databases,
    rev: int,
    status: str = "queued",
    actor: Actor | None = None,
    sha: str = "b",
) -> None:
    actor = actor or Actor(subject="s", issuer="i", name="Ayu")
    with transaction(engine(fresh_database.app)) as session:
        job = store.accept(
            session,
            actor,
            equipment="TP-201",
            rev=rev,
            sha256=sha * 64,
            size_bytes=1,
            pages=1,
            estimate=Decimal(0),
            ceiling=Decimal(0),
        )
        for step in () if status == "queued" else ("running", status):
            session.execute(
                text(
                    "UPDATE upload_jobs SET status = :s,"
                    " cost_usd = CASE WHEN :s = 'running' THEN NULL ELSE 0 END,"
                    " run_id = CASE WHEN :s = 'succeeded' THEN 'a-run' END,"
                    " finished_at = CASE WHEN :s = 'running' THEN NULL ELSE clock_timestamp() END"
                    " WHERE id = :id"
                ),
                {"s": step, "id": job.id},
            )


@pytest.mark.parametrize("status", ["queued", "running"])
def test_an_upload_queued_or_running_for_the_equipment_counts_as_a_newer_revision(
    client: TestClient,
    decider: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
    status: str,
) -> None:
    ready(client, decider, protocol)
    _queue_upload(fresh_database, 1, status)
    for read_rev in (0, 1):
        refused = post_submit(client, decider, protocol, read_rev)
        assert refused.status_code == 409
        assert refused.headers["X-TraceQ-Conflict"] == "pinned_behind"
        assert "revision 1" in refused.json()["detail"]
        assert "being read" in refused.json()["detail"]
    assert read(client, decider)["status"] == "draft"


def test_a_failed_upload_does_not_hold_a_signature_back(
    client: TestClient,
    decider: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    ready(client, decider, protocol)
    _queue_upload(fresh_database, 1, "failed")
    assert post_submit(client, decider, protocol, 0).status_code == 200


def test_the_check_waits_for_the_revision_being_written_under_the_equipment_lock(
    client: TestClient,
    decider: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    ready(client, decider, protocol)
    with transaction(engine(fresh_database.app)) as writer:
        lock_equipment(writer, "TP-201")
        doc = writer.execute(text("SELECT draft_doc FROM assembled_protocols")).scalar_one()
        writer.execute(
            text(
                "INSERT INTO document_versions (equipment, doc_id, rev, doc_type, source, sha256,"
                " first_seen_run_id) SELECT 'TP-201', :doc, 1, 'protocol_draft',"
                " 'review_package_draft', repeat('c', 64), run_id FROM imported_runs LIMIT 1"
            ),
            {"doc": doc},
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(post_submit, client, decider, protocol, 0)
            time.sleep(1.0)
            assert not pending.done()  # it waits for the writer: it does not read rev 0 now
            writer.commit()
            refused = pending.result(timeout=30)
    assert refused.status_code == 409
    assert refused.headers["X-TraceQ-Conflict"] == "pinned_behind"


# --- The uploader of the pinned revision may not approve (spec #375, ticket #393) ------


def _uploader(demo_issuer: DemoIssuer) -> Actor:
    """``other`` as the upload ledger names them."""
    return Actor(subject="test-0099", issuer=demo_issuer.url, name="Eka Pratama")


def test_the_uploader_of_the_pinned_draft_revision_may_not_approve_but_another_approver_may(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    approver: dict[str, str],
    other: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    _queue_upload(fresh_database, 0, "succeeded", _uploader(demo_issuer))
    ready(client, decider, protocol)
    view = submitted(client, decider, protocol)
    refused = post_approve(client, other, protocol, view, 0)
    assert refused.status_code == 409, refused.text
    assert refused.headers["X-TraceQ-Conflict"] == "uploader_approves"
    assert "uploaded the Protocol Draft revision 0" in refused.json()["detail"]
    assert read(client, decider)["status"] == "submitted"
    assert trail(fresh_database, "protocol")[-1].action == "protocol submitted"
    r = post_approve(client, approver, protocol, view, 0)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


def test_the_uploader_of_another_revision_than_the_pinned_one_may_approve(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    other: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    """Only the pinned revision counts: an earlier or a later upload by the Approver does not."""
    _queue_upload(fresh_database, 0, "succeeded", sha="a")
    _queue_upload(fresh_database, 1, "failed", _uploader(demo_issuer), sha="c")
    ready(client, decider, protocol)
    view = submitted(client, decider, protocol)
    r = post_approve(client, other, protocol, view, 0)
    assert r.status_code == 200, r.text


def test_a_revision_with_no_upload_job_names_no_uploader(
    client: TestClient, decider: dict[str, str], other: dict[str, str], protocol: Any
) -> None:
    """A draft revision that arrived another way than an upload has no uploader to exclude."""
    ready(client, decider, protocol)
    view = submitted(client, decider, protocol)
    assert post_approve(client, other, protocol, view, 0).status_code == 200


def test_a_failed_upload_at_the_pinned_revision_excludes_nobody(
    client: TestClient,
    demo_issuer: DemoIssuer,
    decider: dict[str, str],
    other: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
) -> None:
    """A failed job registered no revision, so its uploader is not the uploader of the pin."""
    _queue_upload(fresh_database, 0, "failed", _uploader(demo_issuer))
    ready(client, decider, protocol)
    view = submitted(client, decider, protocol)
    assert post_approve(client, other, protocol, view, 0).status_code == 200
