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
