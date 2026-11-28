"""Seed a running TraceQ demo instance to a target lifecycle stage via the public API.

Usage:
    uv run python scripts/demo_seed.py --stage approved-protocol [--ready-file FILE]
    uv run python scripts/demo_seed.py --stage completed-execution [--ready-file FILE]
    uv run python scripts/demo_seed.py --stage qualification-report [--ready-file FILE]
    uv run python scripts/demo_seed.py --stage two-rounds [--ready-file FILE] [--second-run-id ID]
    uv run python scripts/demo_seed.py --stage stale-pin [--ready-file FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from traceq.app.demo import keycloak_pkce_token

DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_ISSUER_URL = "http://127.0.0.1:9000"
KEYCLOAK_ISSUER_URL = "http://127.0.0.1:8080/realms/traceq"
"""The Keycloak realm URL of docs/demo-runbook.md section 15 (``Settings.keycloak_url``)."""
DEFAULT_EQUIPMENT = "TP-201"
DEFAULT_REV0_PDF = Path("dist/TP-201-OQ-draft/OQ-TP201_rev0.pdf")
DEFAULT_REV1_PDF = Path("dist/TP-201-OQ-draft/OQ-TP201_rev1.pdf")

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


def _resolve_connection(args: argparse.Namespace) -> tuple[str, str, str | None, str]:
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
    return api_url.rstrip("/"), issuer_url.rstrip("/"), run_id, idp


def _resolve_target(args: argparse.Namespace, client: Any) -> tuple[str, str, str, str]:
    api_url, issuer_url, run_id, idp = _resolve_connection(args)
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
    return api_url, issuer_url, run_id, idp


def _has_review_package(client: Any, api_url: str, run_id: str, headers: dict[str, str]) -> bool:
    resp = _checked(
        client.get(f"{api_url}/runs/{run_id}", headers=headers),
        f"Reading run {run_id}",
    )
    return resp.json().get("review_package") is not None


def _upload_draft_pdf(
    client: Any,
    api_url: str,
    equipment: str,
    pdf_path: Path,
    headers: dict[str, str],
    *,
    timeout_s: float = 120.0,
    poll_interval_s: float = 0.25,
) -> str:
    """Uploads a Protocol Draft PDF for ``equipment``, waits for ``succeeded``, returns id."""
    data = pdf_path.read_bytes()
    resp = client.post(
        f"{api_url}/equipment/{equipment}/drafts",
        headers={**headers, "Content-Type": "application/pdf"},
        content=data,
    )
    if resp.status_code == 409:
        sha256 = hashlib.sha256(data).hexdigest()
        listing = _checked(
            client.get(f"{api_url}/equipment/{equipment}/drafts", headers=headers),
            f"Listing draft uploads for {equipment}",
        ).json()
        existing = next(
            (
                j
                for j in listing.get("jobs") or []
                if j.get("sha256") == sha256 and j.get("status") != "failed"
            ),
            None,
        )
        if existing is None:
            _checked(resp, f"Uploading draft PDF {pdf_path}")
            raise RuntimeError(f"Uploading draft PDF {pdf_path} returned 409 without an active job")
        job: dict[str, Any] = existing
    else:
        job = _checked(resp, f"Uploading draft PDF {pdf_path}").json()

    job_id = int(job["id"])
    deadline = time.monotonic() + timeout_s
    while job.get("status") in ("queued", "running"):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Upload job {job_id} ({pdf_path}) did not finish within {timeout_s}s"
            )
        time.sleep(poll_interval_s)
        job = _checked(
            client.get(f"{api_url}/uploads/{job_id}", headers=headers),
            f"Polling upload job {job_id}",
        ).json()
    if job.get("status") != "succeeded" or not job.get("run_id"):
        status = job.get("status")
        msg = job.get("message")
        raise RuntimeError(f"Upload job {job_id} ({pdf_path}) ended with {status}: {msg}")
    return str(job["run_id"])


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
    if kind == "exclusive_range":
        lo = acceptance.get("min")
        hi = acceptance.get("max")
        if lo is not None and hi is not None:
            val = (float(lo) + float(hi)) / 2.0
        elif lo is not None:
            val = float(lo) + 1.0
        elif hi is not None:
            hi_f = float(hi)
            val = hi_f / 2.0 if hi_f > 0 else hi_f - 1.0
        else:
            val = 1.0
        return {"type": "number", "value": val}
    if kind == "tolerance":
        return {"type": "number", "value": float(acceptance["nominal"])}
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
    ``acceptance_not_shaped``: its accepted draft is rejected, with any other accepted draft step
    of the row, then edited (the edit route is refused while another draft stays accepted).
    Returns the latest Protocol view."""
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
        # A row holds one Test Step: the edit is refused while any other draft step standing for
        # the row is accepted (accept-all accepted every one of them). Newest decision first.
        for coll_key in ("candidates", "drafts"):
            for cand in row.get(coll_key) or []:
                other = cand["proposal"]
                decisions = other.get("decisions") or []
                if (
                    other["id"] != proposal_id
                    and other.get("state") == "decided"
                    and decisions
                    and decisions[0]["decision"] == "accepted"
                ):
                    more = client.post(
                        f"{api_url}/runs/{proto['run_id']}/proposals/{other['id']}/decisions",
                        headers=ayu,
                        json={
                            "decision": "rejected",
                            "reason": "Demo seed: the row holds one Test Step, the edited draft",
                        },
                    )
                    _checked(more, f"Rejecting draft {other['id']} of {row['requirement']}")
        edit = client.post(
            f"{api_url}/protocols/{protocol_id}/drafts/{proposal_id}/edit",
            headers=ayu,
            json={
                "reason": "Demo seed: acceptance criterion set so the row can be executed",
                "test_step": {
                    "description": (step.get("description") or "").strip()
                    or f"Test {row['requirement']}",
                    "method": (step.get("method") or "").strip() or "Verify per procedure.",
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
        f"{c['check']} ({c['count']}): "
        f"{c.get('requirements') or c.get('numbers') or c.get('steps')}"
        for c in proto.get("checklist") or []
        if c["count"]
    ]
    rows = [
        f"{r['requirement']}: {r['blockers']}" for r in proto.get("rows") or [] if r["blockers"]
    ]
    return "; ".join([*checks, *rows])


def _post_decision(
    client: Any,
    api_url: str,
    run_id: str,
    proposal: dict[str, Any],
    headers: dict[str, str],
    decision: str,
    *,
    reason: str | None = None,
) -> Any:
    payload: dict[str, Any] = {"decision": decision}
    effective_reason = reason
    if effective_reason is None and proposal.get("state") == "decided":
        effective_reason = "Demo seed: decision updated"
    if effective_reason is not None:
        payload["reason"] = effective_reason
    resp = client.post(
        f"{api_url}/runs/{run_id}/proposals/{proposal['id']}/decisions",
        headers=headers,
        json=payload,
    )
    return _checked(resp, f"Recording {decision} on proposal {proposal['id']}").json()


def _resolve_draft_steps(
    client: Any, api_url: str, protocol_id: int, proto: dict[str, Any], ayu: dict[str, str]
) -> dict[str, Any]:
    """Maps or rejects every unresolved draft Test Step on a Protocol started from the draft."""
    draft_steps = proto.get("draft_steps") or []
    if not any(not ds.get("resolved") for ds in draft_steps):
        return proto
    run_id = str(proto["run_id"])
    test_step_reqs = {
        str(r["requirement"])
        for r in proto.get("rows") or []
        if r.get("decided_class") != "covered_by_vendor"
    }
    assigned_reqs = {str(ds["requirement"]) for ds in draft_steps if ds.get("requirement")}
    rejected_any = False
    for ds in draft_steps:
        if ds.get("resolved"):
            continue
        step = ds["step"]
        step_id = str(step["id"])
        readable = (
            step.get("not_read") is None
            and bool((step.get("description") or "").strip())
            and bool((step.get("method") or "").strip())
        )
        candidates = [*(step.get("mapped_to") or []), *(step.get("requirements") or [])]
        target = next(
            (r for r in candidates if str(r) in test_step_reqs and str(r) not in assigned_reqs),
            None,
        )
        if readable and target is not None:
            resp = client.put(
                f"{api_url}/protocols/{protocol_id}/draft-steps/{step_id}/mapping",
                headers=ayu,
                json={"requirement": str(target)},
            )
            if resp.status_code < 400:
                proto = resp.json()
                assigned_reqs.add(str(target))
                continue
        _post_decision(
            client,
            api_url,
            run_id,
            ds["proposal"],
            ayu,
            "rejected",
            reason="Demo seed: unresolved draft step not usable",
        )
        rejected_any = True
    if rejected_any:
        proto = _checked(
            client.get(f"{api_url}/runs/{run_id}/protocol", headers=ayu),
            f"Re-reading Protocol {protocol_id}",
        ).json()
    return proto


def _is_currently_accepted(
    proposal: dict[str, Any] | None, mapping: dict[str, Any] | None = None
) -> bool:
    if proposal is None or proposal.get("state") != "decided":
        return False
    decisions = proposal.get("decisions") or []
    if not decisions or decisions[0].get("decision") != "accepted":
        return False
    if mapping is not None and decisions[0].get("at") and mapping.get("at"):
        return str(decisions[0]["at"]) > str(mapping["at"])
    return True


def _write_demo_test_step(
    client: Any,
    api_url: str,
    protocol_id: int,
    row: dict[str, Any],
    ayu: dict[str, str],
) -> dict[str, Any]:
    req = str(row["requirement"])
    prefill = row.get("prefill") or {}
    acceptance = prefill.get("acceptance")
    if acceptance is None or acceptance.get("type") == "text":
        acceptance = _demo_acceptance(str(row["text"]))
    payload = {
        "test_step": {
            "description": (prefill.get("description") or "").strip() or f"Verify {req}",
            "method": (prefill.get("method") or "").strip()
            or "Inspect and verify per approved procedure.",
            "instrument": prefill.get("instrument"),
            "acceptance": acceptance,
        }
    }
    resp = client.post(
        f"{api_url}/protocols/{protocol_id}/test-steps/{req}", headers=ayu, json=payload
    )
    return _checked(resp, f"Writing Test Step for {req}").json()


def _resolve_row_candidates(
    client: Any,
    api_url: str,
    protocol_id: int,
    run_id: str,
    row: dict[str, Any],
    ayu: dict[str, str],
) -> None:
    req = str(row["requirement"])
    candidates = row.get("candidates") or []
    test_step = row.get("test_step")
    if test_step is not None and test_step.get("origin") == "written":
        for cand in candidates:
            if not cand.get("ready"):
                _post_decision(
                    client,
                    api_url,
                    run_id,
                    cand["proposal"],
                    ayu,
                    "rejected",
                    reason="Demo seed: written Test Step already in force",
                )
        return
    if test_step is not None and test_step.get("origin") == "accepted_draft":
        active_pid = int(test_step["proposal_id"])
        for cand in candidates:
            if int(cand["proposal"]["id"]) != active_pid and not cand.get("ready"):
                _post_decision(
                    client,
                    api_url,
                    run_id,
                    cand["proposal"],
                    ayu,
                    "rejected",
                    reason="Demo seed: another draft Test Step is active on this row",
                )
        return

    primary = next(
        (c for c in candidates if _is_currently_accepted(c["proposal"], c.get("mapping"))),
        None,
    )
    if primary is None:
        primary = next(
            (
                c
                for c in candidates
                if c["step"].get("not_read") is None
                and bool((c["step"].get("description") or "").strip())
                and bool((c["step"].get("method") or "").strip())
            ),
            candidates[0],
        )
    primary_pid = int(primary["proposal"]["id"])
    for cand in candidates:
        if int(cand["proposal"]["id"]) != primary_pid and (
            not cand.get("ready") or _is_currently_accepted(cand["proposal"], cand.get("mapping"))
        ):
            _post_decision(
                client,
                api_url,
                run_id,
                cand["proposal"],
                ayu,
                "rejected",
                reason="Demo seed: row takes a single draft Test Step",
            )
    p_step = primary["step"]
    c_prop = primary.get("criterion_proposal")
    readable = (
        p_step.get("not_read") is None
        and bool((p_step.get("description") or "").strip())
        and bool((p_step.get("method") or "").strip())
    )
    if readable and c_prop is not None:
        if not _is_currently_accepted(primary["proposal"], primary.get("mapping")):
            _post_decision(client, api_url, run_id, primary["proposal"], ayu, "accepted")
        if not _is_currently_accepted(c_prop, primary.get("mapping")):
            _post_decision(client, api_url, run_id, c_prop, ayu, "accepted")
    else:
        edit = client.post(
            f"{api_url}/protocols/{protocol_id}/drafts/{primary_pid}/edit",
            headers=ayu,
            json={
                "reason": "Demo seed: edited draft step with shaped acceptance criterion",
                "test_step": {
                    "description": (p_step.get("description") or "").strip() or f"Test {req}",
                    "method": (p_step.get("method") or "").strip() or "Verify per procedure.",
                    "instrument": (p_step.get("instrument") or "").strip() or None,
                    "acceptance": _demo_acceptance(str(row["text"])),
                },
            },
        )
        _checked(edit, f"Editing draft {primary_pid} of {req}")


def _resolve_row_traceq_drafts(
    client: Any,
    api_url: str,
    protocol_id: int,
    run_id: str,
    row: dict[str, Any],
    ayu: dict[str, str],
) -> None:
    drafts = row.get("drafts") or []
    test_step = row.get("test_step")
    if test_step is not None and test_step.get("origin") == "written":
        for d in drafts:
            if d["proposal"].get("state") != "decided":
                _post_decision(
                    client,
                    api_url,
                    run_id,
                    d["proposal"],
                    ayu,
                    "rejected",
                    reason="Demo seed: written Test Step already in force",
                )
        return
    if test_step is not None and test_step.get("origin") == "accepted_draft":
        active_pid = int(test_step["proposal_id"])
        for d in drafts:
            if int(d["proposal"]["id"]) != active_pid and d["proposal"].get("state") != "decided":
                _post_decision(
                    client,
                    api_url,
                    run_id,
                    d["proposal"],
                    ayu,
                    "rejected",
                    reason="Demo seed: another draft Test Step is active on this row",
                )
        return

    chosen = next(
        (
            d
            for d in drafts
            if not (
                d["proposal"].get("state") == "decided"
                and (d["proposal"].get("decisions") or [{}])[0].get("decision") == "rejected"
            )
        ),
        None,
    )
    if chosen is None:
        _write_demo_test_step(client, api_url, protocol_id, row, ayu)
        return
    chosen_pid = int(chosen["proposal"]["id"])
    for d in drafts:
        if int(d["proposal"]["id"]) != chosen_pid and d["proposal"].get("state") != "decided":
            _post_decision(
                client,
                api_url,
                run_id,
                d["proposal"],
                ayu,
                "rejected",
                reason="Demo seed: row takes a single Test Step",
            )
    if chosen["proposal"].get("state") != "decided":
        _post_decision(client, api_url, run_id, chosen["proposal"], ayu, "accepted")


def _resolve_draft_protocol_rows(
    client: Any, api_url: str, protocol_id: int, proto: dict[str, Any], ayu: dict[str, str]
) -> dict[str, Any]:
    """Resolves Test Steps, findings/reasons, stages, and missed numbers on a draft Protocol."""
    run_id = str(proto["run_id"])
    for row in proto.get("rows") or []:
        if row.get("kind") != "test_step":
            continue
        if row.get("candidates"):
            _resolve_row_candidates(client, api_url, protocol_id, run_id, row, ayu)
        else:
            _resolve_row_traceq_drafts(client, api_url, protocol_id, run_id, row, ayu)

    proto = _checked(
        client.get(f"{api_url}/runs/{run_id}/protocol", headers=ayu),
        f"Re-reading Protocol {protocol_id}",
    ).json()
    proto = _shape_acceptances(client, api_url, protocol_id, proto, ayu)

    for row in proto.get("rows") or []:
        req = str(row["requirement"])
        blockers = set(row.get("blockers") or [])
        accepted_new_finding = False
        for f in row.get("findings") or []:
            fp = f["proposal"]
            if fp.get("state") != "decided":
                _post_decision(client, api_url, run_id, fp, ayu, "accepted")
                accepted_new_finding = True
        if "finding_reason_missing" in blockers or accepted_new_finding:
            for f in row.get("findings") or []:
                fp = f["proposal"]
                decisions = fp.get("decisions") or []
                is_accepted = accepted_new_finding or (
                    fp.get("state") == "decided"
                    and bool(decisions)
                    and decisions[0].get("decision") == "accepted"
                )
                if not is_accepted:
                    continue
                reasons = f.get("reasons") or []
                latest_at = decisions[0].get("at") if decisions else None
                has_current = bool(reasons) and (
                    latest_at is None or str(reasons[-1]["at"]) > str(latest_at)
                )
                if not has_current:
                    resp = client.post(
                        f"{api_url}/protocols/{protocol_id}/findings/{fp['id']}/reason",
                        headers=ayu,
                        json={
                            "reason": (
                                "Demo seed: finding acknowledged and justified for submission."
                            )
                        },
                    )
                    _checked(resp, f"Recording finding reason on {req}")
        if row.get("kind") == "test_step" and (
            "stage_missing" in blockers or row.get("stage") is None
        ):
            stage = "OQ" if (row.get("step_source") == "draft" or row.get("candidates")) else "IQ"
            resp = client.put(
                f"{api_url}/protocols/{protocol_id}/rows/{req}/attributes",
                headers=ayu,
                json={"stage": stage, "witness_required": bool(row.get("witness_required", False))},
            )
            _checked(resp, f"Setting stage {stage} on {req}")

    for u in proto.get("urs") or []:
        if u.get("numbers") != "checked":
            continue
        for m in u.get("missed") or []:
            if m.get("blocking"):
                resp = client.post(
                    f"{api_url}/protocols/{protocol_id}/missed-numbers",
                    headers=ayu,
                    json={
                        "doc": u["doc"],
                        "rev": int(u["rev"]),
                        "number": m["number"],
                        "kind": "not_tested_here",
                        "justification": "Demo seed: missed number disposition recorded.",
                    },
                )
                _checked(resp, f"Recording disposition for missed number {m['number']}")

    return _checked(
        client.get(f"{api_url}/runs/{run_id}/protocol", headers=ayu),
        f"Re-reading Protocol {protocol_id}",
    ).json()


def _ensure_submitted_protocol(
    client: Any,
    api_url: str,
    run_id: str,
    ayu: dict[str, str],
    *,
    from_draft: bool = False,
) -> dict[str, Any]:
    imp = client.post(f"{api_url}/runs/{run_id}/import", headers=ayu)
    imp.raise_for_status()

    _decide_proposals(
        client,
        api_url,
        run_id,
        ayu,
        kinds=("coverage", "draft") if from_draft else None,
    )

    proto_resp = client.get(f"{api_url}/runs/{run_id}/protocol", headers=ayu)
    if proto_resp.status_code == 404:
        if from_draft:
            proto_resp = client.post(
                f"{api_url}/runs/{run_id}/protocol", headers=ayu, json={"from_draft": True}
            )
        else:
            proto_resp = client.post(f"{api_url}/runs/{run_id}/protocol", headers=ayu)
    proto_resp.raise_for_status()
    proto: dict[str, Any] = proto_resp.json()
    protocol_id = int(proto["id"])

    if proto["status"] == "draft":
        if from_draft:
            proto = _resolve_draft_steps(client, api_url, protocol_id, proto, ayu)
            proto = _resolve_draft_protocol_rows(client, api_url, protocol_id, proto, ayu)
        else:
            proto = _shape_acceptances(client, api_url, protocol_id, proto, ayu)
        draft_hash = proto.get("draft_hash")
        if not draft_hash:
            raise RuntimeError(
                f"Protocol {protocol_id} cannot be submitted, a check blocks it: {_blocking(proto)}"
            )
        submit_body: dict[str, Any] = {"expected_draft_hash": str(draft_hash)}
        if proto.get("latest_draft_rev") is not None:
            submit_body["expected_latest_draft_rev"] = int(proto["latest_draft_rev"])
        sub = client.post(
            f"{api_url}/protocols/{protocol_id}/submit",
            headers=ayu,
            json=submit_body,
        )
        proto = _checked(sub, f"Submitting Protocol {protocol_id}").json()
    return proto


def _ensure_approved_protocol(
    client: Any,
    api_url: str,
    issuer_url: str,
    run_id: str,
    ayu: dict[str, str],
    *,
    idp: str = "demo",
    from_draft: bool = False,
) -> dict[str, Any]:
    proto = _ensure_submitted_protocol(client, api_url, run_id, ayu, from_draft=from_draft)
    if proto["status"] == "submitted":
        protocol_id = int(proto["id"])
        submission = proto["submission"]
        approve_body: dict[str, Any] = {
            "submission_event_id": int(submission["event_id"]),
            "hash": str(submission["hash"]),
        }
        if proto.get("latest_draft_rev") is not None:
            approve_body["expected_latest_draft_rev"] = int(proto["latest_draft_rev"])
        app = client.post(
            f"{api_url}/protocols/{protocol_id}/approve",
            headers=_token(client, issuer_url, "dewi", idp=idp),
            json=approve_body,
        )
        proto = _checked(app, f"Approving Protocol {protocol_id}").json()
    return proto


def _run_stale_pin(
    client: Any,
    api_url: str,
    issuer_url: str,
    equipment: str,
    rev0_pdf: Path,
    rev1_pdf: Path,
    ayu: dict[str, str],
    *,
    idp: str = "demo",
) -> dict[str, Any]:
    """Uploads rev0, submits a Protocol pinned to rev0 without approving, then uploads rev1."""
    del issuer_url, idp  # signature reserved for symmetric stage runners
    rev0_run_id = _upload_draft_pdf(client, api_url, equipment, rev0_pdf, ayu)
    _ensure_submitted_protocol(client, api_url, rev0_run_id, ayu, from_draft=True)
    rev1_run_id = _upload_draft_pdf(client, api_url, equipment, rev1_pdf, ayu)
    proto = _checked(
        client.get(f"{api_url}/runs/{rev0_run_id}/protocol", headers=ayu),
        f"Reading Protocol of {rev0_run_id}",
    ).json()
    source = proto.get("source") or {}
    return {
        "stage": "stale-pin",
        "equipment": equipment,
        "rev0_run_id": rev0_run_id,
        "rev1_run_id": rev1_run_id,
        "protocol_id": proto["id"],
        "protocol_status": proto["status"],
        "pinned_rev": source.get("rev"),
        "latest_rev": proto.get("latest_draft_rev"),
    }


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


def _decide_proposals(
    client: Any,
    api_url: str,
    run_id: str,
    ayu: dict[str, str],
    *,
    kinds: tuple[str, ...] | None = None,
) -> None:
    imp = client.post(f"{api_url}/runs/{run_id}/import", headers=ayu)
    imp.raise_for_status()
    proposals_resp = client.get(f"{api_url}/runs/{run_id}/proposals", headers=ayu)
    proposals_resp.raise_for_status()
    for p in proposals_resp.json():
        if kinds is not None and p.get("kind") not in kinds:
            continue
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
        choices=(
            "approved-protocol",
            "completed-execution",
            "qualification-report",
            "two-rounds",
            "stale-pin",
        ),
        required=True,
    )
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--api-url")
    parser.add_argument("--issuer-url")
    parser.add_argument("--idp", choices=("demo", "keycloak"))
    parser.add_argument("--run-id")
    parser.add_argument("--second-run-id")
    parser.add_argument("--review-package", action="store_true")
    parser.add_argument("--from-draft", action="store_true")
    parser.add_argument("--draft-pdf", type=Path)
    parser.add_argument("--equipment", default=DEFAULT_EQUIPMENT)
    parser.add_argument("--rev0-pdf", type=Path, default=DEFAULT_REV0_PDF)
    parser.add_argument("--rev1-pdf", type=Path, default=DEFAULT_REV1_PDF)
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        if args.stage == "stale-pin":
            api_url, issuer_url, _, idp = _resolve_connection(args)
            ayu = _token(client, issuer_url, "ayu", idp=idp)
            print(
                json.dumps(
                    _run_stale_pin(
                        client,
                        api_url,
                        issuer_url,
                        args.equipment,
                        args.rev0_pdf,
                        args.rev1_pdf,
                        ayu,
                        idp=idp,
                    )
                )
            )
            return 0
        if args.draft_pdf is not None:
            api_url, issuer_url, _, idp = _resolve_connection(args)
            ayu = _token(client, issuer_url, "ayu", idp=idp)
            run_id = _upload_draft_pdf(client, api_url, args.equipment, args.draft_pdf, ayu)
            from_draft = True
        else:
            api_url, issuer_url, run_id, idp = _resolve_target(args, client)
            ayu = _token(client, issuer_url, "ayu", idp=idp)
            if args.stage == "two-rounds":
                rounds_summary = _ensure_two_rounds(
                    client, api_url, run_id, args.second_run_id, ayu
                )
                print(json.dumps({"stage": args.stage, **rounds_summary}))
                return 0
            from_draft = bool(args.from_draft or _has_review_package(client, api_url, run_id, ayu))
        proto = _ensure_approved_protocol(
            client, api_url, issuer_url, run_id, ayu, idp=idp, from_draft=from_draft
        )
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
