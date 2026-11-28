"""Contract tests for ``scripts/demo_seed.py`` against actual TraceQ API schemas."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from traceq.execution.results import ConfirmWitnessRequest, InstrumentInput, RecordAttemptRequest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_seed.py"


def _load_demo_seed() -> Any:
    spec = importlib.util.spec_from_file_location("demo_seed", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["demo_seed"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_passing_value_matches_record_attempt_request_schema() -> None:
    ds = _load_demo_seed()
    for acceptance in (
        {"type": "number", "value": 10.0, "unit": "rpm"},
        {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        {"type": "range", "min": 15.0, "max": None, "unit": "rpm"},
        {"type": "range", "min": None, "max": 80.0, "unit": "rpm"},
        {"type": "one_of", "allowed": ["Pass", "OK"]},
        {"type": "present"},
    ):
        val = ds._passing_value(acceptance)
        req = RecordAttemptRequest(outcome_kind="value", value=val)
        assert req.outcome_kind == "value"

    assert ds._passing_value({"type": "range", "min": 20.0, "max": 70.0})["value"] == 45.0
    assert ds._passing_value({"type": "one_of", "allowed": ["Pass", "OK"]})["value"] == "Pass"


def test_instrument_payload_matches_instrument_input_schema() -> None:
    ds = _load_demo_seed()
    inst = ds._instrument_payload("URS-TP201-026")
    parsed = InstrumentInput.model_validate(inst)
    assert parsed.identifier == "CAL-URS-TP201-026"


def test_witness_payload_matches_witness_confirm_request_and_skips_active() -> None:
    ds = _load_demo_seed()
    unwitnessed_ver = {
        "version": 2,
        "version_hash": "abc123",
        "witness_confirmations": [],
    }
    assert ds._needs_witness(unwitnessed_ver) is True
    payload = ds._witness_payload(unwitnessed_ver)
    parsed = ConfirmWitnessRequest.model_validate(payload)
    assert parsed.version_number == 2
    assert parsed.version_hash == "abc123"

    witnessed_ver = {
        "version": 2,
        "version_hash": "abc123",
        "witness_confirmations": [{"status": "active"}],
    }
    assert ds._needs_witness(witnessed_ver) is False


def test_ensure_approved_protocol_imports_and_handles_changed_and_null_coverage() -> None:
    ds = _load_demo_seed()
    calls: list[tuple[str, str, Any]] = []

    class _Resp:
        def __init__(self, status_code: int, body: Any) -> None:
            self.status_code = status_code
            self._body = body
            self.text = str(body)

        def json(self) -> Any:
            return self._body

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}: {self._body}")

    class _FakeClient:
        def get(self, url: str, headers: dict[str, str] | None = None) -> _Resp:
            calls.append(("GET", url, None))
            if url.endswith("/proposals"):
                return _Resp(
                    200,
                    [
                        {"id": 1, "kind": "coverage", "state": "undecided"},
                        {"id": 2, "kind": "coverage", "state": "changed"},
                    ],
                )
            if url.endswith("/protocol"):
                return _Resp(404, {})
            raise AssertionError(f"unexpected GET {url}")

        def post(self, url: str, headers: dict[str, str] | None = None, json: Any = None) -> _Resp:
            calls.append(("POST", url, json))
            if url.endswith("/import"):
                return _Resp(200, {"run_id": "r1", "already_imported": False})
            if url.endswith("/proposals/1/decisions"):
                return _Resp(201, {"id": 10})
            if url.endswith("/proposals/2/decisions"):
                # Simulate coverage row with proposed_class=None refusing "accepted" with 422
                if json.get("decision") == "accepted":
                    return _Resp(422, {"detail": "no proposed class"})
                return _Resp(201, {"id": 11})
            if url.endswith("/protocol"):
                return _Resp(
                    201,
                    {"id": 7, "status": "draft", "blockers": [], "draft_hash": "d" * 64},
                )
            if url.endswith("/submit"):
                return _Resp(
                    200,
                    {
                        "id": 7,
                        "status": "submitted",
                        "submission": {"event_id": 99, "hash": "h99"},
                    },
                )
            if url.endswith("/demo/token"):
                return _Resp(200, {"access_token": f"tok-{json['username']}"})
            if url.endswith("/approve"):
                return _Resp(200, {"id": 7, "status": "approved"})
            raise AssertionError(f"unexpected POST {url}")

    proto = ds._ensure_approved_protocol(
        _FakeClient(), "http://api", "http://issuer", "r1", {"a": "1"}
    )
    assert proto["status"] == "approved"
    assert ("POST", "http://api/runs/r1/import", None) in calls
    # The seed submits what it just read: the draft hash of the Protocol view.
    assert ("POST", "http://api/protocols/7/submit", {"expected_draft_hash": "d" * 64}) in calls
    assert any(
        m == "POST" and u.endswith("/proposals/2/decisions") and b.get("decision") == "edited"
        for m, u, b in calls
    )


def test_resolve_target_reads_idp_from_ready_file_and_uses_pkce_in_keycloak_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    ds = _load_demo_seed()
    ready = tmp_path / "ready.json"
    ready.write_text(
        json.dumps(
            {
                "run_id": "run-kc-1",
                "api_url": "http://127.0.0.1:8000/",
                "issuer_url": "http://127.0.0.1:8080/realms/traceq/",
                "idp": "keycloak",
                "role_claim": "realm_access.roles",
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        ready_file=ready,
        api_url=None,
        issuer_url=None,
        idp=None,
        run_id=None,
        review_package=False,
    )
    api_url, issuer_url, run_id, idp = ds._resolve_target(args, None)
    assert api_url == "http://127.0.0.1:8000"
    assert issuer_url == "http://127.0.0.1:8080/realms/traceq"
    assert run_id == "run-kc-1"
    assert idp == "keycloak"

    called: list[tuple[str, str]] = []

    def _fake_pkce(issuer: str, username: str) -> str:
        called.append((issuer, username))
        return f"pkce-{username}"

    monkeypatch.setattr(ds, "keycloak_pkce_token", _fake_pkce)
    headers = ds._token(None, issuer_url, "dewi", idp="keycloak")
    assert headers == {"Authorization": "Bearer pkce-dewi"}
    assert called == [("http://127.0.0.1:8080/realms/traceq", "dewi")]


# --- Protocol with rows blocked by acceptance_not_shaped (issue #353) -------------------------


class _FakeResp:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> Any:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _proposal(proposal_id: int, kind: str) -> dict[str, Any]:
    return {
        "id": proposal_id,
        "kind": kind,
        "requirement": None,
        "position": None,
        "content_hash": "c" * 64,
        "state": "decided",
        "decisions": [],
        "previous": None,
        "previous_class": None,
    }


def _row(
    requirement: str, text: str, acceptance: dict[str, Any] | None, proposal_id: int
) -> dict[str, Any]:
    """A Test Step row as ``ProtocolRowView`` has it: an accepted draft with ``acceptance``."""
    shaped = acceptance is not None and acceptance.get("type") != "text"
    return {
        "requirement": requirement,
        "text": text,
        "source": {"doc": "URS", "rev": 1, "page": 1, "quote": text},
        "coverage": _proposal(proposal_id + 100, "coverage"),
        "decided_class": "site_only",
        "kind": "test_step",
        "evidence": [],
        "test_step": {
            "origin": "accepted_draft",
            "proposal_id": proposal_id,
            "version": None,
            "description": f"Check {requirement}",
            "method": "Measure on site",
            "instrument": "Tachometer",
            "acceptance": acceptance,
            "acceptance_flag": None,
        },
        "drafts": [],
        "written": [],
        "prefill": None,
        "blockers": [] if shaped else ["acceptance_not_shaped"],
    }


def _view(rows: list[dict[str, Any]], status: str = "draft") -> dict[str, Any]:
    """A Protocol view built through the real response model, so a shape drift fails here."""
    from traceq.assembly.api import ProtocolView

    blocked = [r["requirement"] for r in rows if r["blockers"]]
    view = {
        "id": 7,
        "equipment": "TP-201",
        "run_id": "r1",
        "status": status,
        "events": [],
        "rows": rows,
        "urs": [],
        "checklist": [
            {
                "check": "acceptance_not_shaped",
                "count": len(blocked),
                "requirements": blocked,
                "numbers": [],
            }
        ],
        "draft_hash": None if blocked else "d" * 64,
        "submission": None,
        "submissions": [],
    }
    return ProtocolView.model_validate(view).model_dump(mode="json")


class _SeedClient:
    """A fake API holding one Protocol with rows, behaving like the routes it stands for."""

    def __init__(self, rows: list[dict[str, Any]], submit_status: int = 200) -> None:
        self.rows = rows
        self.submit_status = submit_status
        self.posts: list[tuple[str, Any]] = []

    def get(self, url: str, headers: Any = None) -> _FakeResp:
        if url.endswith("/proposals"):
            return _FakeResp(200, [])
        if url.endswith("/protocol"):
            return _FakeResp(200, _view(self.rows))
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, headers: Any = None, json: Any = None) -> _FakeResp:
        self.posts.append((url, json))
        if url.endswith("/import"):
            return _FakeResp(200, {"run_id": "r1", "already_imported": False})
        if url.endswith("/decisions"):
            return _FakeResp(201, {"id": 1})
        if "/drafts/" in url and url.endswith("/edit"):
            from traceq.assembly.api import DraftEdit

            body = DraftEdit.model_validate(json)
            proposal_id = int(url.split("/drafts/")[1].split("/")[0])
            for i, row in enumerate(self.rows):
                if row["test_step"]["proposal_id"] == proposal_id:
                    self.rows[i] = _row(
                        row["requirement"],
                        row["text"],
                        body.test_step.acceptance.model_dump(mode="json"),
                        proposal_id,
                    )
            return _FakeResp(201, _view(self.rows))
        if url.endswith("/submit"):
            if self.submit_status != 200:
                return _FakeResp(
                    self.submit_status, {"detail": "blocked: acceptance_not_shaped (1)"}
                )
            return _FakeResp(
                200,
                {"id": 7, "status": "submitted", "submission": {"event_id": 5, "hash": "h"}},
            )
        if url.endswith("/demo/token"):
            return _FakeResp(200, {"access_token": f"tok-{json['username']}"})
        if url.endswith("/approve"):
            return _FakeResp(200, {"id": 7, "status": "approved"})
        raise AssertionError(f"unexpected POST {url}")


def test_demo_acceptance_reads_range_from_requirement_text_else_present() -> None:
    from traceq.assembly.written import WrittenContent

    ds = _load_demo_seed()
    texts = {
        "Speed shall be 20–70 rpm.": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        "Speed shall be 20-70 rpm": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        "The panel shall show an alarm.": {"type": "present"},
    }
    for text, expected in texts.items():
        got = ds._demo_acceptance(text)
        assert got == expected
        WrittenContent.model_validate(
            {"description": "d", "method": "m", "instrument": None, "acceptance": got}
        )


def test_blocked_rows_are_rejected_then_edited_with_a_shaped_acceptance_then_submitted() -> None:
    ds = _load_demo_seed()
    rows = [
        _row("URS-1", "Speed shall be 20–70 rpm.", None, 11),
        _row("URS-2", "An alarm shall sound.", {"type": "text", "value": "see manual"}, 12),
        _row("URS-3", "Done already.", {"type": "present", "value": None}, 13),
    ]
    client = _SeedClient(rows)
    proto = ds._ensure_approved_protocol(client, "http://api", "http://iss", "r1", {"a": "1"})
    assert proto["status"] == "approved"

    urls = [u for u, _ in client.posts]
    # Only the blocked rows are touched; each is rejected before it is edited.
    assert not any("/drafts/13/" in u or "/proposals/13/" in u for u in urls)
    for pid in (11, 12):
        reject = urls.index(f"http://api/runs/r1/proposals/{pid}/decisions")
        edit = urls.index(f"http://api/protocols/7/drafts/{pid}/edit")
        assert reject < edit
    edits = {u: b for u, b in client.posts if u.endswith("/edit")}
    first = edits["http://api/protocols/7/drafts/11/edit"]
    assert first["test_step"]["acceptance"]["type"] == "range"
    assert first["reason"].startswith("Demo seed")
    assert edits["http://api/protocols/7/drafts/12/edit"]["test_step"]["acceptance"] == {
        "type": "present"
    }
    # The draft hash read after the edits is the one submitted.
    assert ("http://api/protocols/7/submit", {"expected_draft_hash": "d" * 64}) in client.posts


def _candidate(proposal_id: int, decision: str | None) -> dict[str, Any]:
    """The part of a ``RowCandidate`` the seed reads: its Proposal and that Proposal's state."""
    return {
        "proposal": {
            "id": proposal_id,
            "state": "undecided" if decision is None else "decided",
            "decisions": [] if decision is None else [{"decision": decision}],
        }
    }


