"""A real round 2 over two draft revisions (spec #375, ticket S3): finding identity across
revisions, the per-finding round diff, and decisions bound to the content they were made on.

Synthetic cases reuse the fixture run and Protocol Draft of ``tests/test_protocol_draft_api.py``;
the last tests replay revision 0 and revision 1 of the 0.2.0 package (dev only, no live call).
"""

from __future__ import annotations

import copy
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from test_proposals_api import (
    bearer,
    configured,
    decide,
    import_run,
    proposals,
    token,
)
from test_protocol_draft_api import DRAFT, add_package_run, drafted

from traceq.runs.run import run

RUN_2 = "20261120T090000Z-c0ffee"
RUN_3 = "20261125T090000Z-decade"
ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "recordings"


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    path = tmp_path / "runs"
    path.mkdir()
    add_package_run(path)
    return path


@pytest.fixture
def client(runs: Path, demo_issuer: DemoIssuer, fresh_database: Databases) -> TestClient:
    return TestClient(configured(runs, demo_issuer, fresh_database))


@pytest.fixture
def decider(demo_issuer: DemoIssuer) -> dict[str, str]:
    return bearer(token(demo_issuer, decider=True))


type Edit = Callable[[dict[str, Any]], None]


def next_run(runs: Path, run_id: str, edit: Edit | None = None) -> str:
    return add_package_run(runs, run_id, edit)


