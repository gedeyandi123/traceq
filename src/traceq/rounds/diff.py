"""Pure round-over-round diffing for documents, findings, and decisions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RoundDoc:
    doc_id: str
    rev: int
    sha256: str


@dataclass(frozen=True)
class RoundFindingItem:
    subject_hash: str
    state: str
    decided_run_id: str | None


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
    findings_new: int
    decisions_carried_forward: int
    decisions_changed: int
    decisions_undecided: int


def compute_round_diff(
    *,
    previous_round_number: int,
    previous_run_id: str,
    current_run_id: str,
    previous_docs: Sequence[RoundDoc],
    current_docs: Sequence[RoundDoc],
    previous_finding_hashes: Sequence[str],
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

    prev_hashes = set(previous_finding_hashes)
    curr_hashes = {f.subject_hash for f in current_findings}
    resolved = len(prev_hashes - curr_hashes)
    persisted = len(prev_hashes & curr_hashes)
    new = len(curr_hashes - prev_hashes)

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
        findings_resolved=resolved,
        findings_persisted=persisted,
        findings_new=new,
        decisions_carried_forward=carried_forward,
        decisions_changed=changed,
        decisions_undecided=undecided,
    )