class _OneStepClient(_SeedClient):
    """Refuses an edit while another draft step of the row is accepted, as the API does."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(rows)
        self.candidates = [
            _candidate(105, "accepted"),
            _candidate(106, "accepted"),
            _candidate(107, "rejected"),
        ]
        self.accepted = {105, 106}

    def get(self, url: str, headers: Any = None) -> _FakeResp:
        resp = super().get(url, headers)
        if url.endswith("/protocol"):
            body = resp.json()
            for row in body["rows"]:
                row["candidates"] = self.candidates
            return _FakeResp(200, body)
        return resp

    def post(self, url: str, headers: Any = None, json: Any = None) -> _FakeResp:
        if url.endswith("/decisions") and url.split("/proposals/")[1].split("/")[0].isdigit():
            pid = int(url.split("/proposals/")[1].split("/")[0])
            if json["decision"] == "rejected":
                self.accepted.discard(pid)
        if "/drafts/" in url and url.endswith("/edit"):
            pid = int(url.split("/drafts/")[1].split("/")[0])
            if self.accepted - {pid}:
                return _FakeResp(409, {"detail": "another drafted Test Step is accepted"})
        return super().post(url, headers, json)


def test_every_other_accepted_draft_step_of_a_blocked_row_is_rejected_before_the_edit() -> None:
    ds = _load_demo_seed()
    row = _row("URS-1", "Speed shall be 20-70 rpm.", None, 105)
    client = _OneStepClient([row])
    proto = ds._ensure_approved_protocol(client, "http://api", "http://iss", "r1", {"a": "1"})
    assert proto["status"] == "approved"
    urls = [u for u, _ in client.posts]
    assert "http://api/runs/r1/proposals/106/decisions" in urls
    assert "http://api/runs/r1/proposals/107/decisions" not in urls


def test_unblocked_protocol_is_not_edited_again() -> None:
    ds = _load_demo_seed()
    client = _SeedClient([_row("URS-1", "x", {"type": "present", "value": None}, 11)])
    ds._ensure_approved_protocol(client, "http://api", "http://iss", "r1", {"a": "1"})
    assert not any(u.endswith("/edit") for u, _ in client.posts)


def test_a_409_on_submit_surfaces_its_detail() -> None:
    ds = _load_demo_seed()
    client = _SeedClient([_row("URS-1", "x", {"type": "present", "value": None}, 11)], 409)
    with pytest.raises(RuntimeError, match=r"409.*acceptance_not_shaped"):
        ds._ensure_approved_protocol(client, "http://api", "http://iss", "r1", {"a": "1"})


def test_a_blocked_row_that_cannot_be_edited_names_the_row() -> None:
    ds = _load_demo_seed()
    row = _row("URS-1", "x", None, 11)
    row["test_step"]["origin"] = "written"
    client = _SeedClient([row])
    with pytest.raises(RuntimeError, match="URS-1"):
        ds._ensure_approved_protocol(client, "http://api", "http://iss", "r1", {"a": "1"})


def test_keycloak_defaults_the_issuer_url_and_demo_keeps_its_own() -> None:
    import argparse

    ds = _load_demo_seed()

    def _args(idp: str | None) -> argparse.Namespace:
        return argparse.Namespace(
            ready_file=None,
            api_url=None,
            issuer_url=None,
            idp=idp,
            run_id="r1",
            review_package=False,
        )

    api, issuer, _, idp = ds._resolve_target(_args("keycloak"), None)
    assert (api, issuer, idp) == (
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080/realms/traceq",
        "keycloak",
    )
    api, issuer, _, idp = ds._resolve_target(_args(None), None)
    assert (issuer, idp) == ("http://127.0.0.1:9000", "demo")


# --- two-rounds: the older run is round 1 (issue #365) ---------------------------------------


class _RunsClient:
    def __init__(self, runs: list[dict[str, Any]]) -> None:
        self._runs = runs

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        assert url.endswith("/runs")
        assert kwargs["headers"] == {"Authorization": "Bearer tok-ayu"}  # runs need a token
        return _FakeResp(200, self._runs)

    def post(self, url: str, json: Any = None, **_: Any) -> _FakeResp:
        assert url.endswith("/demo/token")
        return _FakeResp(200, {"access_token": f"tok-{json['username']}"})


def _two_rounds_args(**over: Any) -> Any:
    import argparse

    base: dict[str, Any] = {
        "stage": "two-rounds",
        "ready_file": None,
        "api_url": None,
        "issuer_url": None,
        "idp": None,
        "run_id": None,
        "second_run_id": None,
        "review_package": False,
    }
    return argparse.Namespace(**{**base, **over})


def test_two_rounds_takes_the_older_run_as_round_1_and_the_newer_as_round_2() -> None:
    ds = _load_demo_seed()
    # The API lists newest first.
    client = _RunsClient(
        [
            {"run_id": "run-new", "created": "2026-11-26T10:00:00+00:00"},
            {"run_id": "run-old", "created": "2026-11-25T10:00:00+00:00"},
        ]
    )
    args = _two_rounds_args()
    _, _, run_id, _ = ds._resolve_target(args, client)
    assert run_id == "run-old"
    assert args.second_run_id == "run-new"


def test_two_rounds_explicit_ids_are_left_alone() -> None:
    ds = _load_demo_seed()
    args = _two_rounds_args(run_id="a", second_run_id="b")
    _, _, run_id, _ = ds._resolve_target(args, _RunsClient([]))
    assert (run_id, args.second_run_id) == ("a", "b")


def test_two_rounds_with_a_single_run_names_the_runbook_command() -> None:
    ds = _load_demo_seed()
    client = _RunsClient([{"run_id": "only", "created": "2026-11-25T10:00:00+00:00"}])
    with pytest.raises(RuntimeError, match=r"section 13.*traceq run"):
        ds._resolve_target(_two_rounds_args(), client)


# --- ExclusiveRange and ToleranceBand passing values (K84, S4a3) ----------------------------


def test_passing_value_handles_exclusive_range_and_tolerance() -> None:
    from traceq.execution.results import judge
    from traceq.traceability.values import ExclusiveRange, ToleranceBand

    ds = _load_demo_seed()
    cases: list[tuple[dict[str, Any], float, Any]] = [
        (
            {
                "type": "exclusive_range",
                "min": 10.0,
                "max": 20.0,
                "min_exclusive": True,
                "max_exclusive": True,
                "unit": "kN",
            },
            15.0,
            ExclusiveRange(min=10.0, max=20.0, min_exclusive=True, max_exclusive=True, unit="kN"),
        ),
        (
            {
                "type": "exclusive_range",
                "min": 5.0,
                "max": None,
                "min_exclusive": True,
                "max_exclusive": False,
                "unit": "bar",
            },
            6.0,
            ExclusiveRange(min=5.0, max=None, min_exclusive=True, max_exclusive=False, unit="bar"),
        ),
        (
            {
                "type": "exclusive_range",
                "min": None,
                "max": 0.8,
                "min_exclusive": False,
                "max_exclusive": True,
                "unit": "µm",
            },
            0.4,
            ExclusiveRange(min=None, max=0.8, min_exclusive=False, max_exclusive=True, unit="µm"),
        ),
        (
            {
                "type": "exclusive_range",
                "min": None,
                "max": -2.0,
                "min_exclusive": False,
                "max_exclusive": True,
                "unit": "°C",
            },
            -3.0,
            ExclusiveRange(min=None, max=-2.0, min_exclusive=False, max_exclusive=True, unit="°C"),
        ),
        (
            {
                "type": "tolerance",
                "nominal": 380.0,
                "tolerance": 10.0,
                "tolerance_unit": "%",
                "unit": "V",
            },
            380.0,
            ToleranceBand(nominal=380.0, tolerance=10.0, tolerance_unit="%", unit="V"),
        ),
    ]
    for acc_dict, expected_num, acc_model in cases:
        val = ds._passing_value(acc_dict)
        assert val == {"type": "number", "value": expected_num}
        req = RecordAttemptRequest(outcome_kind="value", value=val)
        assert judge(acc_model, req) == "pass"


# --- Draft-aware protocol seeding (#439, #456) ----------------------------------------------


class _DraftProtocolClient:
    """Simulates a Protocol started from a Protocol Draft across every blocker kind."""

    def __init__(self, *, latest_draft_rev: int = 0) -> None:
        self.latest_draft_rev = latest_draft_rev
        self.calls: list[tuple[str, str, Any]] = []
        self.status = "draft"
        self.mapped: dict[str, str] = {}
        self.rejected_steps: set[int] = set()
        self.accepted_steps: set[int] = set()
        self.accepted_criteria: set[int] = set()
        self.edited_steps: dict[int, dict[str, Any]] = {}
        self.written_steps: dict[str, dict[str, Any]] = {}
        self.finding_accepted = False
        self.finding_reasons: list[str] = []
        self.stages: dict[str, str] = {}
        self.missed_disposed = False

    def _proto(self) -> dict[str, Any]:
        # Rows:
        # 1) URS-1: draft candidate OQ-02 (with finding + acceptance_not_shaped -> edited/reason)
        # 2) URS-2: mapped OQ-26 (accepted cleanly) + competing OQ-27 mapped to URS-2
        # 3) URS-3: TraceQ-written (no candidates, no drafts -> written via /test-steps/URS-3)
        # 4) URS-4: vendor_reference (no step or stage needed)
        oq26_mapped = self.mapped.get("OQ-26") == "URS-2"
        oq40_resolved = 104 in self.rejected_steps
        unresolved = []
        if not oq26_mapped:
            unresolved.append("OQ-26")
        if not oq40_resolved:
            unresolved.append("OQ-40")

        r1_written = 101 in self.edited_steps
        r1_blockers: list[str] = []
        if not self.finding_accepted:
            r1_blockers.append("finding_undecided")
        elif not r1_written and not self.finding_reasons:
            r1_blockers.append("finding_reason_missing")
        if not r1_written and not (101 in self.accepted_steps and 201 in self.accepted_criteria):
            r1_blockers.append("draft_undecided")
            r1_blockers.append("no_test_step")
        if "URS-1" not in self.stages:
            r1_blockers.append("stage_missing")

        r2_cand_ready = (102 in self.accepted_steps and 202 in self.accepted_criteria) and (
            103 in self.rejected_steps
        )
        r2_has_step = 102 in self.accepted_steps and 202 in self.accepted_criteria
        r2_blockers: list[str] = []
        if oq26_mapped and not r2_cand_ready:
            r2_blockers.append("draft_undecided")
        if not r2_has_step:
            r2_blockers.append("no_test_step")
        if r2_has_step and "URS-2" not in self.stages:
            r2_blockers.append("stage_missing")

        r3_has_step = "URS-3" in self.written_steps
        r3_blockers: list[str] = []
        if not r3_has_step:
            r3_blockers.append("no_test_step")
        elif "URS-3" not in self.stages:
            r3_blockers.append("stage_missing")

        rows = [
            {
                "requirement": "URS-1",
                "text": "Speed shall be 20-70 rpm.",
                "kind": "test_step",
                "decided_class": "partial",
                "step_source": "draft" if (r1_written or 101 in self.accepted_steps) else None,
                "stage": self.stages.get("URS-1"),
                "witness_required": False,
                "test_step": (
                    {
                        "origin": "written",
                        "proposal_id": 101,
                        "version": 1,
                        **self.edited_steps[101],
                    }
                    if r1_written
                    else None
                ),
                "drafts": [],
                "written": [],
                "prefill": None,
                "candidates": [
                    {
                        "step": {
                            "id": "OQ-02",
                            "description": "Check speed",
                            "method": "Measure",
                            "instrument": "Tach",
                            "not_read": None,
                        },
                        "proposal": {"id": 101, "state": "undecided", "decisions": []},
                        "criterion": None,
                        "criterion_proposal": None,
                        "mapping": None,
                        "ready": r1_written,
                        "accepted": False,
                    }
                ],
                "findings": [
                    {
                        "finding": {"type": "ac_deviates_from_urs", "requirement": "URS-1"},
                        "proposal": {
                            "id": 301,
                            "state": "decided" if self.finding_accepted else "undecided",
                            "decisions": [{"decision": "accepted", "at": "2026-11-28T00:00:00Z"}]
                            if self.finding_accepted
                            else [],
                        },
                        "reasons": [
                            {"version": i + 1, "reason": r, "at": "2026-11-28T00:01:00Z"}
                            for i, r in enumerate(self.finding_reasons)
                        ],
                    }
                ],
                "blockers": r1_blockers,
            },
            {
                "requirement": "URS-2",
                "text": "Surface roughness < 0.8 um.",
                "kind": "test_step",
                "decided_class": "site_only",
                "step_source": "draft" if r2_has_step else None,
                "stage": self.stages.get("URS-2"),
                "witness_required": False,
                "test_step": (
                    {
                        "origin": "accepted_draft",
                        "proposal_id": 102,
                        "version": None,
                        "description": "Check Ra",
                        "method": "Profilometer",
                        "instrument": "P-1",
                        "acceptance": {
                            "type": "exclusive_range",
                            "min": None,
                            "max": 0.8,
                            "min_exclusive": False,
                            "max_exclusive": True,
                            "unit": "um",
                        },
                    }
                    if r2_has_step
                    else None
                ),
                "drafts": [],
                "written": [],
                "prefill": None,
                "candidates": (
                    [
                        {
                            "step": {
                                "id": "OQ-26",
                                "description": "Check Ra",
                                "method": "Profilometer",
                                "instrument": "P-1",
                                "not_read": None,
                            },
                            "proposal": {
                                "id": 102,
                                "state": "decided" if 102 in self.accepted_steps else "undecided",
                                "decisions": (
                                    [{"decision": "accepted", "at": "2026-11-28T00:00:00Z"}]
                                    if 102 in self.accepted_steps
                                    else []
                                ),
                            },
                            "criterion": {"printed": "< 0.8 um", "value": {"type": "range"}},
                            "criterion_proposal": {
                                "id": 202,
                                "state": (
                                    "decided" if 202 in self.accepted_criteria else "undecided"
                                ),
                                "decisions": [],
                            },
                            "mapping": {"requirement": "URS-2", "at": "2026-11-28T00:00:00Z"},
                            "ready": 102 in self.accepted_steps and 202 in self.accepted_criteria,
                            "accepted": r2_has_step,
                        },
                        {
                            "step": {
                                "id": "OQ-27",
                                "description": "Duplicate Ra",
                                "method": "Profilometer",
                                "instrument": None,
                                "not_read": None,
                            },
                            "proposal": {
                                "id": 103,
                                "state": "decided" if 103 in self.rejected_steps else "undecided",
                                "decisions": [],
                            },
                            "criterion": None,
                            "criterion_proposal": None,
                            "mapping": None,
                            "ready": 103 in self.rejected_steps,
                            "accepted": False,
                        },
                    ]
                    if oq26_mapped
                    else []
                ),
                "findings": [],
                "blockers": r2_blockers,
            },
            {
                "requirement": "URS-3",
                "text": "Panel alarm shall sound.",
                "kind": "test_step",
                "decided_class": "gap",
                "step_source": "traceq_written" if r3_has_step else None,
                "stage": self.stages.get("URS-3"),
                "witness_required": False,
                "test_step": (
                    {
                        "origin": "written",
                        "proposal_id": None,
                        "version": 1,
                        **self.written_steps["URS-3"],
                    }
                    if r3_has_step
                    else None
                ),
                "drafts": [],
                "written": [],
                "prefill": None,
                "candidates": [],
                "findings": [],
                "blockers": r3_blockers,
            },
            {
                "requirement": "URS-4",
                "text": "Material SS316L.",
                "kind": "vendor_reference",
                "decided_class": "covered_by_vendor",
                "step_source": None,
                "stage": None,
                "witness_required": False,
                "test_step": None,
                "drafts": [],
                "written": [],
                "prefill": None,
                "candidates": [],
                "findings": [],
                "blockers": [],
            },
        ]
        all_blocked = (
            any(r["blockers"] for r in rows) or bool(unresolved) or not self.missed_disposed
        )
        return {
            "id": 42,
            "equipment": "TP-201",
            "run_id": "run-draft-1",
            "status": self.status,
            "source": {"doc": "OQ-TP201", "rev": 0, "sha256": "0a" * 32},
            "latest_draft_rev": self.latest_draft_rev,
            "draft_steps": [
                {
                    "step": {
                        "id": "OQ-26",
                        "mapped_to": ["URS-2", "URS-3"],
                        "requirements": ["URS-2"],
                        "description": "Check Ra",
                        "method": "Profilometer",
                        "not_read": None,
                    },
                    "proposal": {"id": 102, "state": "undecided", "decisions": []},
                    "requirement": "URS-2" if oq26_mapped else None,
                    "resolved": oq26_mapped,
                },
                {
                    "step": {
                        "id": "OQ-40",
                        "mapped_to": [],
                        "requirements": [],
                        "description": None,
                        "method": None,
                        "not_read": "dropped",
                    },
                    "proposal": {"id": 104, "state": "undecided", "decisions": []},
                    "requirement": None,
                    "resolved": oq40_resolved,
                },
            ],
            "rows": rows,
            "urs": [
                {
                    "doc": "URS-TP201",
                    "rev": 0,
                    "numbers": "checked",
                    "missed": [
                        {
                            "number": "3.1",
                            "page": 2,
                            "blocking": not self.missed_disposed,
                        }
                    ],
                }
            ],
            "checklist": [
                {
                    "check": "draft_step_unresolved",
                    "count": len(unresolved),
                    "requirements": [],
                    "numbers": [],
                    "steps": unresolved,
                }
            ],
            "draft_hash": None if all_blocked else "f" * 64,
            "submission": (
                {"event_id": 88, "hash": "s" * 64}
                if self.status in ("submitted", "approved")
                else None
            ),
        }

    def get(self, url: str, headers: Any = None) -> _FakeResp:
        self.calls.append(("GET", url, None))
        if url.endswith("/proposals"):
            return _FakeResp(
                200,
                [
                    {"id": 1, "kind": "coverage", "state": "undecided"},
                    {"id": 301, "kind": "draft", "state": "undecided"},
                    {"id": 501, "kind": "test_step", "state": "undecided"},
                    {"id": 102, "kind": "draft_step", "state": "undecided"},
                ],
            )
        if url.endswith("/protocol"):
            return _FakeResp(200, self._proto())
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, headers: Any = None, json: Any = None) -> _FakeResp:
        self.calls.append(("POST", url, json))
        if url.endswith("/import"):
            return _FakeResp(200, {"run_id": "run-draft-1", "already_imported": False})
        if "/proposals/" in url and url.endswith("/decisions"):
            pid = int(url.split("/proposals/")[1].split("/")[0])
            if pid in (501,):
                raise AssertionError("from_draft must NOT blindly decide test_step proposals")
            if pid == 301 and json["decision"] == "accepted":
                self.finding_accepted = True
            if pid == 102 and json["decision"] == "accepted":
                if 103 in self.accepted_steps:
                    return _FakeResp(409, {"detail": "another draft Test Step is accepted"})
                self.accepted_steps.add(102)
            if pid == 202 and json["decision"] == "accepted":
                self.accepted_criteria.add(202)
            if pid in (103, 104) and json["decision"] == "rejected":
                self.rejected_steps.add(pid)
            return _FakeResp(201, {"id": pid * 10})
        if "/drafts/" in url and url.endswith("/edit"):
            pid = int(url.split("/drafts/")[1].split("/")[0])
            self.edited_steps[pid] = json["test_step"]
            return _FakeResp(201, self._proto())
        if "/test-steps/" in url:
            req = url.split("/test-steps/")[1]
            self.written_steps[req] = json["test_step"]
            return _FakeResp(201, self._proto())
        if url.endswith("/missed-numbers"):
            self.missed_disposed = True
            return _FakeResp(201, self._proto())
        if url.endswith("/submit"):
            proto = self._proto()
            assert proto["draft_hash"] is not None, proto
            assert json["expected_draft_hash"] == proto["draft_hash"]
            assert json["expected_latest_draft_rev"] == self.latest_draft_rev
            self.status = "submitted"
            return _FakeResp(200, self._proto())
        if url.endswith("/demo/token"):
            return _FakeResp(200, {"access_token": f"tok-{json['username']}"})
        if url.endswith("/approve"):
            assert json["expected_latest_draft_rev"] == self.latest_draft_rev
            self.status = "approved"
            return _FakeResp(200, self._proto())
        raise AssertionError(f"unexpected POST {url}")

    def put(self, url: str, headers: Any = None, json: Any = None) -> _FakeResp:
        self.calls.append(("PUT", url, json))
        if "/draft-steps/" in url and url.endswith("/mapping"):
            step = url.split("/draft-steps/")[1].split("/")[0]
            self.mapped[step] = json["requirement"]
            return _FakeResp(200, self._proto())
        if "/rows/" in url and url.endswith("/attributes"):
            req = url.split("/rows/")[1].split("/")[0]
            self.stages[req] = json["stage"]
            return _FakeResp(200, self._proto())
        raise AssertionError(f"unexpected PUT {url}")


def test_from_draft_resolves_all_blockers_without_409_and_passes_latest_rev() -> None:
    ds = _load_demo_seed()
    client = _DraftProtocolClient(latest_draft_rev=0)
    proto = ds._ensure_approved_protocol(
        client, "http://api", "http://iss", "run-draft-1", {"a": "1"}, from_draft=True
    )
    assert proto["status"] == "approved"
    assert client.mapped["OQ-26"] == "URS-2"
    assert 104 in client.rejected_steps
    assert 103 in client.rejected_steps
    assert 102 in client.accepted_steps and 202 in client.accepted_criteria
    assert 101 in client.edited_steps
    assert "URS-3" in client.written_steps
    assert client.stages["URS-1"] == "OQ"
    assert client.stages["URS-2"] == "OQ"
    assert client.stages["URS-3"] == "IQ"
    assert "URS-4" not in client.stages
    assert client.missed_disposed is True
    # Only coverage and draft (finding) proposals were decided upfront.
    upfront_decision_urls = [
        u
        for m, u, _ in client.calls
        if m == "POST" and "/proposals/" in u and u.endswith("/decisions")
    ]
    assert "http://api/runs/run-draft-1/proposals/501/decisions" not in upfront_decision_urls


def test_from_draft_writes_finding_reason_when_row_unchanged() -> None:
    ds = _load_demo_seed()
    client = _DraftProtocolClient(latest_draft_rev=0)
    # Pre-accept OQ-02 with a shaped criterion so row URS-1 stays unchanged (needs reason).
    orig_proto = client._proto

    def _unchanged_proto() -> dict[str, Any]:
        p = orig_proto()
        r1 = p["rows"][0]
        r1["test_step"] = {
            "origin": "accepted_draft",
            "proposal_id": 101,
            "version": None,
            "description": "Check speed",
            "method": "Measure",
            "instrument": "Tach",
            "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        }
        r1["step_source"] = "draft"
        r1["candidates"][0]["ready"] = True
        r1["candidates"][0]["accepted"] = True
        finding_b = (
            ["finding_undecided"]
            if not client.finding_accepted
            else ([] if client.finding_reasons else ["finding_reason_missing"])
        )
        r1["blockers"] = finding_b + (["stage_missing"] if "URS-1" not in client.stages else [])
        p["draft_hash"] = (
            None
            if any(r["blockers"] for r in p["rows"])
            or any(not d["resolved"] for d in p["draft_steps"])
            or not client.missed_disposed
            else "f" * 64
        )
        return p

    client._proto = _unchanged_proto  # type: ignore[method-assign]
    orig_post = client.post

    def _post_with_reason(url: str, headers: Any = None, json: Any = None) -> _FakeResp:
        if "/findings/" in url and url.endswith("/reason"):
            client.calls.append(("POST", url, json))
            client.finding_reasons.append(json["reason"])
            return _FakeResp(201, client._proto())
        return orig_post(url, headers=headers, json=json)

    client.post = _post_with_reason  # type: ignore[method-assign]
    proto = ds._ensure_approved_protocol(
        client, "http://api", "http://iss", "run-draft-1", {"a": "1"}, from_draft=True
    )
    assert proto["status"] == "approved"
    assert len(client.finding_reasons) == 1


def test_upload_draft_pdf_polls_until_succeeded_and_stale_pin_stops_at_submitted(
    tmp_path: Path,
) -> None:
    ds = _load_demo_seed()
    rev0 = tmp_path / "rev0.pdf"
    rev1 = tmp_path / "rev1.pdf"
    rev0.write_bytes(b"%PDF-1.4 rev0")
    rev1.write_bytes(b"%PDF-1.4 rev1")

    class _StalePinClient(_DraftProtocolClient):
        def __init__(self) -> None:
            super().__init__(latest_draft_rev=0)
            self.polls = 0

        def get(self, url: str, headers: Any = None) -> _FakeResp:
            if url == "http://api/uploads/10":
                self.polls += 1
                if self.polls == 1:
                    return _FakeResp(200, {"id": 10, "status": "running", "run_id": None})
                return _FakeResp(200, {"id": 10, "status": "succeeded", "run_id": "run-rev0"})
            if url == "http://api/uploads/11":
                self.latest_draft_rev = 1
                return _FakeResp(200, {"id": 11, "status": "succeeded", "run_id": "run-rev1"})
            return super().get(url, headers)

        def post(
            self, url: str, headers: Any = None, json: Any = None, content: bytes | None = None
        ) -> _FakeResp:
            if url == "http://api/equipment/TP-201/drafts":
                self.calls.append(("POST", url, len(content or b"")))
                assert headers is not None and headers.get("Content-Type") == "application/pdf"
                job_id = 10 if content == b"%PDF-1.4 rev0" else 11
                return _FakeResp(202, {"id": job_id, "status": "queued", "run_id": None})
            return super().post(url, headers=headers, json=json)

    client = _StalePinClient()
    summary = ds._run_stale_pin(
        client,
        "http://api",
        "http://iss",
        "TP-201",
        rev0,
        rev1,
        {"Authorization": "Bearer tok-ayu"},
        idp="demo",
    )
    assert summary == {
        "stage": "stale-pin",
        "equipment": "TP-201",
        "rev0_run_id": "run-rev0",
        "rev1_run_id": "run-rev1",
        "protocol_id": 42,
        "protocol_status": "submitted",
        "pinned_rev": 0,
        "latest_rev": 1,
    }
    assert not any(m == "POST" and u.endswith("/approve") for m, u, _ in client.calls)


def test_upload_draft_pdf_raises_on_failed_job_and_handles_409_duplicate(
    tmp_path: Path,
) -> None:
    ds = _load_demo_seed()
    pdf = tmp_path / "draft.pdf"
    pdf.write_bytes(b"%PDF-1.4 duplicate")
    import hashlib

    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()

    class _DupClient:
        def post(self, url: str, headers: Any = None, content: bytes | None = None) -> _FakeResp:
            return _FakeResp(409, {"detail": "duplicate"})

        def get(self, url: str, headers: Any = None) -> _FakeResp:
            if url.endswith("/drafts"):
                return _FakeResp(
                    200,
                    {"jobs": [{"id": 9, "sha256": sha, "status": "succeeded", "run_id": "r-dup"}]},
                )
            raise AssertionError(f"unexpected GET {url}")

    assert ds._upload_draft_pdf(_DupClient(), "http://api", "TP-201", pdf, {"a": "1"}) == "r-dup"

    class _FailClient:
        def post(self, url: str, headers: Any = None, content: bytes | None = None) -> _FakeResp:
            return _FakeResp(202, {"id": 12, "status": "queued", "run_id": None})

        def get(self, url: str, headers: Any = None) -> _FakeResp:
            return _FakeResp(200, {"id": 12, "status": "failed", "message": "not recorded"})

    with pytest.raises(RuntimeError, match=r"Upload job 12.*failed: not recorded"):
        ds._upload_draft_pdf(_FailClient(), "http://api", "TP-201", pdf, {"a": "1"})


def test_has_review_package_detects_review_package_runs() -> None:
    ds = _load_demo_seed()

    class _RunClient:
        def __init__(self, rp: Any) -> None:
            self.rp = rp

        def get(self, url: str, headers: Any = None) -> _FakeResp:
            assert url == "http://api/runs/run-1"
            return _FakeResp(200, {"run_id": "run-1", "review_package": self.rp})

    rp_client = _RunClient({"doc_id": "OQ-TP201"})
    assert ds._has_review_package(rp_client, "http://api", "run-1", {}) is True
    assert ds._has_review_package(_RunClient(None), "http://api", "run-1", {}) is False
