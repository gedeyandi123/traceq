"""Seed a running TraceQ demo instance to a target lifecycle stage via the public API.

Usage:
    uv run python scripts/demo_seed.py --stage approved-protocol [--ready-file FILE]
    uv run python scripts/demo_seed.py --stage completed-execution [--ready-file FILE]
    uv run python scripts/demo_seed.py --stage qualification-report [--ready-file FILE]
    uv run python scripts/demo_seed.py --stage two-rounds [--ready-file FILE] [--second-run-id ID]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from traceq.app.demo import keycloak_pkce_token

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_ISSUER_URL = "http://127.0.0.1:9000"


def _token(
    client: httpx.Client, issuer_url: str, username: str, *, idp: str = "demo"
) -> dict[str, str]:
    if idp == "keycloak":
        access_token = keycloak_pkce_token(issuer_url, username)
        return {"Authorization": f"Bearer {access_token}"}
    resp = client.post(f"{issuer_url}/demo/token", json={"username": username})
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _resolve_target(args: argparse.Namespace, client: httpx.Client) -> tuple[str, str, str, str]:
    api_url: str = args.api_url or DEFAULT_API_URL
    issuer_url: str = args.issuer_url or DEFAULT_ISSUER_URL
    idp: str = getattr(args, "idp", None) or "demo"
    run_id: str | None = args.run_id
    if args.ready_file is not None:
        meta = json.loads(Path(args.ready_file).read_text(encoding="utf-8"))
        api_url = args.api_url or str(meta["api_url"])
        issuer_url = args.issuer_url or str(meta["issuer_url"])
        if getattr(args, "idp", None) is None and meta.get("idp"):
            idp = str(meta["idp"])
        if not getattr(args, "review_package", False):
            run_id = run_id or str(meta["run_id"])
    if run_id is None:
        runs = client.get(f"{api_url}/runs")
        runs.raise_for_status()
        items = runs.json()
        if not items:
            raise RuntimeError("No runs found on API; start scripts/demo.py first.")
        if getattr(args, "review_package", False):
            rp_item = next((i for i in items if i.get("review_package") is not None), None)
            if rp_item is None:
                raise RuntimeError("No Review Package run found on API.")
            run_id = str(rp_item["run_id"])
        else:
            run_id = str(items[0]["run_id"])
    return api_url.rstrip("/"), issuer_url.rstrip("/"), run_id, idp


def _passing_value(acceptance: dict[str, Any]) -> dict[str, Any]:
    kind = acceptance.get("type")
    if kind == "number":
        target = acceptance.get("value")
        return {"type": "number", "value": float(target) if target is not None else 1.0}
    if kind == "range":
        lo = acceptance.get("min")
        hi = acceptance.get("max")
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
        choices = acceptance.get("allowed") or []
        val = str(choices[0]) if choices else "ok"
        return {"type": "one_of", "value": val, "not_one_of": False}
    return {"type": "present", "value": True}


def _instrument_payload(req: str) -> dict[str, str]:
    return {"identifier": f"CAL-{req}", "calibration_due_date": "2099-12-31"}


def _needs_witness(latest_ver: dict[str, Any]) -> bool:
    confirmations = latest_ver.get("witness_confirmations") or []
    return not any(not c.get("voided") for c in confirmations)


def _witness_payload(latest_ver: dict[str, Any]) -> dict[str, Any]:
    return {
        "version_number": int(latest_ver["version"]),
        "version_hash": str(latest_ver["version_hash"]),
    }


def _ensure_approved_protocol(
    client: Any,
    api_url: str,
    issuer_url: str,
    run_id: str,
    ayu: dict[str, str],
    *,
    idp: str = "demo",
) -> dict[str, Any]:
    imp = client.post(f"{api_url}/runs/{run_id}/import", headers=ayu)
    imp.raise_for_status()

    proposals_resp = client.get(f"{api_url}/runs/{run_id}/proposals", headers=ayu)
    proposals_resp.raise_for_status()
    for p in proposals_resp.json():
        if p["state"] not in ("undecided", "changed"):
            continue
        url = f"{api_url}/runs/{run_id}/proposals/{p['id']}/decisions"
        r = client.post(url, headers=ayu, json={"decision": "accepted"})
        if r.status_code in (409, 422) and p.get("kind") == "coverage":
            r = client.post(
                url,
                headers=ayu,
                json={
                    "decision": "edited",
                    "coverage": "gap",
                    "reason": "Demo seed: no proposed coverage class",
                },
            )
        elif r.status_code == 409 and p.get("kind") == "test_step":
            r = client.post(
                url,
                headers=ayu,
                json={
                    "decision": "rejected",
                    "reason": "Demo seed: requirement already has an active Test Step",
                },
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Decision failed on proposal {p['id']}: {r.status_code} {r.text}")

    proto_resp = client.get(f"{api_url}/runs/{run_id}/protocol", headers=ayu)
    if proto_resp.status_code == 404:
        proto_resp = client.post(f"{api_url}/runs/{run_id}/protocol", headers=ayu)
    proto_resp.raise_for_status()
    proto: dict[str, Any] = proto_resp.json()
    protocol_id = int(proto["id"])

    if proto["status"] == "draft":
        blockers = proto.get("blockers") or []
        if blockers:
            raise RuntimeError(
                f"Protocol {protocol_id} has blockers preventing submission: {blockers}"
            )
        draft_hash = proto.get("draft_hash")
        if not draft_hash:
            raise RuntimeError(f"Protocol {protocol_id} has no draft hash: a check blocks it")
        sub = client.post(
            f"{api_url}/protocols/{protocol_id}/submit",
            headers=_token(client, issuer_url, "ayu", idp=idp),
            json={"expected_draft_hash": str(draft_hash)},
        )
        sub.raise_for_status()
        proto = sub.json()

    if proto["status"] == "submitted":
        submission = proto["submission"]
        app = client.post(
            f"{api_url}/protocols/{protocol_id}/approve",
            headers=_token(client, issuer_url, "dewi", idp=idp),
            json={
                "submission_event_id": int(submission["event_id"]),
                "hash": str(submission["hash"]),
            },
        )
        app.raise_for_status()
        proto = app.json()
    return proto


def _ensure_completed_execution(
    client: Any,
    api_url: str,
    issuer_url: str,
    run_id: str,
    protocol_id: int,
    ayu: dict[str, str],
    *,
    idp: str = "demo",
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
            payload["instruments"] = [_instrument_payload(req)]
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
        latest_ver = latest_attempt["versions"][-1]
        if not _needs_witness(latest_ver):
            continue
        wit = client.post(
            f"{api_url}/executions/{execution_id}/rows/{req}/attempts/{latest_attempt['attempt_number']}/witness",
            headers=_token(client, issuer_url, "eko", idp=idp),
            json=_witness_payload(latest_ver),
        )
        wit.raise_for_status()
        execution = wit.json()

    if execution["status"] != "completed":
        comp = client.post(f"{api_url}/executions/{execution_id}/complete", headers=ayu)
        comp.raise_for_status()
        execution = comp.json()
    return execution


def _decide_proposals(client: Any, api_url: str, run_id: str, ayu: dict[str, str]) -> None:
    imp = client.post(f"{api_url}/runs/{run_id}/import", headers=ayu)
    imp.raise_for_status()
    proposals_resp = client.get(f"{api_url}/runs/{run_id}/proposals", headers=ayu)
    proposals_resp.raise_for_status()
    for p in proposals_resp.json():
        if p["state"] not in ("undecided", "changed"):
            continue
        url = f"{api_url}/runs/{run_id}/proposals/{p['id']}/decisions"
        r = client.post(url, headers=ayu, json={"decision": "accepted"})
        if r.status_code in (409, 422) and p.get("kind") == "coverage":
            r = client.post(
                url,
                headers=ayu,
                json={
                    "decision": "edited",
                    "coverage": "gap",
                    "reason": "Demo seed: no proposed coverage class",
                },
            )
        elif r.status_code == 409 and p.get("kind") == "test_step":
            r = client.post(
                url,
                headers=ayu,
                json={
                    "decision": "rejected",
                    "reason": "Demo seed: requirement already has an active Test Step",
                },
            )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Decision failed on proposal {p['id']}: {r.status_code} {r.text}")


def _ensure_two_rounds(
    client: Any,
    api_url: str,
    first_run_id: str,
    second_run_id: str | None,
    ayu: dict[str, str],
) -> dict[str, Any]:
    if second_run_id is None:
        runs = client.get(f"{api_url}/runs")
        runs.raise_for_status()
        items = [str(i["run_id"]) for i in runs.json() if str(i["run_id"]) != first_run_id]
        if not items:
            raise RuntimeError(
                "Need a second run on API for --stage two-rounds (or pass --second-run-id)."
            )
        second_run_id = items[0]

    _decide_proposals(client, api_url, first_run_id, ayu)
    r1_view = client.get(f"{api_url}/runs/{first_run_id}/rounds", headers=ayu)
    r1_view.raise_for_status()
    r1_id = int(r1_view.json()["current_round_id"])

    exp1 = client.post(f"{api_url}/rounds/{r1_id}/exports", headers=ayu)
    exp1.raise_for_status()

    r1_current = next(r for r in r1_view.json()["rounds"] if int(r["id"]) == r1_id)
    if r1_current["status"] == "open":
        close1 = client.post(
            f"{api_url}/rounds/{r1_id}/close",
            headers=ayu,
            json={
                "outcome": "returned_for_revision",
                "reason": "Demo seed: returned for revision before second round.",
            },
        )
        close1.raise_for_status()

    _decide_proposals(client, api_url, second_run_id, ayu)
    r2_view = client.get(f"{api_url}/runs/{second_run_id}/rounds", headers=ayu)
    r2_view.raise_for_status()
    r2_id = int(r2_view.json()["current_round_id"])
    exp2 = client.post(f"{api_url}/rounds/{r2_id}/exports", headers=ayu)
    exp2.raise_for_status()

    return {
        "round_1_id": r1_id,
        "round_1_run_id": first_run_id,
        "round_1_export_id": exp1.json()["id"],
        "round_2_id": r2_id,
        "round_2_run_id": second_run_id,
        "round_2_export_id": exp2.json()["id"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--stage",
        choices=("approved-protocol", "completed-execution", "qualification-report", "two-rounds"),
        required=True,
    )
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--api-url")
    parser.add_argument("--issuer-url")
    parser.add_argument("--idp", choices=("demo", "keycloak"))
    parser.add_argument("--run-id")
    parser.add_argument("--second-run-id")
    parser.add_argument("--review-package", action="store_true")
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        api_url, issuer_url, run_id, idp = _resolve_target(args, client)
        ayu = _token(client, issuer_url, "ayu", idp=idp)
        if args.stage == "two-rounds":
            rounds_summary = _ensure_two_rounds(client, api_url, run_id, args.second_run_id, ayu)
            print(json.dumps({"stage": args.stage, **rounds_summary}))
            return 0
        proto = _ensure_approved_protocol(client, api_url, issuer_url, run_id, ayu, idp=idp)
        summary: dict[str, Any] = {
            "run_id": run_id,
            "protocol_id": proto["id"],
            "protocol_status": proto["status"],
            "stage": args.stage,
        }
        if args.stage in ("completed-execution", "qualification-report"):
            execution = _ensure_completed_execution(
                client, api_url, issuer_url, run_id, int(proto["id"]), ayu, idp=idp
            )
            summary["execution_id"] = execution["id"]
            summary["execution_status"] = execution["status"]
            if args.stage == "qualification-report":
                qual_state = client.get(
                    f"{api_url}/runs/{run_id}/qualification-report", headers=ayu
                )
                qual_state.raise_for_status()
                qual_data = qual_state.json()
                next_rev = (
                    int(qual_data["latest_export"]["revision_number"]) + 1
                    if qual_data.get("latest_export")
                    else 1
                )
                qual_resp = client.post(
                    f"{api_url}/executions/{execution['id']}/qualification-reports",
                    headers=_token(client, issuer_url, "dewi", idp=idp),
                    json={
                        "conclusion_note": "Demo seed: qualification report approved.",
                        "expected_revision_number": next_rev,
                        "expected_execution_copy_hash": str(qual_data["execution_copy_hash"]),
                    },
                )
                qual_resp.raise_for_status()
                qual = qual_resp.json()
                latest_exp = qual.get("latest_export") or {}
                summary["qualification_report_export_id"] = latest_exp.get("id")
                summary["technical_conclusion"] = qual.get("technical_conclusion")
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
