"""Approving or returning a submitted Protocol (spec #247, "Submission, freezing and approval";
ADR 0012 "Freezing and approval", "Statuses").

Approval is a recorded status bound to the submission the Approver read (its event id and
hash), not an Electronic Signature (ADR 0007 phase 2). The Approver is neither the Preparer nor
anyone the frozen copy records as an author: of a decision in force (on Coverage, on the Test
Step, and every current decision on a drafted Test Step, rejections included), or of any
version of a written Test Step or of a disposition of a missed number (owner decision on #256).
The check reads the copy only, so a decision recorded after submission does not change it.

A return sends a Submitted Protocol back to Draft with a reason; its copy stays as history.
Both take the per-Protocol lock and check the status inside it, so approve and return cannot
both succeed, and each has its Audit Trail entry in the same transaction.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle
from traceq.assembly.lifecycle import Conflict, Refused
from traceq.assembly.submission import Author, ProtocolCopy, Submission, submissions_of

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
    return found


def _same(a: Author, actor: audit.Actor) -> bool:
    return (a.subject, a.issuer) == (actor.subject, actor.issuer)


def _submitted(
    session: Session, protocol_id: int
) -> tuple[lifecycle.AssembledProtocol, Submission]:
    """The Protocol, locked, and its current submission; refused unless it is Submitted."""
    current = lifecycle.locked(
        session, protocol_id, "submitted", "only a Submitted Protocol can be approved or returned"
    )
    return current, submissions_of(session, protocol_id)[-1]


def approve(
    session: Session, actor: audit.Actor, protocol_id: int, event_id: int, hashed: str
) -> lifecycle.AssembledProtocol:
    """Approves the Submitted Protocol whose current submission is ``event_id`` with copy hash
    ``hashed``: what the Approver read."""
    current, latest = _submitted(session, protocol_id)
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
            " force, a disposition of a missed number, a written Test Step or step attributes):"
            " an Approver did not"
        )
    done = lifecycle.append(session, actor, protocol_id, "approved", None)
    audit.append(
        session,
        actor,
        "protocol approved",
        "protocol",
        str(protocol_id),
        old={"status": current.status},
        new={
            "status": done.status,
            "event_id": done.id,
            "submission_event_id": latest.event_id,
            "hash": latest.hash,
        },
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
