"""Seed a running TraceQ demo instance to a target lifecycle stage via the public API.

Usage:
    uv run python scripts/demo_seed.py --stage approved-protocol [--ready-file FILE]
    uv run python scripts/demo_seed.py --stage completed-execution [--ready-file FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_ISSUER_URL = "http://127.0.0.1:9000"


def _token(client: httpx.Client, issuer_url: str, username: str) -> dict[str, str]:
    resp = client.post(f"{issuer_url}/demo/token", json={"username": username})
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _resolve_target(args: argparse.Namespace, client: httpx.Client) -> tuple[str, str, str]:
    api_url: str = args.api_url or DEFAULT_API_URL
    issuer_url: str = args.issuer_url or DEFAULT_ISSUER_URL
    run_id: str | None = args.run_id
    if args.ready_file is not None:
        meta = json.loads(Path(args.ready_file).read_text(encoding="utf-8"))
        api_url = args.api_url or str(meta["api_url"])
        issuer_url = args.issuer_url or str(meta["issuer_url"])
        run_id = run_id or str(meta["run_id"])
    if run_id is None:
        runs = client.get(f"{api_url}/runs")
        runs.raise_for_status()
        items = runs.json()
        if not items:
            raise RuntimeError("No runs found on API; start scripts/demo.py first.")
        run_id = str(items[0]["run_id"])
    return api_url.rstrip("/"), issuer_url.rstrip("/"), run_id


def _passing_value(acceptance: dict[str, Any]) -> dict[str, Any]:
    kind = acceptance.get("type")
    if kind == "number":
        target = acceptance.get("value")
        return {"type": "number", "value": float(target) if target is not None else 1.0}
    if kind == "range":
        lo = acceptance.get("low")
        hi = acceptance.get("high")
        if lo is not None and hi is not None:
            val = (float(lo) + float(hi)) / 2.0
        elif lo is not None:
            val = float(lo)
        elif hi is not None:
            val = float(hi)
        else:
            val = 1.0
        return {"type": "number", "value": val}
    if kind == "one_of":
        choices = acceptance.get("values") or []
        val = str(choices[0]) if choices else "ok"
        return {"type": "one_of", "value": val, "not_one_of": False}
    return {"type": "present", "value": True}


def _ensure_approved_protocol(
    client: httpx.Client, api_url: str, run_id: str, ayu: dict[str, str], dewi: dict[str, str]
) -> dict[str, Any]:
    proposals_resp = client.get(f"{api_url}/runs/{run_id}/proposals", headers=ayu)
    proposals_resp.raise_for_status()
    for p in proposals_resp.json():
        if p["state"] == "undecided":
            r = client.post(
                f"{api_url}/runs/{run_id}/proposals/{p['id']}/decisions",
                headers=ayu,
                json={"decision": "accepted"},
            )
            if r.status_code not in (200, 201):
                raise RuntimeError(
                    f"Decision failed on proposal {p['id']}: {r.status_code} {r.text}"
                )

    proto_resp = client.get(f"{api_url}/runs/{run_id}/protocol", headers=ayu)
    if proto_resp.status_code == 404:
        proto_resp = client.post(f"{api_url}/runs/{run_id}/protocol", headers=ayu)
    proto_resp.raise_for_status()
    proto: dict[str, Any] = proto_resp.json()
    protocol_id = int(proto["id"])

    if proto["status"] == "draft":
        sub = client.post(f"{api_url}/protocols/{protocol_id}/submit", headers=ayu)
        sub.raise_for_status()
        proto = sub.json()

    if proto["status"] == "submitted":
        submission = proto["submission"]
        app = client.post(
            f"{api_url}/protocols/{protocol_id}/approve",
            headers=dewi,
            json={
                "submission_event_id": int(submission["event_id"]),
                "hash": str(submission["hash"]),
            },
        )
        app.raise_for_status()
        proto = app.json()
    return proto


def _ensure_completed_execution(
    client: httpx.Client,
    api_url: str,
    run_id: str,
    protocol_id: int,
    ayu: dict[str, str],
    eko: dict[str, str],
) -> dict[str, Any]:
    exec_resp = client.get(f"{api_url}/runs/{run_id}/execution", headers=ayu)
    if exec_resp.status_code == 404:
        exec_resp = client.post(f"{api_url}/protocols/{protocol_id}/execution", headers=ayu)
    exec_resp.raise_for_status()
    execution: dict[str, Any] = exec_resp.json()
    execution_id = int(execution["id"])

    for row in execution["rows"]:
        if row["kind"] != "test_step" or row["attempts"]:
            continue
        req = str(row["requirement"])
        test_step = row["test_step"] or {}
        acceptance = test_step.get("acceptance") or {"type": "present"}
        payload: dict[str, Any] = {
            "outcome_kind": "value",
            "value": _passing_value(acceptance),
            "observation": "Seeded passing demo measurement.",
            "evidence": ["demo-seed"],
        }
        if test_step.get("instrument"):
            payload["instruments"] = [
                {
                    "instrument_id": f"CAL-{req}",
                    "calibrated_until": "2099-12-31",
                    "serial": f"SN-{req}",
                }
            ]
        att = client.post(
            f"{api_url}/executions/{execution_id}/rows/{req}/attempts",
            headers=ayu,
            json=payload,
        )
        att.raise_for_status()
        execution = att.json()

    for row in execution["rows"]:
        if row["kind"] != "test_step" or not row["attempts"]:
            continue
        req = str(row["requirement"])
        latest_attempt = row["attempts"][-1]
        if latest_attempt.get("witness") is not None:
            continue
        latest_ver = latest_attempt["versions"][-1]
        wit = client.post(
            f"{api_url}/executions/{execution_id}/rows/{req}/attempts/{latest_attempt['attempt_number']}/witness",
            headers=eko,
            json={
                "version_number": int(latest_ver["version_number"]),
                "version_hash": str(latest_ver["version_hash"]),
            },
        )
        wit.raise_for_status()
        execution = wit.json()

    if execution["status"] != "completed":
        comp = client.post(f"{api_url}/executions/{execution_id}/complete", headers=ayu)
        comp.raise_for_status()
        execution = comp.json()
    return execution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--stage",
        choices=("approved-protocol", "completed-execution"),
        required=True,
    )
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--api-url")
    parser.add_argument("--issuer-url")
    parser.add_argument("--run-id")
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        api_url, issuer_url, run_id = _resolve_target(args, client)
        ayu = _token(client, issuer_url, "ayu")
        dewi = _token(client, issuer_url, "dewi")
        proto = _ensure_approved_protocol(client, api_url, run_id, ayu, dewi)
        summary: dict[str, Any] = {
            "run_id": run_id,
            "protocol_id": proto["id"],
            "protocol_status": proto["status"],
            "stage": args.stage,
        }
        if args.stage == "completed-execution":
            eko = _token(client, issuer_url, "eko")
            execution = _ensure_completed_execution(
                client, api_url, run_id, int(proto["id"]), ayu, eko
            )
            summary["execution_id"] = execution["id"]
            summary["execution_status"] = execution["status"]
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
