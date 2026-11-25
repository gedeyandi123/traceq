"""Answering the printed requirement numbers a run missed, on a Protocol in Draft status, over
HTTP with a real Postgres and the demo issuer (spec #247, "Missed requirement numbers"; ADR
0012 "Submission"; ticket #251).

The TP-201 demo run misses no number, so each test writes its own ``completeness.json`` into
the fixture run of ``tests/test_assembled_protocol_api.py``: ``URS-TP201`` rev 0, checked,
missing ``003`` (page 1) and ``004`` (page 2), with unquoted text; and an annex checked as
``not_applicable``, whose listed number must not be asked about.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_assembled_protocol_api import read, start, withdraw
from test_proposals_api import RUN_ID, bearer, configured, import_run, token
from test_test_step_proposals import add_drafted_run

from traceq.audit import entries
from traceq.db import engine, transaction

URS, ANNEX = "URS-TP201", "URS-TP201-ANNEX"
N003, N004 = "URS-TP201-003", "URS-TP201-004"

COMPLETENESS: dict[str, Any] = {
    "urs": [
        {
            "doc": URS,
            "rev": 0,
            "numbers": "checked",
            "found": 5,
            "missed": [{"number": N003, "page": 1}, {"number": N004, "page": 2}],
            "unquoted": [
                {"page": 1, "text": "Spesifikasi Kebutuhan Pengguna (SKP)\nNomor dokumen URS-TP201"}
            ],
        },
        {
            "doc": ANNEX,
            "rev": 1,
            "numbers": "not_applicable",
            "found": 0,
            "missed": [{"number": "A-1", "page": 1}],
            "unquoted": [{"page": 1, "text": "Lampiran A"}],
        },
    ]
}


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
    return start(client, decider)


def url(protocol: Any) -> str:
    return f"/protocols/{protocol['id']}/missed-numbers"


def body(
    number: str = N003,
    kind: str = "not_a_requirement",
    justification: str = "It numbers the document's heading, not a requirement.",
    doc: str = URS,
    rev: int = 0,
) -> dict[str, Any]:
    return {
        "doc": doc,
        "rev": rev,
        "number": number,
        "kind": kind,
        "justification": justification,
    }


def answer(client: TestClient, headers: dict[str, str], protocol: Any, **kw: Any) -> Any:
    r = client.post(url(protocol), headers=headers, json=body(**kw))
    assert r.status_code == 201, r.text
    return r.json()


def urs(view: Any) -> dict[str, Any]:
    return {u["doc"]: u for u in view["urs"]}


def missed(view: Any) -> dict[str, Any]:
    return {m["number"]: m for m in urs(view)[URS]["missed"]}


# --- Reading --------------------------------------------------------------------------


def test_the_protocol_lists_each_missed_number_per_urs_with_its_page_and_blocks_on_it(
    client: TestClient, reader: dict[str, str], protocol: Any
) -> None:
    got = read(client, reader)
    assert [(u["doc"], u["rev"], u["numbers"]) for u in got["urs"]] == [
        (URS, 0, "checked"),
        (ANNEX, 1, "not_applicable"),
    ]
    listed = urs(got)[URS]["missed"]
    assert [
        (m["number"], m["page"], m["blocking"], m["disposition"], m["dispositions"]) for m in listed
    ] == [
        (N003, 1, True, None, []),
        (N004, 2, True, None, []),
    ]
    # Checked not_applicable: the URS lists no number, whatever the file holds.
    assert urs(got)[ANNEX]["missed"] == []


def test_unquoted_text_is_shown_and_never_blocks(
    client: TestClient, reader: dict[str, str], protocol: Any
) -> None:
    got = urs(read(client, reader))
    assert got[URS]["unquoted"] == COMPLETENESS["urs"][0]["unquoted"]
    assert got[ANNEX]["unquoted"] == [{"page": 1, "text": "Lampiran A"}]
    assert all("blocking" not in u for u in got[URS]["unquoted"])


def test_a_run_without_a_completeness_check_lists_nothing_to_answer(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    (runs / RUN_ID / "completeness.json").unlink()
    import_run(client, decider)
    start(client, decider)
    assert read(client, decider)["urs"] is None


# --- Answering ------------------------------------------------------------------------


def test_answering_needs_a_token_the_deciding_role_and_a_known_protocol(
    client: TestClient, decider: dict[str, str], reader: dict[str, str], protocol: Any
) -> None:
    assert client.post(url(protocol), json=body()).status_code == 401
    r = client.post(url(protocol), headers=reader, json=body())
    assert r.status_code == 403
    assert "deciding role" in r.json()["detail"]
    assert client.post(url({"id": 999999}), headers=decider, json=body()).status_code == 404
    # An unknown Protocol is 404 before a blank justification is 422.
    blank = body(justification="  ")
    assert client.post(url({"id": 999999}), headers=decider, json=blank).status_code == 404


@pytest.mark.parametrize(
    "wrong",
    [
        {"number": "URS-TP201-002"},  # a kept requirement, not missed
        {"rev": 1},  # another revision of the URS
        {"doc": ANNEX, "rev": 1, "number": "A-1"},  # a URS checked not_applicable
    ],
)
def test_only_a_number_the_run_missed_can_be_answered(
    client: TestClient, decider: dict[str, str], protocol: Any, wrong: dict[str, Any]
) -> None:
    r = client.post(url(protocol), headers=decider, json=body(**wrong))
    assert r.status_code == 404, r.text


@pytest.mark.parametrize(
    "bad", [{"justification": "   "}, {"justification": ""}, {"kind": "duplicate"}]
)
def test_an_answer_needs_one_of_the_two_kinds_and_a_justification(
    client: TestClient, decider: dict[str, str], protocol: Any, bad: dict[str, Any]
) -> None:
    r = client.post(url(protocol), headers=decider, json=body(**bad))
    assert r.status_code == 422, r.text
    assert missed(read(client, decider))[N003]["dispositions"] == []


def test_an_answer_stops_its_number_blocking_and_names_who_gave_it(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    got = missed(answer(client, decider, protocol, kind="not_tested_here", justification="  FAT "))
    a = got[N003]["disposition"]
    assert (a["version"], a["kind"], a["justification"]) == (1, "not_tested_here", "FAT")
    assert a["subject"] and a["issuer"] and a["name"] and a["at"]
    assert got[N003]["blocking"] is False
    assert got[N004]["blocking"] is True


def test_an_answer_can_be_changed_every_version_is_kept_and_the_latest_counts(
    client: TestClient, decider: dict[str, str], protocol: Any, fresh_database: Databases
) -> None:
    answer(client, decider, protocol)
    got = missed(
        answer(client, decider, protocol, kind="not_tested_here", justification="Tested in IQ.")
    )[N003]
    assert [(a["version"], a["kind"]) for a in got["dispositions"]] == [
        (1, "not_a_requirement"),
        (2, "not_tested_here"),
    ]
    assert got["disposition"] == got["dispositions"][-1]
    with transaction(engine(fresh_database.app)) as s:
        trail = [e for e in entries(s) if e.record_type == "missed_number"]
    assert [e.action for e in trail] == ["missed number disposition recorded"] * 2
    assert {e.record_id for e in trail} == {f"{protocol['id']}/{URS}/0/{N003}"}
    first, second = trail
    assert first.old_value is None
    assert second.old_value == first.new_value
    assert isinstance(second.new_value, dict)
    assert second.new_value["kind"] == "not_tested_here"


def test_answers_are_refused_unless_the_protocol_is_in_draft_status(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    withdraw(client, decider, protocol, "a newer run reads the URS revision 1")
    r = client.post(url(protocol), headers=decider, json=body())
    assert r.status_code == 409
    assert "Draft status" in r.json()["detail"]


def test_answers_do_not_carry_over_to_a_new_protocol(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    answer(client, decider, protocol)
    withdraw(client, decider, protocol, "restart")
    assert missed(start(client, decider))[N003]["blocking"] is True


def test_two_answers_at_once_both_land_as_versions_1_and_2(
    client: TestClient, decider: dict[str, str], protocol: Any
) -> None:
    def post(kind: str) -> int:
        return client.post(url(protocol), headers=decider, json=body(kind=kind)).status_code

    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(post, ["not_a_requirement", "not_tested_here"]))
    assert codes == [201, 201]
    got = missed(read(client, decider))[N003]["dispositions"]
    assert [a["version"] for a in got] == [1, 2]


# --- Append-only ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE missed_number_answers SET justification = 'rewritten'",
        "DELETE FROM missed_number_answers",
        "TRUNCATE missed_number_answers",
    ],
)
def test_answers_are_append_only(
    client: TestClient,
    decider: dict[str, str],
    protocol: Any,
    fresh_database: Databases,
    statement: str,
) -> None:
    answer(client, decider, protocol)
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        engine(fresh_database.app).begin() as c,
    ):
        c.execute(text(statement))
    with pytest.raises(DBAPIError, match="append-only"), engine(fresh_database.owner).begin() as c:
        c.execute(text(statement))
    assert missed(read(client, decider))[N003]["disposition"]["version"] == 1