def rounds(client: TestClient, headers: dict[str, str], run_id: str) -> Any:
    r = client.get(f"/runs/{run_id}/rounds", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def changes(diff: dict[str, Any]) -> dict[tuple[str | None, str | None], str]:
    """Each finding's change, by its Test Step (or table row) and requirement."""
    return {
        (f["test_step"], f["requirement"]): f["change"]
        for f in diff["findings"]
        if f["kind"] == "draft"
    }


def revision_1(draft: dict[str, Any]) -> None:
    draft["document"].update(rev=1, sha256="cd" * 32)


# --- Identity ---------------------------------------------------------------------------


def test_a_finding_is_the_same_finding_in_the_next_draft_revision(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    first = drafted(proposals(client, decider))
    made = decide(client, decider, first[0], decision="accepted")
    next_run(runs, RUN_2, revision_1)
    import_run(client, decider, RUN_2)
    second = drafted(proposals(client, decider, RUN_2))
    assert [(p["id"], p["content_hash"]) for p in second] == [
        (p["id"], p["content_hash"]) for p in first
    ]
    assert (second[0]["state"], second[0]["decisions"]) == ("decided", [made])


def _page_shift(draft: dict[str, Any]) -> None:
    """Revision 1 prints the same text one page later: every citation of the draft moves from
    its page to the next (the URS citations stay where they are)."""
    for f in draft["findings"]:
        for c in f["citations"]:
            if c["doc"] == DRAFT["doc"]:
                c["page"] += 1
    for s in draft["test_steps"]:
        s["acceptance"]["citation"]["page"] += 1
    for r in draft["trace_rows"]:
        r["citation"]["page"] += 1


def _of_kind(ps: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [p for p in ps if p["kind"] == kind]


def test_a_finding_whose_page_shifts_between_revisions_is_the_same_finding(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    """The OQ-24 anomaly: the same defect on page 6 of revision 0 and page 7 of revision 1 is
    one finding that persists, not one resolved and another new."""
    import_run(client, decider)
    first = drafted(proposals(client, decider))
    made = decide(client, decider, first[0], decision="accepted")

    def round_2(draft: dict[str, Any]) -> None:
        revision_1(draft)
        _page_shift(draft)

    next_run(runs, RUN_2, round_2)
    import_run(client, decider, RUN_2)
    second = drafted(proposals(client, decider, RUN_2))
    assert [(p["id"], p["content_hash"]) for p in second] == [
        (p["id"], p["content_hash"]) for p in first
    ]
    assert (second[0]["state"], second[0]["decisions"]) == ("decided", [made])
    diff = rounds(client, decider, RUN_2)["diff"]
    assert set(changes(diff).values()) == {"persisted"}
    assert (diff["findings_resolved"], diff["findings_new"]) == (0, 0)


def test_a_criterion_whose_page_shifts_keeps_its_identity_content_and_decision(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    before = _of_kind(proposals(client, decider), "draft_criterion")
    assert len(before) == 1
    made = decide(client, decider, before[0], decision="accepted")

    def round_2(draft: dict[str, Any]) -> None:
        revision_1(draft)
        _page_shift(draft)

    next_run(runs, RUN_2, round_2)
    import_run(client, decider, RUN_2)
    after = _of_kind(proposals(client, decider, RUN_2), "draft_criterion")
    assert [(p["id"], p["content_hash"]) for p in after] == [
        (p["id"], p["content_hash"]) for p in before
    ]
    assert (after[0]["state"], after[0]["decisions"]) == ("decided", [made])


def _two_findings_of_one_step_and_type(draft: dict[str, Any]) -> None:
    """OQ-03 against URS-TP201-003 twice, the second citing another document than the first."""
    twin = copy.deepcopy(draft["findings"][0])
    twin["citations"][0]["doc"] = "REF-TP201"
    twin["detail"] += " (second document)"
    draft["findings"].insert(1, twin)


def test_two_findings_of_one_step_and_type_are_told_apart_by_the_documents_they_cite(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    next_run(runs, RUN_2, _two_findings_of_one_step_and_type)
    import_run(client, decider, RUN_2)
    both = drafted(proposals(client, decider, RUN_2))
    assert len({p["id"] for p in both}) == 4
    own, other = both[0], both[1]
    made = decide(client, decider, other, run_id=RUN_2, decision="accepted")

    def first_is_fixed(draft: dict[str, Any]) -> None:
        _two_findings_of_one_step_and_type(draft)
        del draft["findings"][0]  # the first finding is fixed; the other document's is not

    next_run(runs, RUN_3, first_is_fixed)
    import_run(client, decider, RUN_3)
    left = drafted(proposals(client, decider, RUN_3))
    # The decision stays on the finding it was made on and does not move to the other.
    assert other["id"] in {p["id"] for p in left} and own["id"] not in {p["id"] for p in left}
    kept = next(p for p in left if p["id"] == other["id"])
    assert (kept["state"], kept["decisions"]) == ("decided", [made])


def test_two_findings_citing_the_same_documents_fall_back_to_their_order(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    """A page does not tell findings apart (it shifts between revisions), so two findings of one
    Test Step, type and requirement that cite the same documents are told apart by order."""

    def twins(draft: dict[str, Any]) -> None:
        twin = copy.deepcopy(draft["findings"][0])
        twin["citations"][0]["page"] = 5
        twin["detail"] += " (second place)"
        draft["findings"].insert(1, twin)

    def shifted_twins(draft: dict[str, Any]) -> None:
        revision_1(draft)
        twins(draft)
        _page_shift(draft)

    next_run(runs, RUN_2, twins)
    import_run(client, decider, RUN_2)
    both = drafted(proposals(client, decider, RUN_2))
    assert len({p["id"] for p in both}) == 4
    next_run(runs, RUN_3, shifted_twins)
    import_run(client, decider, RUN_3)
    again = drafted(proposals(client, decider, RUN_3))
    assert [p["id"] for p in again] == [p["id"] for p in both]


DATASHEET = {"doc": "DS-TP201", "rev": 0}
CAPABILITY_ROWS = (("Maximum noise, idle", 55.0, 3), ("Maximum noise, full load", 60.0, 4))
"""Two rows of one Datasheet, each a maximum OQ-03's Acceptance Criterion goes above."""


def _capability(row: str, top: float, page: int) -> dict[str, Any]:
    return {
        "type": "ac_outside_documented_capability",
        "layer": "rule",
        "test_step": "OQ-03",
        "row": None,
        "requirement": "URS-TP201-003",
        "detail": (
            f"OQ-03 requires at most 65 dB(A), above the maximum {top:g} dB(A) the Datasheet"
            " DS-TP201 states: the limit may not be reachable."
        ),
        "ac": {"type": "range", "unit": "dB(A)", "max": 65},
        "urs_limit": None,
        "capability": {"type": "range", "unit": "dB(A)", "max": top},
        "label": "not reviewed by a practitioner",
        "citations": [
            {**DRAFT, "page": 2, "quote": "OQ-03 Kebisingan maks. 65 dB(A)"},
            {**DATASHEET, "page": page, "quote": f"{row} {top:g} dB(A)"},
        ],
    }


def _two_capability_findings(rows: tuple[tuple[str, float, int], ...]) -> Edit:
    """OQ-03 against URS-TP201-003, whose matrix row holds both Datasheet rows: a capability
    finding on each of ``rows``, appended after the older findings as the rule does."""

    def edit(draft: dict[str, Any]) -> None:
        facts = [
            {
                "name": row,
                "printed": f"{top:g} dB(A)",
                "citation": {**DATASHEET, "page": page, "quote": f"{row} {top:g} dB(A)"},
            }
            for row, top, page in CAPABILITY_ROWS
        ]
        comparator = {**DATASHEET, "kind": "design", "facts": facts}
        draft["test_steps"][0]["traced"][0]["comparators"] = [comparator]
        draft["findings"] += [_capability(*r) for r in rows]

    return edit


def test_two_capability_findings_of_one_step_are_told_apart_by_their_datasheet_row(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    """Both cite the draft and the same Datasheet, so the cited documents do not tell them
    apart; the Datasheet row does. When the first is fixed in revision 1, the second persists
    with its decision: it does not take the first one's place by order."""
    next_run(runs, RUN_2, _two_capability_findings(CAPABILITY_ROWS))
    import_run(client, decider, RUN_2)
    both = [p for p in drafted(proposals(client, decider, RUN_2)) if p["position"] >= 3]
    assert len({p["id"] for p in both}) == 2
    idle, full_load = both
    made = decide(client, decider, full_load, run_id=RUN_2, decision="accepted")

    def idle_is_fixed(draft: dict[str, Any]) -> None:
        revision_1(draft)
        _two_capability_findings(CAPABILITY_ROWS[1:])(draft)

    next_run(runs, RUN_3, idle_is_fixed)
    import_run(client, decider, RUN_3)
    left = [p for p in drafted(proposals(client, decider, RUN_3)) if p["position"] >= 3]
    assert [(p["id"], p["content_hash"]) for p in left] == [
        (full_load["id"], full_load["content_hash"])
    ]
    assert (left[0]["state"], left[0]["decisions"]) == ("decided", [made])
    assert idle["id"] not in {p["id"] for p in left}
    diff = rounds(client, decider, RUN_3)["diff"]
    assert (
        diff["findings_resolved"],
        diff["findings_persisted_changed"],
        diff["findings_new"],
    ) == (1, 0, 0)


# --- The round diff ---------------------------------------------------------------------


def test_a_re_uploaded_revision_is_unchanged_not_removed(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    next_run(runs, RUN_2)  # the same revision, uploaded again
    import_run(client, decider, RUN_2)
    diff = rounds(client, decider, RUN_2)["diff"]
    assert DRAFT["doc"] in diff["documents_unchanged"]
    assert diff["documents_removed"] == []
    assert diff["documents_revised"] == [] and diff["documents_added"] == []


def test_a_revised_draft_is_revised_and_each_finding_has_its_state(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)

    def round_2(draft: dict[str, Any]) -> None:
        revision_1(draft)
        # OQ-03 against URS-TP201-003 is fixed (resolved); against URS-TP201-004 it stays on
        # the same limit (persisted); the row of URS-TP201-027 names another Test Step
        # (persisted, changed); a finding on a new Test Step appears (new).
        del draft["findings"][0]
        draft["trace_rows"][0]["test_steps"] = ["OQ-27", "OQ-28"]
        draft["findings"][-1]["detail"] += " Also OQ-28."
        added = copy.deepcopy(draft["findings"][0])
        added["test_step"] = "OQ-05"
        added["requirement"] = "URS-TP201-005"
        draft["findings"].append(added)

    next_run(runs, RUN_2, round_2)
    import_run(client, decider, RUN_2)
    diff = rounds(client, decider, RUN_2)["diff"]
    assert diff["documents_revised"] == [DRAFT["doc"]] and diff["documents_removed"] == []
    assert changes(diff) == {
        ("OQ-03", "URS-TP201-004"): "persisted",
        ("URS-TP201-027", "URS-TP201-027"): "persisted_changed",
        ("OQ-05", "URS-TP201-005"): "new",
        ("OQ-03", "URS-TP201-003"): "resolved",
    }
    # The Equipment's own findings (the fixture run's) are the same in both runs: persisted.
    equipment = [f for f in diff["findings"] if f["kind"] != "draft"]
    assert equipment and {f["change"] for f in equipment} == {"persisted"}
    assert [f["change"] for f in diff["findings"] if f["kind"] == "draft"] == [
        "persisted",
        "persisted_changed",
        "new",
        "resolved",
    ]
    assert diff["findings_resolved"] == 1 and diff["findings_new"] == 1
    assert diff["findings_persisted"] == len(equipment) + 2
    assert diff["findings_persisted_changed"] == 1


def test_a_decision_carries_over_to_a_persisted_finding_and_is_asked_again_on_a_changed_one(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    first = drafted(proposals(client, decider))
    decide(client, decider, first[1], decision="accepted")
    decide(client, decider, first[2], decision="rejected", reason="tested in PQ")

    def round_2(draft: dict[str, Any]) -> None:
        revision_1(draft)
        draft["trace_rows"][0]["test_steps"] = ["OQ-27", "OQ-28"]

    next_run(runs, RUN_2, round_2)
    import_run(client, decider, RUN_2)
    diff = rounds(client, decider, RUN_2)["diff"]
    got = {(p["id"]): p["state"] for p in drafted(proposals(client, decider, RUN_2))}
    assert [got[p["id"]] for p in first] == ["undecided", "decided", "changed"]
    assert (diff["decisions_carried_forward"], diff["decisions_changed"]) == (1, 1)
    equipment = [f for f in diff["findings"] if f["kind"] != "draft"]
    assert diff["decisions_undecided"] == 1 + len(equipment)  # the Equipment's were never decided


# --- A decision binds to the content it was made on ---------------------------------------


def _acceptance(printed: str, **limit: float) -> Edit:
    def edit(draft: dict[str, Any]) -> None:
        ac = draft["test_steps"][0]["acceptance"]
        ac["printed"] = printed
        ac["value"]["max"] = limit["max"]

    return edit


def _mapped(*requirements: str) -> Edit:
    def edit(draft: dict[str, Any]) -> None:
        step = draft["test_steps"][0]
        step["traced"] = [t for t in step["traced"] if t["requirement"] in requirements]

    return edit


@pytest.mark.parametrize(
    ("edit", "what"),
    [
        (_acceptance("maks. 65 dB(A) pada 1 m", max=65), "the printed Acceptance Criterion"),
        (_acceptance("maks. 65 dB(A)", max=66), "the parsed Acceptance Criterion"),
        (_mapped("URS-TP201-003"), "the requirement mapping"),
        (lambda d: d["test_steps"][0].update(requirements=["URS-TP201-003"]), "the step header"),
    ],
    ids=["printed", "parsed", "mapping", "header"],
)
def test_a_changed_test_step_mapping_or_criterion_asks_again_though_the_finding_reads_alike(
    client: TestClient, runs: Path, decider: dict[str, str], edit: Edit, what: str
) -> None:
    import_run(client, decider)
    first = drafted(proposals(client, decider))
    made = decide(client, decider, first[0], decision="accepted")
    next_run(runs, RUN_2, edit)
    import_run(client, decider, RUN_2)
    second = drafted(proposals(client, decider, RUN_2))
    assert second[0]["id"] == first[0]["id"], what
    assert second[0]["content_hash"] != first[0]["content_hash"], what
    assert (second[0]["state"], second[0]["previous"]) == ("changed", made), what


def _step_field(field: str, value: str) -> Edit:
    def edit(draft: dict[str, Any]) -> None:
        draft["test_steps"][0][field] = value

    return edit


@pytest.mark.parametrize("field", ["description", "method", "instrument"])
def test_a_changed_step_description_method_or_instrument_asks_again_on_its_finding(
    client: TestClient, runs: Path, decider: dict[str, str], field: str
) -> None:
    """ADR 0012, "Binding to content": a finding's decision rests on the Test Step's content,
    which is its description, method and instrument as well as its criterion and mapping."""
    next_run(runs, RUN_2, _step_field(field, "as first read"))
    import_run(client, decider, RUN_2)
    first = drafted(proposals(client, decider, RUN_2))
    made = decide(client, decider, first[0], RUN_2, decision="accepted")
    next_run(runs, RUN_3, _step_field(field, "as reworded in the next revision"))
    import_run(client, decider, RUN_3)
    second = drafted(proposals(client, decider, RUN_3))
    assert second[0]["id"] == first[0]["id"]
    assert second[0]["content_hash"] != first[0]["content_hash"]
    assert (second[0]["state"], second[0]["previous"]) == ("changed", made)
    # A finding of another Test Step does not ask again: only the step it rests on changed.
    assert second[2]["content_hash"] == first[2]["content_hash"]


def test_content_that_reverts_does_not_revive_an_older_decision_over_a_newer_one(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    first = drafted(proposals(client, decider))
    decide(client, decider, first[0], decision="accepted")
    next_run(runs, RUN_2, _acceptance("maks. 70 dB(A)", max=70))
    import_run(client, decider, RUN_2)
    changed = drafted(proposals(client, decider, RUN_2))[0]
    newer = decide(
        client, decider, changed, RUN_2, decision="rejected", reason="70 is the site limit"
    )
    # Revision 2 prints what revision 0 printed: the old decision is not the one that stands.
    next_run(runs, RUN_3)
    import_run(client, decider, RUN_3)
    back = drafted(proposals(client, decider, RUN_3))[0]
    assert back["content_hash"] == first[0]["content_hash"]
    assert (back["state"], back["previous"], back["decisions"]) == ("changed", newer, [])
    counts = client.get(f"/runs/{RUN_3}/decision-counts", headers=decider).json()["draft"]
    assert (counts["changed"], counts["accepted"], counts["rejected"]) == (1, 0, 0)


def test_a_decision_made_again_on_reverted_content_stands(
    client: TestClient, runs: Path, decider: dict[str, str]
) -> None:
    import_run(client, decider)
    decide(client, decider, drafted(proposals(client, decider))[0], decision="accepted")
    next_run(runs, RUN_2, _acceptance("maks. 70 dB(A)", max=70))
    import_run(client, decider, RUN_2)
    decide(
        client,
        decider,
        drafted(proposals(client, decider, RUN_2))[0],
        RUN_2,
        decision="rejected",
        reason="70 is the site limit",
    )
    next_run(runs, RUN_3)
    import_run(client, decider, RUN_3)
    back = drafted(proposals(client, decider, RUN_3))[0]
    again = decide(
        client, decider, back, RUN_3, decision="accepted", reason="back to 65, as first read"
    )
    now = drafted(proposals(client, decider, RUN_3))[0]
    assert (now["state"], now["decisions"][0]) == ("decided", again)


# --- Two real revisions of the 0.2.0 package, replayed ------------------------------------


@pytest.fixture(scope="module")
def replayed_runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    """A run over revision 0 and one over revision 1, replayed from the recordings that were
    made live once (``recordings/haiku-oq-draft-r8``): no live call."""
    out = tmp_path_factory.mktemp("two-revisions")
    first, second = (
        run(
            RECORDINGS / "corpus-0.1.1",
            out,
            RECORDINGS / "haiku-r10",
            "claude-haiku-5-5",
            equipment="TP-201",
            review_package=RECORDINGS / "TP-201-OQ-draft-0.2.0",
            package_recordings=RECORDINGS / "haiku-oq-draft-r8",
            draft_rev=rev,
        )
        for rev in (0, 1)
    )
    assert first.metadata["calls"]["live"] == second.metadata["calls"]["live"] == 0
    return out, first.metadata["run_id"], second.metadata["run_id"]


def test_a_run_over_revision_0_and_one_over_revision_1_make_a_real_round_2(
    replayed_runs: tuple[Path, str, str],
    tmp_path: Path,
    demo_issuer: DemoIssuer,
    fresh_database: Databases,
) -> None:
    out, first, second = replayed_runs
    served = tmp_path / "runs"
    for run_id in (first, second):
        shutil.copytree(out / run_id, served / run_id)
    client = TestClient(configured(served, demo_issuer, fresh_database))
    decider = bearer(token(demo_issuer, decider=True))
    import_run(client, decider, first)
    import_run(client, decider, second)
    body = rounds(client, decider, second)
    assert [r["round_number"] for r in body["rounds"]] == [1, 2]
    diff = body["diff"]
    assert diff["documents_revised"] == ["OQ-TP201"] and diff["documents_removed"] == []
    states = {f["change"] for f in diff["findings"]}
    # Revision 1 fixes some defects, leaves one, adds one and carries one wrong fix.
    assert states == {"resolved", "persisted", "persisted_changed", "new"}
    assert diff["findings_persisted"] == sum(
        f["change"] in {"persisted", "persisted_changed"} for f in diff["findings"]
    )
    assert all(f["finding_type"] for f in diff["findings"])
    # The defect of OQ-24 sits on page 6 of revision 0 and page 7 of revision 1: it persists,
    # it is not one finding resolved and another new (S8, the OQ-24 anomaly).
    by_change = {
        (f["finding_type"], f["test_step"], f["requirement"]): f["change"]
        for f in diff["findings"]
        if f["kind"] == "draft"
    }
    assert by_change[("ac_deviates_from_urs", "OQ-24", "URS-TP201-029")] == "persisted"
    assert len(by_change) == sum(f["kind"] == "draft" for f in diff["findings"])
