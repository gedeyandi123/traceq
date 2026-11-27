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
import re
import sys
from pathlib import Path
from typing import Any

import httpx

from traceq.app.demo import keycloak_pkce_token

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_ISSUER_URL = "http://127.0.0.1:9000"
KEYCLOAK_ISSUER_URL = "http://127.0.0.1:8080/realms/traceq"
"""The Keycloak realm URL of docs/demo-runbook.md section 15 (``Settings.keycloak_url``)."""

_RANGE = re.compile(
    r"(?P<lo>-?\d+(?:[.,]\d+)?)\s*(?:[-–—]|to)\s*(?P<hi>-?\d+(?:[.,]\d+)?)"
    r"\s*(?P<unit>[A-Za-z%°µ][A-Za-z0-9%°µ/.]*)"
)


def _checked(resp: Any, what: str) -> Any:
    """The response when it succeeded; otherwise an error naming the call and the body."""
    if resp.status_code >= 400:
        raise RuntimeError(f"{what} failed: {resp.status_code} {resp.text}")
    return resp


def _token(
    client: httpx.Client, issuer_url: str, username: str, *, idp: str = "demo"
) -> dict[str, str]:
    if idp == "keycloak":
        access_token = keycloak_pkce_token(issuer_url, username)
        return {"Authorization": f"Bearer {access_token}"}
    resp = client.post(f"{issuer_url}/demo/token", json={"username": username})
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


_SECOND_RUN_HINT = (
    "Create it as in docs/demo-runbook.md section 13: uv run traceq run <corpus> "
    "--equipment TP-201 --out runs-demo --recordings recordings/haiku-r10"
)


def _pick_two_rounds(
    client: Any, api_url: str, args: argparse.Namespace, headers: dict[str, str]
) -> str:
    """Round 1 = the older of the two oldest runs by ``created``, round 2 = the newer.

    Sets ``args.second_run_id`` unless given explicitly; returns the round 1 run id.
    """
    resp = client.get(f"{api_url}/runs", headers=headers)
    resp.raise_for_status()
    ordered = sorted(resp.json(), key=lambda r: str(r["created"]))
    if args.second_run_id is not None:
        others = [str(r["run_id"]) for r in ordered if str(r["run_id"]) != args.second_run_id]
        if not others:
            raise RuntimeError(f"No run besides {args.second_run_id} found. {_SECOND_RUN_HINT}")
        return others[0]
    if len(ordered) < 2:
        raise RuntimeError(f"--stage two-rounds needs two runs on the API. {_SECOND_RUN_HINT}")
    args.second_run_id = str(ordered[1]["run_id"])
    return str(ordered[0]["run_id"])


def _resolve_target(args: argparse.Namespace, client: httpx.Client) -> tuple[str, str, str, str]:
    api_url: str = args.api_url or DEFAULT_API_URL
    idp: str = getattr(args, "idp", None) or "demo"
    issuer_url: str = args.issuer_url or (
        KEYCLOAK_ISSUER_URL if idp == "keycloak" else DEFAULT_ISSUER_URL
    )
    run_id: str | None = args.run_id
    if args.ready_file is not None:
        meta = json.loads(Path(args.ready_file).read_text(encoding="utf-8"))
        api_url = args.api_url or str(meta["api_url"])
        issuer_url = args.issuer_url or str(meta["issuer_url"])
        if getattr(args, "idp", None) is None and meta.get("idp"):
            idp = str(meta["idp"])
        if not args.issuer_url and not meta.get("issuer_url") and idp == "keycloak":
            issuer_url = KEYCLOAK_ISSUER_URL
        if not getattr(args, "review_package", False):
            run_id = run_id or str(meta["run_id"])
    # Listing runs needs a token: the run routes are not open to an anonymous caller.
    if run_id is None and getattr(args, "stage", None) == "two-rounds":
        run_id = _pick_two_rounds(client, api_url, args, _token(client, issuer_url, "ayu", idp=idp))
    if run_id is None:
        runs = client.get(f"{api_url}/runs", headers=_token(client, issuer_url, "ayu", idp=idp))
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


