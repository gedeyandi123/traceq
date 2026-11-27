"""Approving or returning a submitted Protocol (spec #247, "Submission, freezing and approval";
ADR 0012 "Freezing and approval", "Statuses").

Approval is a recorded status bound to the submission the Approver read (its event id and
hash), not an Electronic Signature (ADR 0007 phase 2). The Approver is neither the Preparer nor
anyone the frozen copy records as an author: of a decision in force (on Coverage, on the Test
Step, and every current decision on a drafted Test Step, rejections included), or of any
version of a written Test Step or of a disposition of a missed number (owner decision on #256).
The check reads the copy only, so a decision recorded after submission does not change it. For
a Protocol started from the Protocol Draft (version 2 copy, spec #375, S4a2) the Approver is also
none of those who decided a finding of the run (rejections too), mapped a draft Test Step,
decided a draft step or its criterion, or wrote a reason; and the approval is refused when a
newer revision of the draft arrived since the Approver opened it, recording the latest revision
in its event. The Approver also did not upload the revision of the draft the Protocol is pinned
to (ADR 0012, amended 27 November 2026): the upload queue names the uploader, so this is read
there, not from the copy (that revision only, not earlier ones).

A return sends a Submitted Protocol back to Draft with a reason; its copy stays as history.
Both take the per-Protocol lock and check the status inside it, so approve and return cannot
both succeed, and each has its Audit Trail entry in the same transaction.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import draft_source, lifecycle
from traceq.assembly.lifecycle import Conflict, Refused
from traceq.assembly.submission import (
    Author,
    FrozenDecision,
    ProtocolCopy,
    ProtocolCopyV2,
    Submission,
    submissions_of,
)

APPROVAL_NOTE = "a recorded status, not an Electronic Signature (ADR 0007 phase 2)"


def authors(copy: ProtocolCopy) -> list[Author]:
    """Everyone the copy records as an author of what it rests on, the Preparer excluded."""
    found: list[Author] = []
    for r in copy.rows:
        found.append(r.coverage.decision.author)
        found.extend(d.decision.author for d in r.drafts if d.decision is not None)
        if r.test_step is not None and r.test_step.decision is not None:
            found.append(r.test_step.decision.author)
        found.extend(v.author for v in r.written)
        found.extend(a.author for a in r.step_attributes)
    for u in copy.urs or ():
        found.extend(d.author for m in u.missed for d in m.dispositions)
    if isinstance(copy, ProtocolCopyV2):
        found.extend(_authors_v2(copy))
    return found


def _by(decisions: tuple[FrozenDecision, ...]) -> list[Author]:
    return [d.author for d in decisions]


def _authors_v2(copy: ProtocolCopyV2) -> list[Author]:
    """The authors only a version 2 copy records: the decisions on the criterion of an accepted
    draft step and on each candidate, every finding decision and reason of the run (findings tied
    to no row too), and every draft step's mapping and decisions."""
    found: list[Author] = []
    for r in copy.row_details:
        if r.criterion_decision is not None:
            found.append(r.criterion_decision.author)
        for c in r.candidates:
            found.extend(_by(tuple(d for d in (c.step_decision, c.criterion_decision) if d)))
    for f in copy.findings:
        found.extend(_by(f.decisions))
        found.extend(x.author for x in f.reasons)
    for s in copy.draft_steps:
        found.extend(m.author for m in s.mappings)
        found.extend(_by(s.decisions))
        found.extend(_by(s.criterion_decisions))
    return found


def _same(a: Author | audit.Actor, actor: audit.Actor) -> bool:
    return (a.subject, a.issuer) == (actor.subject, actor.issuer)


def _check_not_the_source_of_the_pin(
    session: Session, actor: audit.Actor, protocol: lifecycle.AssembledProtocol, rev: int
) -> None:
    """``UploaderApproves`` when ``actor`` uploaded the pinned Protocol Draft revision, or, with
    no upload of its bytes recorded, registered it by an import (ADR 0012, amended 27 and 28
    November 2026)."""
    uploaders = draft_source.uploaders_of_pinned(session, protocol)
    if uploaders:
        if any(_same(u, actor) for u in uploaders):
            raise draft_source.UploaderApproves(
                f"{actor.name} uploaded the Protocol Draft revision {rev} that Protocol"
                f" {protocol.id} is pinned to: an Approver did not"
            )
        return
    importer = draft_source.importer_of_pinned(session, protocol)
    if importer is not None and _same(importer, actor):
        raise draft_source.UploaderApproves(
            f"{actor.name} imported the Protocol Draft revision {rev} that Protocol"
            f" {protocol.id} is pinned to: an Approver did not"
        )


