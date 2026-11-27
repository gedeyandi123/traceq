"""Pure round-over-round diffing for documents, findings, and decisions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RoundDoc:
    doc_id: str
    rev: int
    sha256: str


type FindingChange = Literal["resolved", "persisted", "persisted_changed", "new"]
"""Where a finding of the round stands against the round before: ``resolved`` (only the
earlier round has it), ``persisted`` (both, on the same content), ``persisted_changed`` (both,
on other content) or ``new`` (only this round has it)."""


@dataclass(frozen=True)
class RoundFindingItem:
    """A finding of the later round: its identity (``proposal_id``, one per subject key and
    ordinal), the content hash its run proposed, and where its decision stands."""

    proposal_id: int
    content_hash: str
    state: str
    decided_run_id: str | None
    kind: str = "check"
    label: FindingLabel | None = None


@dataclass(frozen=True)
class PreviousFinding:
    """A finding of the earlier round: its identity and the content hash it had then."""

    proposal_id: int
    content_hash: str
    kind: str = "check"
    label: FindingLabel | None = None


@dataclass(frozen=True)
class FindingLabel:
    """What names a finding to a reader; never part of its identity."""

    finding_type: str | None
    test_step: str | None
    requirement: str | None


@dataclass(frozen=True)
class FindingDiff:
    proposal_id: int
    kind: str
    change: FindingChange
    label: FindingLabel | None


@dataclass(frozen=True)
class RoundDiff:
    previous_round_number: int
    previous_run_id: str
    documents_added: tuple[str, ...]
    documents_revised: tuple[str, ...]
    documents_unchanged: tuple[str, ...]
    documents_removed: tuple[str, ...]
    findings_resolved: int
    findings_persisted: int
    """Findings of both rounds, on the same content or not."""
    findings_persisted_changed: int
    """Of those persisted, the findings whose content changed."""
    findings_new: int
    decisions_carried_forward: int
    decisions_changed: int
    decisions_undecided: int
    findings: tuple[FindingDiff, ...] = ()
    """Every finding of either round and what became of it: the later round's in its order,
    then the resolved ones."""


def compute_round_diff(
    *,
    previous_round_number: int,
    previous_run_id: str,
    current_run_id: str,
    previous_docs: Sequence[RoundDoc],
    current_docs: Sequence[RoundDoc],
    previous_findings: Sequence[PreviousFinding],
    current_findings: Sequence[RoundFindingItem],
) -> RoundDiff:
    """Computes document, finding, and decision diffs between two consecutive rounds."""
    prev_by_id = {d.doc_id: (d.rev, d.sha256) for d in previous_docs}
    curr_by_id = {d.doc_id: (d.rev, d.sha256) for d in current_docs}

    added: list[str] = []
    revised: list[str] = []
    unchanged: list[str] = []
    for doc_id in sorted(curr_by_id):
        if doc_id not in prev_by_id:
            added.append(doc_id)
        elif prev_by_id[doc_id] == curr_by_id[doc_id]:
            unchanged.append(doc_id)
        else:
            revised.append(doc_id)
    removed = sorted(doc_id for doc_id in prev_by_id if doc_id not in curr_by_id)

    before = {f.proposal_id: f for f in previous_findings}
    now = {f.proposal_id: f for f in current_findings}
    changes: list[FindingDiff] = []
    for f in current_findings:
        earlier = before.get(f.proposal_id)
        change: FindingChange = (
            "new"
            if earlier is None
            else "persisted"
            if earlier.content_hash == f.content_hash
            else "persisted_changed"
        )
        changes.append(FindingDiff(f.proposal_id, f.kind, change, f.label))
    changes += [
        FindingDiff(p.proposal_id, p.kind, "resolved", p.label)
        for p in previous_findings
        if p.proposal_id not in now
    ]
    count = Counter(c.change for c in changes)

    carried_forward = sum(
        1
        for f in current_findings
        if f.state == "decided"
        and f.decided_run_id is not None
        and f.decided_run_id != current_run_id
    )
    changed = sum(1 for f in current_findings if f.state == "changed")
    undecided = sum(1 for f in current_findings if f.state == "undecided")

    return RoundDiff(
        previous_round_number=previous_round_number,
        previous_run_id=previous_run_id,
        documents_added=tuple(added),
        documents_revised=tuple(revised),
        documents_unchanged=tuple(unchanged),
        documents_removed=tuple(removed),
        findings_resolved=count["resolved"],
        findings_persisted=count["persisted"] + count["persisted_changed"],
        findings_persisted_changed=count["persisted_changed"],
        findings_new=count["new"],
        decisions_carried_forward=carried_forward,
        decisions_changed=changed,
        decisions_undecided=undecided,
        findings=tuple(changes),
    )