def _demo_acceptance(requirement_text: str) -> dict[str, Any]:
    """An Acceptance Criterion for a demo row: the ``a-b unit`` range its requirement text
    prints, otherwise ``present``."""
    m = _RANGE.search(requirement_text)
    if m is not None:
        lo = float(m["lo"].replace(",", "."))
        hi = float(m["hi"].replace(",", "."))
        if lo <= hi:
            return {"type": "range", "min": lo, "max": hi, "unit": m["unit"].rstrip(".")}
    return {"type": "present"}


def _shape_acceptances(
    client: Any, api_url: str, protocol_id: int, proto: dict[str, Any], ayu: dict[str, str]
) -> dict[str, Any]:
    """Sets a shaped Acceptance Criterion, as a person does, on every row blocked by
    ``acceptance_not_shaped``: its accepted draft is rejected, then edited (the edit route
    is refused while that draft stays accepted). Returns the latest Protocol view."""
    for row in proto.get("rows") or []:
        if "acceptance_not_shaped" not in (row.get("blockers") or []):
            continue
        step = row["test_step"]
        proposal_id = step.get("proposal_id")
        if step.get("origin") != "accepted_draft" or proposal_id is None:
            raise RuntimeError(f"Row {row['requirement']} is not an accepted draft: cannot edit")
        rej = client.post(
            f"{api_url}/runs/{proto['run_id']}/proposals/{proposal_id}/decisions",
            headers=ayu,
            json={
                "decision": "rejected",
                "reason": "Demo seed: rejected to edit the draft with a shaped acceptance",
            },
        )
        _checked(rej, f"Rejecting draft {proposal_id} of {row['requirement']}")
        edit = client.post(
            f"{api_url}/protocols/{protocol_id}/drafts/{proposal_id}/edit",
            headers=ayu,
            json={
                "reason": "Demo seed: acceptance criterion set so the row can be executed",
                "test_step": {
                    "description": step["description"],
                    "method": step["method"],
                    "instrument": step.get("instrument"),
                    "acceptance": _demo_acceptance(str(row["text"])),
                },
            },
        )
        _checked(edit, f"Editing draft {proposal_id} of {row['requirement']}")
        proto = edit.json()
    return proto


def _blocking(proto: dict[str, Any]) -> str:
    """What still blocks submission: the non-zero checks of the checklist, the rows' blockers."""
    checks = [
        f"{c['check']} ({c['count']}): {c.get('requirements') or c.get('numbers')}"
        for c in proto.get("checklist") or []
        if c["count"]
    ]
    rows = [
        f"{r['requirement']}: {r['blockers']}" for r in proto.get("rows") or [] if r["blockers"]
    ]
    return "; ".join([*checks, *rows])


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
        proto = _shape_acceptances(client, api_url, protocol_id, proto, ayu)
        draft_hash = proto.get("draft_hash")
        if not draft_hash:
            raise RuntimeError(
                f"Protocol {protocol_id} cannot be submitted, a check blocks it: {_blocking(proto)}"
            )
        sub = client.post(
            f"{api_url}/protocols/{protocol_id}/submit",
            headers=_token(client, issuer_url, "ayu", idp=idp),
            json={"expected_draft_hash": str(draft_hash)},
        )
        proto = _checked(sub, f"Submitting Protocol {protocol_id}").json()

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
        proto = _checked(app, f"Approving Protocol {protocol_id}").json()
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
        runs = client.get(f"{api_url}/runs", headers=ayu)
        runs.raise_for_status()
        items = [str(i["run_id"]) for i in runs.json() if str(i["run_id"]) != first_run_id]
        if not items:
            raise RuntimeError(
                "Need a second run on API for --stage two-rounds (or pass --second-run-id). "
                + _SECOND_RUN_HINT
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