def _submitted(
    session: Session, protocol_id: int
) -> tuple[lifecycle.AssembledProtocol, Submission]:
    """The Protocol, locked, and its current submission; refused unless it is Submitted."""
    current = lifecycle.locked(
        session, protocol_id, "submitted", "only a Submitted Protocol can be approved or returned"
    )
    return current, submissions_of(session, protocol_id)[-1]


def approve(
    session: Session,
    actor: audit.Actor,
    protocol_id: int,
    event_id: int,
    hashed: str,
    *,
    auth_time: datetime | None,
    jti: str | None,
    is_demo: bool = False,
    expected_latest_draft_rev: int | None = None,
) -> lifecycle.AssembledProtocol:
    """Approves the Submitted Protocol whose current submission is ``event_id`` with copy hash
    ``hashed``: what the Approver read. ``expected_latest_draft_rev``: for a Protocol started
    from the Protocol Draft, the latest draft revision the Approver saw; ``Conflict`` when a
    newer one arrived since, ``Refused`` without it. Signs it: ``SignatureAuthRequired``
    without a fresh ``auth_time`` and ``jti``, before anything is written."""
    auth_time, jti = audit.require_signing_claims(auth_time, jti)
    current, latest = _submitted(session, protocol_id)
    latest_rev = draft_source.check_latest(session, current, expected_latest_draft_rev)
    if event_id != latest.event_id:
        raise Conflict(
            f"submission {event_id} is not the current submission of Protocol {protocol_id}"
            f" ({latest.event_id}): read it again before approving"
        )
    if hashed != latest.hash:
        raise Conflict(
            f"the hash given is not the hash of submission {latest.event_id}: read it again"
            " before approving"
        )
    copy = latest.copy
    if _same(copy.preparer, actor):
        raise Conflict(
            f"{actor.name} is the Preparer of Protocol {protocol_id}: an Approver is not"
        )
    if any(_same(a, actor) for a in authors(copy)):
        raise Conflict(
            f"{actor.name} recorded part of what Protocol {protocol_id} rests on (a decision in"
            " force, a decision on a finding, a draft step mapping, a disposition of a missed"
            " number, a written Test Step or step attributes): an Approver did not"
        )
    if current.draft is not None:
        _check_not_the_source_of_the_pin(session, actor, current, current.draft.rev)
    done = lifecycle.append(
        session, actor, protocol_id, "approved", None, latest_draft_rev=latest_rev
    )
    sig = audit.record_signature(
        session,
        actor,
        record_type="protocol_approval",
        signature_meaning="approved",
        content_hash=latest.hash,
        auth_time=auth_time,
        jti=jti,
        is_demo=is_demo,
        protocol_event_id=done.id,
    )
    new_audit: dict[str, audit.JsonValue] = {
        "status": done.status,
        "event_id": done.id,
        "submission_event_id": latest.event_id,
        "hash": latest.hash,
        "signature_id": sig.id,
    }
    if latest_rev is not None:
        new_audit["latest_draft_rev"] = latest_rev
    audit.append(
        session,
        actor,
        "protocol approved",
        "protocol",
        str(protocol_id),
        old={"status": current.status},
        new=new_audit,
    )
    return current.after(done)


def return_to_draft(
    session: Session, actor: audit.Actor, protocol_id: int, reason: str
) -> lifecycle.AssembledProtocol:
    """Returns a Submitted Protocol to Draft with a reason; its copy stays readable."""
    reason = reason.strip()
    if not reason:
        raise Refused("returning a Protocol needs a reason")
    current, latest = _submitted(session, protocol_id)
    done = lifecycle.append(session, actor, protocol_id, "returned", reason)
    audit.append(
        session,
        actor,
        "protocol returned",
        "protocol",
        str(protocol_id),
        old={"status": current.status},
        new={"status": done.status, "event_id": done.id, "submission_event_id": latest.event_id},
        reason=reason,
    )
    return current.after(done)
