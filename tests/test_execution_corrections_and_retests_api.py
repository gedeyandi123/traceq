"""Corrections and Retests on Execution attempts over HTTP with a real Postgres and the demo
issuer (ADR 0013, spec #270, #277).
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import Databases, DemoIssuer
from fastapi.testclient import TestClient
from test_missed_numbers_api import COMPLETENESS
from test_proposals_api import RUN_ID, bearer, configured, import_run, token
from test_protocol_approval_api import persona_token
from test_protocol_submission_api import (
    N003,
    N004,
    R002,
    R026,
    R030,
    STEP,
    decide,
    dispose,
    edit,
    place,
    proposals,
    submit,
    write,
)
from test_test_step_proposals import add_drafted_run

from traceq.audit import entries
from traceq.db import engine, transaction
from traceq.execution.results import database_utc_date

pytestmark = pytest.mark.db


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
def ayu(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Ayu: holds qualification-decider and qualification-executor."""
    return bearer(token(demo_issuer, decider=True))


@pytest.fixture
def bima(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Bima: holds qualification-decider and qualification-executor."""
    return persona_token(demo_issuer, "bima")


@pytest.fixture
def reader(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Citra: holds no roles."""
    return bearer(token(demo_issuer, decider=False))


@pytest.fixture
def approver(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Dewi: holds only qualification-approver."""
    return persona_token(demo_issuer, "dewi")


@pytest.fixture
def witness(demo_issuer: DemoIssuer) -> dict[str, str]:
    """Eko: holds only qualification-witness."""
    return persona_token(demo_issuer, "eko")


def _start_execution(
    client: TestClient,
    ayu: dict[str, str],
    approver: dict[str, str],
    *,
    r026_step: dict[str, Any] | None = None,
    r030_step: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import_run(client, ayu)
    r = client.post(f"/runs/{RUN_ID}/protocol", headers=ayu)
    assert r.status_code == 201, r.text
    draft = r.json()
    ps = proposals(client, ayu)
    decide(
        client,
        ayu,
        place(ps, "coverage", R002),
        decision="edited",
        coverage="covered_by_vendor",
        reason="FAT cukup",
    )
    decide(client, ayu, place(ps, "coverage", R026), decision="accepted")
    decide(
        client,
        ayu,
        place(ps, "coverage", R030),
        decision="edited",
        coverage="gap",
        reason="r",
    )
    write(client, ayu, draft, R026, r026_step or STEP)
    edit(client, ayu, draft, place(ps, "test_step", R030), r030_step or STEP)
    dispose(client, ayu, draft, number=N003)
    dispose(client, ayu, draft, number=N004, kind="not_tested_here")
    submitted = submit(client, ayu, draft)
    sub = submitted["submission"]
    app = client.post(
        f"/protocols/{submitted['id']}/approve",
        headers=approver,
        json={"submission_event_id": sub["event_id"], "hash": sub["hash"]},
    )
    assert app.status_code == 200, app.text
    started = client.post(f"/protocols/{submitted['id']}/execution", headers=ayu)
    assert started.status_code == 201, started.text
    return started.json()


def _row(ex: dict[str, Any], req: str) -> dict[str, Any]:
    return next(r for r in ex["rows"] if r["requirement"] == req)


def _attempt_url(execution_id: int, req: str = R026) -> str:
    return f"/executions/{execution_id}/rows/{req}/attempts"


def _correct_url(execution_id: int, req: str = R026, attempt_number: int = 1) -> str:
    return f"/executions/{execution_id}/rows/{req}/attempts/{attempt_number}/corrections"


def _retest_url(execution_id: int, req: str = R026) -> str:
    return f"/executions/{execution_id}/rows/{req}/retests"


def test_correction_requires_role_ownership_and_reason(
    client: TestClient,
    ayu: dict[str, str],
    bima: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
) -> None:
    ex = _start_execution(
        client,
        ayu,
        approver,
        r026_step={
            "description": "Langkah uji",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        },
    )
    r = client.post(
        _attempt_url(ex["id"], R026),
        headers=ayu,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 45.0}},
    )
    assert r.status_code == 201

    # 403 without qualification-executor
    for h in (reader, approver):
        res = client.post(
            _correct_url(ex["id"]),
            headers=h,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 50.0},
                "reason_for_change": "Typo",
            },
        )
        assert res.status_code == 403

    # 409 when another Performer (bima) tries to correct ayu's attempt
    res_other = client.post(
        _correct_url(ex["id"]),
        headers=bima,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "reason_for_change": "Bima correction",
        },
    )
    assert res_other.status_code == 409

    # 422 when reason_for_change is missing or blank
    for payload in (
        {"outcome_kind": "value", "value": {"type": "number", "value": 50.0}},
        {
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "reason_for_change": "   ",
        },
    ):
        res_bad = client.post(_correct_url(ex["id"]), headers=ayu, json=payload)
        assert res_bad.status_code == 422


def test_correction_automatic_deviations_and_witness_voiding(
    client: TestClient,
    ayu: dict[str, str],
    approver: dict[str, str],
    witness: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(
        client,
        ayu,
        approver,
        r026_step={
            "description": "Langkah uji 1",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        },
        r030_step={
            "description": "Langkah uji 2",
            "method": "Metode",
            "instrument": "TACH-01",
            "acceptance": {"type": "number", "value": 30.0, "unit": "°C"},
        },
    )

    # 1) R026: pass -> Witness confirms -> correct to fail -> opens 1 Deviation & voids Witness
    r1 = client.post(
        _attempt_url(ex["id"], R026),
        headers=ayu,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 45.0}},
    )
    assert r1.status_code == 201
    v1 = _row(r1.json(), R026)["attempts"][0]["latest"]
    w1 = client.post(
        f"/executions/{ex['id']}/rows/{R026}/attempts/1/witness",
        headers=witness,
        json={"version_number": 1, "version_hash": v1["version_hash"]},
    )
    assert w1.status_code == 201

    c1 = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 99.0},
            "reason_for_change": "Salah baca nilai awal",
        },
    )
    assert c1.status_code == 201
    body1 = c1.json()
    attempt_r026 = _row(body1, R026)["attempts"][0]
    assert len(attempt_r026["versions"]) == 2
    assert attempt_r026["versions"][0]["witness_confirmations"][0]["voided"] is True
    assert attempt_r026["latest"]["version"] == 2
    assert attempt_r026["latest"]["verdict"] == "fail"
    assert attempt_r026["latest"]["reason_for_change"] == "Salah baca nilai awal"
    assert len(body1["deviations"]) == 1
    assert body1["deviations"][0]["cause"] == "failed"

    # 2) R026: fail -> another fail opens NO new Deviation
    c2 = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 100.0},
            "reason_for_change": "Koreksi nilai gagal",
        },
    )
    assert c2.status_code == 201
    assert len(c2.json()["deviations"]) == 1

    # 3) R026: fail -> pass leaves existing Deviation Open (never closes/removes it)
    c3 = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "reason_for_change": "Nilai sebenarnya lulus",
        },
    )
    assert c3.status_code == 201
    body3 = c3.json()
    assert _row(body3, R026)["attempts"][0]["latest"]["verdict"] == "pass"
    assert len(body3["deviations"]) == 1
    assert body3["deviations"][0]["status"] == "open"

    # 4) R030: both causes -> correction keeping both opens NO new Deviations
    r2 = client.post(
        _attempt_url(ex["id"], R030),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 10.0},
            "no_calibrated_instrument_reason": "Kalibrator rusak",
        },
    )
    assert r2.status_code == 201
    assert len(r2.json()["deviations"]) == 3  # 1 from R026 + 2 from R030

    c4 = client.post(
        _correct_url(ex["id"], R030, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 12.0},
            "no_calibrated_instrument_reason": "Kalibrator masih rusak",
            "reason_for_change": "Koreksi angka",
        },
    )
    assert c4.status_code == 201
    assert len(c4.json()["deviations"]) == 3

    with transaction(engine(fresh_database.app)) as session:
        audit_actions = [e.action for e in entries(session)]
    assert "attempt corrected" in audit_actions
    assert audit_actions.count("deviation opened") == 3


def test_correction_locked_by_submitted_or_closed_deviation_and_unlocked_after_return(
    client: TestClient,
    demo_issuer: DemoIssuer,
    ayu: dict[str, str],
    bima: dict[str, str],
    approver: dict[str, str],
) -> None:
    ex = _start_execution(
        client,
        ayu,
        approver,
        r026_step={
            "description": "Langkah uji",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "number", "value": 30.0, "unit": "°C"},
        },
    )
    r = client.post(
        _attempt_url(ex["id"], R026),
        headers=ayu,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 25.0}},
    )
    assert r.status_code == 201
    dev_id = r.json()["deviations"][0]["id"]

    # Investigate (by bima so approver can close later) and submit
    inv = client.post(
        f"/executions/{ex['id']}/deviations/{dev_id}/investigations",
        headers=bima,
        json={"investigation": "Akar masalah", "deviation_class": "minor"},
    )
    assert inv.status_code == 201
    sub = client.post(f"/executions/{ex['id']}/deviations/{dev_id}/submit", headers=bima)
    assert sub.status_code == 200
    d_sub = sub.json()["deviations"][0]

    # Refused while Submitted
    blocked_sub = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 30.0},
            "reason_for_change": "Try while submitted",
        },
    )
    assert blocked_sub.status_code == 409

    # Return to Open -> correction accepted
    ret = client.post(
        f"/executions/{ex['id']}/deviations/{dev_id}/return",
        headers=approver,
        json={
            "reason": "Perlu verifikasi ulang",
            "expected_event_id": d_sub["events"][-1]["id"],
            "expected_investigation_version": d_sub["investigations"][-1]["version"],
        },
    )
    assert ret.status_code == 200
    allowed_after_return = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 28.0},
            "reason_for_change": "Sudah diverifikasi",
        },
    )
    assert allowed_after_return.status_code == 201

    # Re-submit and Close -> refused while Closed
    resub = client.post(f"/executions/{ex['id']}/deviations/{dev_id}/submit", headers=bima)
    assert resub.status_code == 200
    d_resub = resub.json()["deviations"][0]
    assert (
        client.post(
            f"/executions/{ex['id']}/deviations/{dev_id}/close",
            headers=persona_token(demo_issuer, "dewi"),
            json={
                "expected_event_id": d_resub["events"][-1]["id"],
                "expected_investigation_version": d_resub["investigations"][-1]["version"],
                "expected_content_hash": d_resub["closure_content_hash"],
            },
        ).status_code
        == 200
    )
    blocked_closed = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 30.0},
            "reason_for_change": "Try while closed",
        },
    )
    assert blocked_closed.status_code == 409


def test_instrument_reference_date_on_correction_vs_retest(
    client: TestClient,
    ayu: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ex = _start_execution(
        client,
        ayu,
        approver,
        r026_step={
            "description": "Langkah uji instrumen",
            "method": "Metode",
            "instrument": "TACH-01",
            "acceptance": {"type": "number", "value": 30.0, "unit": "rpm"},
        },
    )
    with transaction(engine(fresh_database.app)) as session:
        today_utc = database_utc_date(session)

    # Record v1 failing with instrument due today_utc
    r = client.post(
        _attempt_url(ex["id"], R026),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 20.0},
            "instruments": [
                {"identifier": "TACH-01", "calibration_due_date": today_utc.isoformat()}
            ],
        },
    )
    assert r.status_code == 201
    dev_id = r.json()["deviations"][0]["id"]

    # Advance DB UTC date by 1 day for subsequent checks
    tomorrow_utc = today_utc + timedelta(days=1)
    monkeypatch.setattr("traceq.execution.results.database_utc_date", lambda _s: tomorrow_utc)

    # Correction uses v1's UTC date (today_utc), so due date == today_utc is ACCEPTED
    corr = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 25.0},
            "instruments": [
                {"identifier": "TACH-01", "calibration_due_date": today_utc.isoformat()}
            ],
            "reason_for_change": "Koreksi pada hari berikutnya",
        },
    )
    assert corr.status_code == 201

    # Retest uses current DB UTC date (tomorrow_utc), so due date == today_utc is REFUSED (409)
    retest_expired = client.post(
        _retest_url(ex["id"], R026),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 30.0},
            "instruments": [
                {"identifier": "TACH-01", "calibration_due_date": today_utc.isoformat()}
            ],
            "deviation_id": dev_id,
            "retest_reason": "Uji ulang",
        },
    )
    assert retest_expired.status_code == 409


def test_retest_refusals_acceptance_and_completion_frozen_copy(
    client: TestClient,
    demo_issuer: DemoIssuer,
    ayu: dict[str, str],
    bima: dict[str, str],
    reader: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(
        client,
        ayu,
        approver,
        r026_step={
            "description": "Langkah uji 1",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "number", "value": 30.0, "unit": "°C"},
        },
        r030_step={
            "description": "Langkah uji 2",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "number", "value": 50.0, "unit": "°C"},
        },
    )

    # Record R026 failing and R030 passing
    r_fail = client.post(
        _attempt_url(ex["id"], R026),
        headers=ayu,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 10.0}},
    )
    assert r_fail.status_code == 201
    dev_r026 = r_fail.json()["deviations"][0]

    r_pass = client.post(
        _attempt_url(ex["id"], R030),
        headers=ayu,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 50.0}},
    )
    assert r_pass.status_code == 201

    # Open a manual Deviation linked to Execution only (requirement=None)
    m_exec = client.post(
        f"/executions/{ex['id']}/deviations",
        headers=ayu,
        json={"requirement": None, "description": "Deviasi umum eksekusi"},
    )
    assert m_exec.status_code == 201
    dev_exec_only = m_exec.json()["deviations"][-1]

    # Open a manual Deviation linked to R030
    m_r030 = client.post(
        f"/executions/{ex['id']}/deviations",
        headers=ayu,
        json={"requirement": R030, "description": "Deviasi manual R030"},
    )
    assert m_r030.status_code == 201
    dev_r030 = m_r030.json()["deviations"][-1]

    # 403 without executing role
    assert (
        client.post(
            _retest_url(ex["id"], R026),
            headers=reader,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 30.0},
                "deviation_id": dev_r026["id"],
                "retest_reason": "Uji ulang",
            },
        ).status_code
        == 403
    )

    # 422 without retest_reason
    assert (
        client.post(
            _retest_url(ex["id"], R026),
            headers=ayu,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 30.0},
                "deviation_id": dev_r026["id"],
                "retest_reason": "   ",
            },
        ).status_code
        == 422
    )

    # 409 when row latest Result passes (R030)
    assert (
        client.post(
            _retest_url(ex["id"], R030),
            headers=ayu,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 50.0},
                "deviation_id": dev_r030["id"],
                "retest_reason": "Uji ulang padahal lulus",
            },
        ).status_code
        == 409
    )

    # 409 when naming Execution-only manual Deviation
    assert (
        client.post(
            _retest_url(ex["id"], R026),
            headers=ayu,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 30.0},
                "deviation_id": dev_exec_only["id"],
                "retest_reason": "Uji ulang",
            },
        ).status_code
        == 409
    )

    # 409 when naming a Deviation of another Test Step (dev_r030 on R026)
    assert (
        client.post(
            _retest_url(ex["id"], R026),
            headers=ayu,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 30.0},
                "deviation_id": dev_r030["id"],
                "retest_reason": "Uji ulang",
            },
        ).status_code
        == 409
    )

    # 409 when naming a Submitted Deviation
    assert (
        client.post(
            f"/executions/{ex['id']}/deviations/{dev_r026['id']}/investigations",
            headers=bima,
            json={"investigation": "Root cause", "deviation_class": "minor"},
        ).status_code
        == 201
    )
    sub_r026 = client.post(
        f"/executions/{ex['id']}/deviations/{dev_r026['id']}/submit", headers=bima
    )
    assert sub_r026.status_code == 200
    d_r026_sub = next(d for d in sub_r026.json()["deviations"] if d["id"] == dev_r026["id"])
    assert (
        client.post(
            _retest_url(ex["id"], R026),
            headers=ayu,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 30.0},
                "deviation_id": dev_r026["id"],
                "retest_reason": "Uji ulang saat diajukan",
            },
        ).status_code
        == 409
    )

    # Return to Open -> failed Retest opens a new Deviation on attempt 2
    assert (
        client.post(
            f"/executions/{ex['id']}/deviations/{dev_r026['id']}/return",
            headers=approver,
            json={
                "reason": "Perlu uji ulang",
                "expected_event_id": d_r026_sub["events"][-1]["id"],
                "expected_investigation_version": d_r026_sub["investigations"][-1]["version"],
            },
        ).status_code
        == 200
    )
    retest_fail = client.post(
        _retest_url(ex["id"], R026),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 15.0},
            "deviation_number": dev_r026["deviation_number"],
            "retest_reason": "Perbaikan pertama",
        },
    )
    assert retest_fail.status_code == 201
    body_rf = retest_fail.json()
    assert len(_row(body_rf, R026)["attempts"]) == 2
    assert _row(body_rf, R026)["attempts"][1]["attempt_number"] == 2
    assert len(body_rf["deviations"]) == 4  # new automatic Deviation opened for attempt 2
    dev_attempt2 = body_rf["deviations"][-1]

    # Correct attempt 2 once so we also test correction + retest in frozen_copy
    corr2 = client.post(
        _correct_url(ex["id"], R026, 2),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 16.0},
            "reason_for_change": "Koreksi percobaan 2",
        },
    )
    assert corr2.status_code == 201

    # Passing Retest (attempt 3)
    retest_pass = client.post(
        _retest_url(ex["id"], R026),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 30.0},
            "deviation_id": dev_attempt2["id"],
            "retest_reason": "Perbaikan kedua berhasil",
        },
    )
    assert retest_pass.status_code == 201
    assert len(_row(retest_pass.json(), R026)["attempts"]) == 3

    # Close all 4 Deviations and Complete Execution (fresh token per signature)
    for d in retest_pass.json()["deviations"]:
        cur_d = d
        if cur_d["status"] == "open":
            if not cur_d["investigations"]:
                assert (
                    client.post(
                        f"/executions/{ex['id']}/deviations/{cur_d['id']}/investigations",
                        headers=bima,
                        json={"investigation": "Selesai", "deviation_class": "minor"},
                    ).status_code
                    == 201
                )
            sub_d = client.post(
                f"/executions/{ex['id']}/deviations/{cur_d['id']}/submit", headers=bima
            )
            assert sub_d.status_code == 200
            cur_d = next(item for item in sub_d.json()["deviations"] if item["id"] == cur_d["id"])
        assert (
            client.post(
                f"/executions/{ex['id']}/deviations/{cur_d['id']}/close",
                headers=persona_token(demo_issuer, "dewi"),
                json={
                    "expected_event_id": cur_d["events"][-1]["id"],
                    "expected_investigation_version": cur_d["investigations"][-1]["version"],
                    "expected_content_hash": cur_d["closure_content_hash"],
                },
            ).status_code
            == 200
        )

    completed = client.post(f"/executions/{ex['id']}/complete", headers=ayu)
    assert completed.status_code == 200
    comp_body = completed.json()
    frozen_r026 = next(r for r in comp_body["frozen_copy"]["rows"] if r["requirement"] == R026)
    assert [a["attempt_number"] for a in frozen_r026["attempts"]] == [1, 2, 3]
    assert [v["version"] for v in frozen_r026["attempts"][1]["versions"]] == [1, 2]
    assert frozen_r026["attempts"][1]["versions"][1]["reason_for_change"] == "Koreksi percobaan 2"

    # Both correct_attempt and retest_row refuse (409) after completion
    assert (
        client.post(
            _correct_url(ex["id"], R026, 3),
            headers=ayu,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 30.0},
                "reason_for_change": "Post completion",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            _retest_url(ex["id"], R026),
            headers=ayu,
            json={
                "outcome_kind": "value",
                "value": {"type": "number", "value": 30.0},
                "deviation_id": dev_attempt2["id"],
                "retest_reason": "Post completion",
            },
        ).status_code
        == 409
    )

    with transaction(engine(fresh_database.app)) as session:
        audit_actions = [e.action for e in entries(session)]
    assert "attempt retested" in audit_actions


def test_correction_and_retest_audit_trail_and_version_hash_rfc(
    client: TestClient,
    ayu: dict[str, str],
    approver: dict[str, str],
    fresh_database: Databases,
) -> None:
    ex = _start_execution(
        client,
        ayu,
        approver,
        r026_step={
            "description": "Langkah uji",
            "method": "Metode",
            "instrument": None,
            "acceptance": {"type": "range", "min": 20.0, "max": 70.0, "unit": "rpm"},
        },
    )
    att1 = client.post(
        _attempt_url(ex["id"], R026),
        headers=ayu,
        json={"outcome_kind": "value", "value": {"type": "number", "value": 45.0}},
    )
    assert att1.status_code == 201
    v1 = _row(att1.json(), R026)["attempts"][0]["versions"][0]

    # Two corrections with identical measurement values but different reason_for_change
    # must produce different version_hash values.
    corr1 = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 95.0},
            "reason_for_change": "  Salah baca angka pertama  ",
        },
    )
    assert corr1.status_code == 201
    v2 = _row(corr1.json(), R026)["attempts"][0]["versions"][1]

    corr2 = client.post(
        _correct_url(ex["id"], R026, 1),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 95.0},
            "reason_for_change": "Alasan koreksi berbeda",
        },
    )
    assert corr2.status_code == 201
    v3 = _row(corr2.json(), R026)["attempts"][0]["versions"][2]
    assert v2["version_hash"] != v3["version_hash"]

    dev_id = corr2.json()["deviations"][0]["id"]
    retest = client.post(
        _retest_url(ex["id"], R026),
        headers=ayu,
        json={
            "outcome_kind": "value",
            "value": {"type": "number", "value": 50.0},
            "deviation_id": dev_id,
            "retest_reason": "  Uji ulang setelah penyetelan  ",
        },
    )
    assert retest.status_code == 201

    with transaction(engine(fresh_database.app)) as session:
        all_entries = entries(session)

    corr_entry = next(
        e
        for e in all_entries
        if e.action == "attempt corrected"
        and isinstance(e.new_value, dict)
        and e.new_value.get("version") == 2
    )
    assert corr_entry.old_value == {
        "version_id": v1["id"],
        "version": 1,
        "outcome_kind": "value",
        "verdict": "pass",
        "version_hash": v1["version_hash"],
    }
    assert corr_entry.reason == "Salah baca angka pertama"

    retest_entry = next(e for e in all_entries if e.action == "attempt retested")
    assert retest_entry.old_value == {
        "attempt_id": _row(att1.json(), R026)["attempts"][0]["id"],
        "attempt_number": 1,
        "verdict": "fail",
    }
    assert retest_entry.reason == "Uji ulang setelah penyetelan"
