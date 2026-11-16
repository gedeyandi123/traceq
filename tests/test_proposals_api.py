"""Importing a run as Proposals, over HTTP with a real Postgres and the demo issuer (spec #105,
"What Postgres holds", "Proposal identity", "Identity and roles").

Each test gets a database migrated from zero (``tests/conftest.py``), and copies the fixture run
folder of ``tests/test_api.py`` into a runs directory of its own, changed where the test needs.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from conftest import Databases, DemoIssuer
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from traceq.app.api import create_app, openapi_schema
from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.identity import DECIDING_ROLE, IdentitySettings
from traceq.identity.issuer import new_signing_key
from traceq.runs.api import create_router as runs_router

FIXTURE = Path(__file__).parent / "fixtures" / "run"
RUN_ID = "20261113T090000Z-f1a2b3"
OTHER_RUN = "20261120T090000Z-c0ffee"
DATABASE_ROUTES = {
    ("post", "/runs/{run_id}/import"),
    ("get", "/runs/{run_id}/proposals"),
}

type Edit = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], None]


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_run(runs: Path, run_id: str = RUN_ID, edit: Edit | None = None) -> str:
    """Copies the fixture run into ``runs`` as ``run_id``; ``edit`` changes its run.json,
    matrix.json and findings.json in place."""
    folder = runs / run_id
    shutil.copytree(FIXTURE / "runs" / RUN_ID, folder)
    files = ("run.json", "matrix.json", "findings.json")
    meta, matrix, findings = (json.loads((folder / f).read_text("utf-8")) for f in files)
    meta["run_id"] = run_id
    if edit:
        edit(meta, matrix, findings)
    for name, data in zip(files, (meta, matrix, findings), strict=True):
        _write(folder / name, data)
    return run_id


def token(issuer: DemoIssuer, *, decider: bool) -> str:
    personas = httpx.get(f"{issuer.url}/demo/personas").json()
    persona = next(p for p in personas if (DECIDING_ROLE in p["roles"]) is decider)
    r = httpx.post(f"{issuer.url}/demo/token", json={"username": persona["username"]})
    r.raise_for_status()
    return r.json()["access_token"]


def bearer(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def configured(runs: Path, issuer: DemoIssuer, dbs: Databases) -> FastAPI:
    identity = IdentitySettings(issuer=issuer.url, audience=issuer.audience)
    return create_app(runs, identity=identity, database=dbs.app)


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


def proposals(client: TestClient, headers: dict[str, str], run_id: str = RUN_ID) -> Any:
    r = client.get(f"/runs/{run_id}/proposals", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def import_run(client: TestClient, headers: dict[str, str], run_id: str = RUN_ID) -> Any:
    r = client.post(f"/runs/{run_id}/import", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- Two states ---------------------------------------------------------------------


def test_default_settings_answer_401_on_every_database_route_also_for_a_demo_token(
    runs: Path, demo_issuer: DemoIssuer
) -> None:
    client = TestClient(create_app(runs))
    good = bearer(token(demo_issuer, decider=True))
    for method, path in DATABASE_ROUTES:
        url = path.format(run_id=RUN_ID)
        assert client.request(method, url).status_code == 401
        assert client.request(method, url, headers=good).status_code == 401
    # The run-folder routes still work.
    assert client.get(f"/runs/{RUN_ID}/matrix").status_code == 200


def test_the_api_refuses_to_start_with_only_an_issuer_or_only_a_database(
    runs: Path, demo_issuer: DemoIssuer, databases: Databases
) -> None:
    identity = IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience)
    with pytest.raises(ValueError, match="both"):
        create_app(runs, identity=identity)
    with pytest.raises(ValueError, match="both"):
        create_app(runs, database=databases.app)


def test_only_database_routes_write_and_each_needs_a_token(client: TestClient) -> None:
    folder_only = FastAPI()
    folder_only.include_router(runs_router(FIXTURE / "runs"))
    folder_paths = folder_only.openapi()["paths"]
    routes = {
        (m, p) for p, item in openapi_schema()["paths"].items() for m in item if m != "parameters"
    }
    database = {(m, p) for m, p in routes if p not in folder_paths}
    assert database == DATABASE_ROUTES
    assert {m for m, p in routes - database} == {"get"}
    for method, path in database:
        r = client.request(method, path.format(run_id=RUN_ID))
        assert r.status_code == 401, (method, path)
        assert r.headers["www-authenticate"] == "Bearer"


# --- Tokens -------------------------------------------------------------------------


def _forged(issuer: DemoIssuer, change: dict[str, object], key: RSAPrivateKey | None) -> str:
    kid = httpx.get(f"{issuer.url}/jwks").json()["keys"][0]["kid"]
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": issuer.url,
        "sub": "demo-0001",
        "aud": issuer.audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "name": "Ayu Kartika Sari",
        "roles": [DECIDING_ROLE],
        **change,
    }
    return jwt.encode(claims, key or issuer.key, algorithm="RS256", headers={"kid": kid})


@pytest.mark.parametrize(
    ("change", "other_key"),
    [
        ({}, False),
        ({"exp": datetime.now(UTC) - timedelta(minutes=1)}, False),
        ({"aud": "another-api"}, False),
        ({}, True),
    ],
    ids=["control", "expired", "wrong audience", "another key"],
)
def test_a_bad_token_is_refused(
    client: TestClient, demo_issuer: DemoIssuer, change: dict[str, object], other_key: bool
) -> None:
    t = _forged(demo_issuer, change, new_signing_key() if other_key else None)
    r = client.post(f"/runs/{RUN_ID}/import", headers=bearer(t))
    assert r.status_code == (200 if not change and not other_key else 401)


def test_a_person_without_the_deciding_role_cannot_import_but_can_read(
    client: TestClient, demo_issuer: DemoIssuer, decider: dict[str, str]
) -> None:
    reader = bearer(token(demo_issuer, decider=False))
    assert client.post(f"/runs/{RUN_ID}/import", headers=reader).status_code == 403
    assert client.get(f"/runs/{RUN_ID}/proposals", headers=reader).status_code == 404
    import_run(client, decider)
    assert len(proposals(client, reader)) == 6


# --- Import -------------------------------------------------------------------------


def test_import_loads_every_coverage_row_and_finding_and_says_where_each_stands(
    client: TestClient, decider: dict[str, str], fresh_database: Databases
) -> None:
    result = import_run(client, decider)
    assert result == {
        "run_id": RUN_ID,
        "equipment": "TP-201",
        "proposals": 6,
        "already_imported": False,
    }
    got = proposals(client, decider)
    assert [(p["kind"], p["requirement"], p["position"], p["state"]) for p in got] == [
        ("coverage", "URS-TP201-002", None, "undecided"),
        ("coverage", "URS-TP201-026", None, "undecided"),
        ("coverage", "URS-TP201-030", None, "undecided"),
        ("check", None, 0, "undecided"),
        ("check", None, 1, "undecided"),
        ("ai", None, 0, "undecided"),
    ]
    assert len({p["id"] for p in got}) == 6
    with transaction(engine(fresh_database.app)) as s:
        trail = entries(s)
    assert [(e.action, e.record_type, e.record_id, e.actor.name) for e in trail] == [
        ("run imported", "run", RUN_ID, "Ayu Kartika Sari")
    ]
    assert trail[0].actor.subject == "demo-0001"
    provenance = trail[0].new_value
    assert isinstance(provenance, dict)
    assert {k: provenance[k] for k in ("equipment", "created", "model", "prompts")} == {
        "equipment": "TP-201",
        "created": "2026-11-13T09:00:00+00:00",
        "model": "claude-haiku-5-5",
        "prompts": {"segment": "aaaaaaaaaaaa"},
    }
    assert [d["doc_id"] for d in provenance["documents"]] == [
        "URS-TP201",
        "FAT-TP201-M",
        "DS-TP201",
    ]


def test_proposals_stay_readable_after_the_run_folder_is_deleted(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    before = proposals(client, decider)
    shutil.rmtree(runs / RUN_ID)
    assert proposals(client, decider) == before


def test_re_import_changes_nothing(
    client: TestClient, decider: dict[str, str], fresh_database: Databases
) -> None:
    import_run(client, decider)
    before = proposals(client, decider)
    again = import_run(client, decider)
    assert again["already_imported"] is True
    assert again["proposals"] == 6
    assert proposals(client, decider) == before
    with transaction(engine(fresh_database.app)) as s:
        assert len(entries(s)) == 1


def test_an_unknown_run_is_not_found(client: TestClient, decider: dict[str, str]) -> None:
    assert client.post("/runs/nope/import", headers=decider).status_code == 404
    assert client.get("/runs/nope/proposals", headers=decider).status_code == 404


def test_an_import_is_all_or_nothing(
    client: TestClient, runs: Path, decider: dict[str, str], fresh_database: Databases
) -> None:
    def broken(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        findings["ai_findings"][0]["type"] = "not a type"

    add_run(runs, OTHER_RUN, broken)
    assert client.post(f"/runs/{OTHER_RUN}/import", headers=decider).status_code == 422
    assert client.get(f"/runs/{OTHER_RUN}/proposals", headers=decider).status_code == 404
    with transaction(engine(fresh_database.app)) as s:
        assert entries(s) == []


def test_a_folder_naming_another_run_id_is_not_imported(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def renamed(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        meta["run_id"] = RUN_ID

    add_run(runs, OTHER_RUN, renamed)
    assert client.post(f"/runs/{OTHER_RUN}/import", headers=decider).status_code == 422
    assert client.get(f"/runs/{RUN_ID}/proposals", headers=decider).status_code == 404


def test_two_findings_with_the_same_subject_key_are_both_kept(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def twice(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        twin = dict(findings["ai_findings"][0])
        twin["detail"] = "Another reading of the same two quotes."
        twin["citations"] = list(reversed(twin["citations"]))
        findings["ai_findings"].append(twin)

    add_run(runs, OTHER_RUN, twice)
    assert import_run(client, decider, OTHER_RUN)["proposals"] == 7
    ai = [p for p in proposals(client, decider, OTHER_RUN) if p["kind"] == "ai"]
    assert [p["position"] for p in ai] == [0, 1]
    assert ai[0]["id"] != ai[1]["id"]
    assert ai[0]["content_hash"] != ai[1]["content_hash"]


# --- Identity across runs -----------------------------------------------------------


def _by_place(ps: list[dict[str, Any]]) -> dict[tuple[str, object], dict[str, Any]]:
    return {(p["kind"], p["requirement"] or p["position"]): p for p in ps}


def test_identity_and_content_hold_across_runs_that_only_word_or_describe_differently(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def reworded(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        meta.update(created="2026-11-20T09:00:00+00:00", model="another-model")
        meta["prompts"] = {"segment": "cccccccccccc"}
        row = matrix["requirements"][0]
        row["text"] = "Turret dapat diatur antara 20 dan 70 rpm."  # the model's paraphrase
        row["source"]["quote"] = "dapat diatur 20-70 rpm"
        row["source"]["page"] = 3
        row["evidence"][0]["citation"]["quote"] = "Turret speed range 20-60 rpm"
        row["design"][0]["citation"]["quote"] = "Turret speed"
        check = findings["check_findings"][1]
        check["citations"] = list(reversed(check["citations"]))
        ai = findings["ai_findings"][0]
        ai["citations"] = list(reversed(ai["citations"]))
        ai.update(model="another-model", prompt="dddddddddddd", created=meta["created"])

    import_run(client, decider)
    add_run(runs, OTHER_RUN, reworded)
    import_run(client, decider, OTHER_RUN)
    first = _by_place(proposals(client, decider))
    second = _by_place(proposals(client, decider, OTHER_RUN))
    assert first == second


def test_what_a_decision_rests_on_changes_the_content_not_the_identity(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def changed(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        rows = matrix["requirements"]
        rows[0]["source"]["rev"] = 1  # a new URS revision
        rows[1]["coverage"] = "gap"
        findings["check_findings"][0]["detail"] = "FAT-M-04: observed 53 dB(A) is outside"
        findings["check_findings"][1]["rule"]["page"] = 2
        findings["ai_findings"][0]["detail"] = "The serial numbers differ."

    import_run(client, decider)
    add_run(runs, OTHER_RUN, changed)
    import_run(client, decider, OTHER_RUN)
    first = _by_place(proposals(client, decider))
    second = _by_place(proposals(client, decider, OTHER_RUN))
    assert first.keys() == second.keys()
    for place, p in first.items():
        assert second[place]["id"] == p["id"], place
        same = place == ("coverage", "URS-TP201-030")
        assert (second[place]["content_hash"] == p["content_hash"]) is same, place


def test_a_finding_citing_other_text_is_another_proposal(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def moved(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        findings["check_findings"][0]["citations"][0]["page"] = 2
        findings["ai_findings"][0]["citations"][0]["quote"] = "Serial No.: TP201-0042"

    import_run(client, decider)
    add_run(runs, OTHER_RUN, moved)
    import_run(client, decider, OTHER_RUN)
    first = _by_place(proposals(client, decider))
    second = _by_place(proposals(client, decider, OTHER_RUN))
    changed = {("check", 0), ("ai", 0)}
    for place, p in first.items():
        assert (second[place]["id"] == p["id"]) is (place not in changed), place


def test_the_same_requirement_of_another_equipment_is_another_proposal(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    def other(meta: dict[str, Any], matrix: dict[str, Any], findings: dict[str, Any]) -> None:
        meta["corpus"]["equipment"] = "TP-999"

    import_run(client, decider)
    add_run(runs, OTHER_RUN, other)
    assert import_run(client, decider, OTHER_RUN)["equipment"] == "TP-999"
    first = {p["id"] for p in proposals(client, decider)}
    assert first.isdisjoint(p["id"] for p in proposals(client, decider, OTHER_RUN))
