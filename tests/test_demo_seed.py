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
