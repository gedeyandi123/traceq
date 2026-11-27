"""Database store for review rounds, document versions, and report exports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    RowMapping,
    Table,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.proposals import decisions
from traceq.proposals.store import (
    PROPOSALS,
    RUN_PROPOSALS,
    RUNS,
    Imported,
    RunFiles,
    draft_document,
)
from traceq.reports import (
    PRE_REVIEW_TEMPLATE_VERSIONS,
    TEMPLATE_VERSION,
    TYPST_VERSION,
    PreReviewReportSnapshotV2,
    ReportDocument,
    ReportDroppedClaim,
    ReportFindingV2,
    ReportKindSummary,
    ReportMissingDocument,
    ReportRoundDiffV2,
    ReportUrsCompleteness,
    check_rendered_pdf,
    check_template_supported,
    parse_pre_review_snapshot,
    render_pre_review_pdf,
    snapshot_hash,
    typesettable_snapshot,
)
from traceq.rounds.diff import (
    FindingLabel,
    PreviousFinding,
    RoundDiff,
    RoundDoc,
    RoundFindingItem,
    compute_round_diff,
)
from traceq.runs.api import FINDINGS_FILE, RUN_FILE, find_run, read_served
from traceq.runs.completeness import COMPLETENESS_FILE
from traceq.runs.schemas import Completeness, Findings

type RoundEventKind = Literal["opened", "returned_for_revision", "ready_for_protocol"]
type RoundStatus = Literal["open", "returned_for_revision", "ready_for_protocol"]
type CloseOutcome = Literal["returned_for_revision", "ready_for_protocol"]

_EQUIPMENT_LOCK_NS = 5
_ROUND_LOCK_NS = 6
_FINDING_KINDS = ("check", "ai", "draft")

_META = MetaData()
DOCUMENT_VERSIONS = Table(
    "document_versions",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("equipment", Text),
    Column("doc_id", Text),
    Column("rev", Integer),
    Column("doc_type", Text),
    Column("source", Text),
    Column("sha256", Text),
    Column("first_seen_run_id", Text),
    Column("at", DateTime(timezone=True)),
)
REVIEW_ROUNDS = Table(
    "review_rounds",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("equipment", Text),
    Column("round_number", Integer),
    Column("run_id", Text),
    Column("previous_round_id", BigInteger),
    Column("at", DateTime(timezone=True)),
)
REVIEW_ROUND_EVENTS = Table(
    "review_round_events",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("round_id", BigInteger),
    Column("event", Text),
    Column("reason", Text),
    Column("at", DateTime(timezone=True)),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
)
REPORT_EXPORTS = Table(
    "report_exports",
    _META,
    Column("id", BigInteger, primary_key=True),
    Column("round_id", BigInteger),
    Column("execution_id", BigInteger),
    Column("report_kind", Text),
    Column("at", DateTime(timezone=True)),
    Column("subject", Text),
    Column("issuer", Text),
    Column("name", Text),
    Column("snapshot_json", JSONB),
    Column("snapshot_hash", Text),
    Column("pdf_sha256", Text),
    Column("template_version", Text),
    Column("typst_version", Text),
)


class NotFound(Exception):
    """Requested round or export does not exist."""


class Conflict(Exception):
    """State transition refused (e.g. round is already closed)."""


class Refused(Exception):
    """Input validation failed (e.g. missing Reason for Change)."""


@dataclass(frozen=True)
class DocumentVersion:
    id: int
    equipment: str
    doc_id: str
    rev: int
    doc_type: str | None
    source: str
    sha256: str
    first_seen_run_id: str
    at: datetime


@dataclass(frozen=True)
class RoundEvent:
    id: int
    round_id: int
    event: RoundEventKind
    reason: str | None
    at: datetime
    actor: audit.Actor


@dataclass(frozen=True)
class ReportExport:
    id: int
    round_id: int | None
    report_kind: str
    at: datetime
    actor: audit.Actor
    snapshot_hash: str
    pdf_sha256: str
    template_version: str
    typst_version: str
    execution_id: int | None = None


@dataclass(frozen=True)
class ReviewRound:
    id: int
    equipment: str
    round_number: int
    run_id: str
    previous_round_id: int | None
    at: datetime
    status: RoundStatus
    documents: tuple[DocumentVersion, ...]
    events: tuple[RoundEvent, ...]
    exports: tuple[ReportExport, ...]


def _lock_equipment(session: Session, equipment: str) -> None:
    session.execute(
        select(func.pg_advisory_xact_lock(_EQUIPMENT_LOCK_NS, func.hashtext(equipment)))
    )


def _lock_round(session: Session, round_id: int) -> None:
    session.execute(
        select(func.pg_advisory_xact_lock(_ROUND_LOCK_NS, func.hashtext(str(round_id))))
    )


def _event_of(m: RowMapping) -> RoundEvent:
    return RoundEvent(
        id=int(m["id"]),
        round_id=int(m["round_id"]),
        event=cast(RoundEventKind, m["event"]),
        reason=m["reason"],
        at=m["at"],
        actor=audit.actor_of_row(m),
    )


def _export_of(m: RowMapping) -> ReportExport:
    return ReportExport(
        id=int(m["id"]),
        round_id=None if m["round_id"] is None else int(m["round_id"]),
        report_kind=str(m["report_kind"]),
        at=m["at"],
        actor=audit.actor_of_row(m),
        snapshot_hash=str(m["snapshot_hash"]),
        pdf_sha256=str(m["pdf_sha256"]),
        template_version=str(m["template_version"]),
        typst_version=str(m["typst_version"]),
        execution_id=None if m["execution_id"] is None else int(m["execution_id"]),
    )


def _doc_of(m: RowMapping) -> DocumentVersion:
    return DocumentVersion(
        id=int(m["id"]),
        equipment=str(m["equipment"]),
        doc_id=str(m["doc_id"]),
        rev=int(m["rev"]),
        doc_type=m["doc_type"],
        source=str(m["source"]),
        sha256=str(m["sha256"]),
        first_seen_run_id=str(m["first_seen_run_id"]),
        at=m["at"],
    )


def _status_from_events(events: tuple[RoundEvent, ...]) -> RoundStatus:
    if not events:
        return "open"
    latest = events[-1].event
    if latest == "opened":
        return "open"
    return latest


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item) for item in cast(list[object], value) if isinstance(item, dict)
    ]


def _extract_documents(run: RunFiles) -> list[dict[str, Any]]:
    meta = run.meta
    rows: list[dict[str, Any]] = []
    corpus = cast(dict[str, Any], meta.get("corpus") or {})
    for doc_d in _dict_items(corpus.get("documents")):
        doc_id = doc_d.get("doc_id")
        rev = doc_d.get("rev")
        sha = doc_d.get("sha256")
        if doc_id is None or rev is None or sha is None:
            continue
        rows.append(
            {
                "doc_id": str(doc_id),
                "rev": int(rev),
                "doc_type": doc_d.get("type") or doc_d.get("doc_type"),
                "source": "corpus",
                "sha256": str(sha),
            }
        )

    drafted = draft_document(run)
    if drafted is not None:
        rows.append(
            {**drafted, "doc_type": "protocol_draft", "source": "review_package_draft"},
        )
    return rows


def register_import(
    session: Session, actor: audit.Actor, imported: Imported, run: RunFiles
) -> None:
    """Opens a 1:1 review round and records document versions for a newly imported run."""
    _lock_equipment(session, imported.equipment)

    docs = _extract_documents(run)
    if docs:
        session.execute(
            insert(DOCUMENT_VERSIONS)
            .values(
                [
                    {
                        "equipment": imported.equipment,
                        "doc_id": d["doc_id"],
                        "rev": d["rev"],
                        "doc_type": d["doc_type"],
                        "source": d["source"],
                        "sha256": d["sha256"],
                        "first_seen_run_id": imported.run_id,
                    }
                    for d in docs
                ]
            )
            .on_conflict_do_nothing(index_elements=["equipment", "doc_id", "rev", "sha256"])
        )

    prev = (
        session.execute(
            select(REVIEW_ROUNDS.c.id, REVIEW_ROUNDS.c.round_number)
            .where(REVIEW_ROUNDS.c.equipment == imported.equipment)
            .order_by(REVIEW_ROUNDS.c.round_number.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    round_number = 1 if prev is None else int(prev["round_number"]) + 1
    previous_round_id = None if prev is None else int(prev["id"])

    round_row = (
        session.execute(
            insert(REVIEW_ROUNDS)
            .values(
                equipment=imported.equipment,
                round_number=round_number,
                run_id=imported.run_id,
                previous_round_id=previous_round_id,
            )
            .returning(REVIEW_ROUNDS.c.id)
        )
        .mappings()
        .one()
    )
    round_id = int(round_row["id"])
    session.execute(
        insert(REVIEW_ROUND_EVENTS).values(
            round_id=round_id,
            event="opened",
            reason=None,
            subject=actor.subject,
            issuer=actor.issuer,
            name=actor.name,
        )
    )
    audit.append(
        session,
        actor,
        "review round opened",
        "review_round",
        str(round_id),
        new={
            "round_id": round_id,
            "equipment": imported.equipment,
            "round_number": round_number,
            "run_id": imported.run_id,
            "previous_round_id": previous_round_id,
        },
    )


def _docs_for_run(session: Session, equipment: str, run_id: str) -> tuple[DocumentVersion, ...]:
    run_row = (
        session.execute(select(RUNS.c.documents).where(RUNS.c.run_id == run_id)).mappings().first()
    )
    corpus_docs = _dict_items(run_row["documents"] if run_row else None)
    keys = {
        (str(d["doc_id"]), int(d["rev"]), str(d["sha256"]))
        for d in corpus_docs
        if {"doc_id", "rev", "sha256"} <= d.keys()
    }
    all_eq_docs = [
        _doc_of(m)
        for m in session.execute(
            select(DOCUMENT_VERSIONS)
            .where(DOCUMENT_VERSIONS.c.equipment == equipment)
            .order_by(DOCUMENT_VERSIONS.c.id)
        ).mappings()
    ]
    return tuple(
        d
        for d in all_eq_docs
        if d.first_seen_run_id == run_id or (d.doc_id, d.rev, d.sha256) in keys
    )


def _load_round(session: Session, round_row: RowMapping) -> ReviewRound:
    round_id = int(round_row["id"])
    equipment = str(round_row["equipment"])
    run_id = str(round_row["run_id"])
    events = tuple(
        _event_of(m)
        for m in session.execute(
            select(REVIEW_ROUND_EVENTS)
            .where(REVIEW_ROUND_EVENTS.c.round_id == round_id)
            .order_by(REVIEW_ROUND_EVENTS.c.id)
        ).mappings()
    )
    exports = tuple(
        _export_of(m)
        for m in session.execute(
            select(REPORT_EXPORTS)
            .where(
                REPORT_EXPORTS.c.round_id == round_id,
                REPORT_EXPORTS.c.report_kind == "pre_review",
            )
            .order_by(REPORT_EXPORTS.c.id)
        ).mappings()
    )
    docs = _docs_for_run(session, equipment, run_id)
    return ReviewRound(
        id=round_id,
        equipment=equipment,
        round_number=int(round_row["round_number"]),
        run_id=run_id,
        previous_round_id=(
            None if round_row["previous_round_id"] is None else int(round_row["previous_round_id"])
        ),
        at=round_row["at"],
        status=_status_from_events(events),
        documents=docs,
        events=events,
        exports=exports,
    )


def _labels_for_run(session: Session, run_id: str) -> dict[int, FindingLabel]:
    """What names each finding of a run, from its subject key: type, Test Step (or table row)
    and requirement."""
    labels: dict[int, FindingLabel] = {}
    for row in session.execute(
        select(PROPOSALS.c.id, PROPOSALS.c.subject)
        .select_from(PROPOSALS.join(RUN_PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id))
        .where(RUN_PROPOSALS.c.run_id == run_id)
        .where(PROPOSALS.c.kind.in_(_FINDING_KINDS))
    ).mappings():
        subject = cast(dict[str, Any], row["subject"])
        labels[int(row["id"])] = FindingLabel(
            finding_type=subject.get("type"),
            test_step=subject.get("test_step") or subject.get("row"),
            requirement=subject.get("requirement"),
        )
    return labels


def _finding_items_for_run(session: Session, run_id: str) -> list[RoundFindingItem]:
    standings = decisions.standings(session, run_id) or []
    labels = _labels_for_run(session, run_id)
    items: list[RoundFindingItem] = []
    for s in standings:
        if s.kind not in _FINDING_KINDS or s.proposal_id not in labels:
            continue
        decided_run_id = s.decisions[0].run_id if s.decisions else None
        items.append(
            RoundFindingItem(
                proposal_id=s.proposal_id,
                content_hash=s.content_hash,
                state=s.state,
                decided_run_id=decided_run_id,
                kind=s.kind,
                label=labels[s.proposal_id],
            )
        )
    return items


def _previous_findings_for_run(session: Session, run_id: str) -> list[PreviousFinding]:
    labels = _labels_for_run(session, run_id)
    return [
        PreviousFinding(
            proposal_id=int(row["proposal_id"]),
            content_hash=str(row["content_hash"]),
            kind=str(row["kind"]),
            label=labels.get(int(row["proposal_id"])),
        )
        for row in session.execute(
            select(RUN_PROPOSALS.c.proposal_id, RUN_PROPOSALS.c.content_hash, PROPOSALS.c.kind)
            .select_from(
                PROPOSALS.join(RUN_PROPOSALS, PROPOSALS.c.id == RUN_PROPOSALS.c.proposal_id)
            )
            .where(RUN_PROPOSALS.c.run_id == run_id)
            .where(PROPOSALS.c.kind.in_(_FINDING_KINDS))
            .order_by(RUN_PROPOSALS.c.seq)
        ).mappings()
    ]


def _diff_for_round(session: Session, current: ReviewRound) -> RoundDiff | None:
    if current.previous_round_id is None:
        return None
    prev_row = (
        session.execute(
            select(REVIEW_ROUNDS).where(REVIEW_ROUNDS.c.id == current.previous_round_id)
        )
        .mappings()
        .first()
    )
    if prev_row is None:
        return None
    prev_run_id = str(prev_row["run_id"])
    prev_docs = _docs_for_run(session, current.equipment, prev_run_id)
    return compute_round_diff(
        previous_round_number=int(prev_row["round_number"]),
        previous_run_id=prev_run_id,
        current_run_id=current.run_id,
        previous_docs=[RoundDoc(d.doc_id, d.rev, d.sha256) for d in prev_docs],
        current_docs=[RoundDoc(d.doc_id, d.rev, d.sha256) for d in current.documents],
        previous_findings=_previous_findings_for_run(session, prev_run_id),
        current_findings=_finding_items_for_run(session, current.run_id),
    )


def rounds_for_run(
    session: Session, run_id: str
) -> tuple[ReviewRound, list[ReviewRound], RoundDiff | None]:
    """Returns ``(current_round, all_equipment_rounds, diff_vs_previous)`` for ``run_id``."""
    target_row = (
        session.execute(select(REVIEW_ROUNDS).where(REVIEW_ROUNDS.c.run_id == run_id))
        .mappings()
        .first()
    )
    if target_row is None:
        raise NotFound(f"no review round for run {run_id}")
    equipment = str(target_row["equipment"])
    all_rows = (
        session.execute(
            select(REVIEW_ROUNDS)
            .where(REVIEW_ROUNDS.c.equipment == equipment)
            .order_by(REVIEW_ROUNDS.c.round_number)
        )
        .mappings()
        .all()
    )
    all_rounds = [_load_round(session, r) for r in all_rows]
    current = next(r for r in all_rounds if r.run_id == run_id)
    diff = _diff_for_round(session, current)
    return current, all_rounds, diff


def close_round(
    session: Session,
    actor: audit.Actor,
    round_id: int,
    outcome: CloseOutcome,
    reason: str | None,
) -> ReviewRound:
    """Closes an open review round as ``returned_for_revision`` or ``ready_for_protocol``."""
    _lock_round(session, round_id)
    row = (
        session.execute(select(REVIEW_ROUNDS).where(REVIEW_ROUNDS.c.id == round_id))
        .mappings()
        .first()
    )
    if row is None:
        raise NotFound(f"no review round {round_id}")
    current = _load_round(session, row)
    if current.status != "open":
        raise Conflict(f"review round {round_id} is already closed ({current.status})")
    clean_reason = reason.strip() if reason is not None else None
    if outcome == "returned_for_revision" and not clean_reason:
        raise Refused("returning a review round for revision requires a non-blank reason")
    if clean_reason == "":
        clean_reason = None

    session.execute(
        insert(REVIEW_ROUND_EVENTS).values(
            round_id=round_id,
            event=outcome,
            reason=clean_reason,
            subject=actor.subject,
            issuer=actor.issuer,
            name=actor.name,
        )
    )
    audit.append(
        session,
        actor,
        "review round closed",
        "review_round",
        str(round_id),
        old={"status": "open"},
        new={"status": outcome},
        reason=clean_reason,
    )
    return _load_round(session, row)


def _format_cite(c: dict[str, Any]) -> str:
    return f"{c.get('doc', '')} rev {c.get('rev', '')} p.{c.get('page', '')}".strip()


def _kind_summary(k: decisions.KindCounts) -> ReportKindSummary:
    decided = k.accepted + k.edited + k.rejected
    return ReportKindSummary(
        total=k.total,
        decided=decided,
        accepted=k.accepted,
        edited=k.edited,
        rejected=k.rejected,
        undecided=k.undecided,
        changed=k.changed,
    )


def _combine_kind_summaries(items: list[decisions.KindCounts]) -> ReportKindSummary:
    total = sum(i.total for i in items)
    accepted = sum(i.accepted for i in items)
    edited = sum(i.edited for i in items)
    rejected = sum(i.rejected for i in items)
    undecided = sum(i.undecided for i in items)
    changed = sum(i.changed for i in items)
    return ReportKindSummary(
        total=total,
        decided=accepted + edited + rejected,
        accepted=accepted,
        edited=edited,
        rejected=rejected,
        undecided=undecided,
        changed=changed,
    )


def _label_of(proposed: dict[str, Any]) -> str | None:
    """The label a finding carries ("not reviewed by a practitioner"), if its payload has one."""
    label = proposed.get("label")
    return label if isinstance(label, str) and label else None


def _build_snapshot(
    session: Session,
    runs: Path,
    current: ReviewRound,
    generated_at: datetime,
) -> PreReviewReportSnapshotV2:
    counts = decisions.counts(session, current.run_id)
    if counts is None:
        raise NotFound(f"run {current.run_id} is not imported")
    standings = decisions.standings(session, current.run_id) or []

    proposed_by_id = {
        int(r["proposal_id"]): cast(dict[str, Any], r["proposed"])
        for r in session.execute(
            select(RUN_PROPOSALS.c.proposal_id, RUN_PROPOSALS.c.proposed).where(
                RUN_PROPOSALS.c.run_id == current.run_id
            )
        ).mappings()
    }

    diff = _diff_for_round(session, current)
    change_of = {} if diff is None else {f.proposal_id: str(f.change) for f in diff.findings}
    check_findings: list[ReportFindingV2] = []
    ai_findings: list[ReportFindingV2] = []
    draft_findings: list[ReportFindingV2] = []

    for s in standings:
        if s.kind not in _FINDING_KINDS:
            continue
        prop = proposed_by_id.get(s.proposal_id, {})
        cites = tuple(_format_cite(c) for c in _dict_items(prop.get("citations")))
        latest = s.decisions[0] if s.decisions else s.previous
        item = ReportFindingV2(
            position=s.position or 0,
            finding_type=str(prop.get("type") or s.kind),
            doc=str(prop["doc"]) if prop.get("doc") is not None else None,
            detail=str(prop.get("detail") or ""),
            citations=cites,
            state=s.state,
            decision=latest.decision if (s.state == "decided" and latest is not None) else None,
            reason=latest.reason if latest is not None else None,
            decided_by=latest.actor.name if (s.state == "decided" and latest is not None) else None,
            decided_at=latest.at if (s.state == "decided" and latest is not None) else None,
            label=_label_of(prop),
            change=change_of.get(s.proposal_id),
        )
        if s.kind == "check":
            check_findings.append(item)
        elif s.kind == "ai":
            ai_findings.append(item)
        else:
            draft_findings.append(item)

    folder = find_run(runs, current.run_id)
    missing_docs: list[ReportMissingDocument] = []
    dropped_claims: list[ReportDroppedClaim] = []
    completeness_rows: list[ReportUrsCompleteness] = []

    if folder is not None:
        findings_path = folder / FINDINGS_FILE
        if findings_path.is_file():
            f_obj = Findings.model_validate(read_served(findings_path))
            for m in f_obj.missing_documents:
                missing_docs.append(
                    ReportMissingDocument(
                        doc_id=m.doc_id,
                        doc_type=m.type,
                        stage=m.stage,
                        citation=f"{m.citation.doc} rev {m.citation.rev} p.{m.citation.page}",
                    )
                )
        run_path = folder / RUN_FILE
        if run_path.is_file():
            meta = read_served(run_path)
            for dc in _dict_items(meta.get("dropped")):
                dropped_claims.append(
                    ReportDroppedClaim(
                        claim=str(dc.get("claim", "")),
                        id=str(dc.get("id", "")),
                        reason=str(dc.get("reason", "")),
                    )
                )

    comp_db = session.execute(
        select(RUNS.c.completeness).where(RUNS.c.run_id == current.run_id)
    ).scalar_one_or_none()
    comp_obj: Completeness | None = None
    if comp_db is not None:
        comp_obj = Completeness.model_validate(comp_db)
    elif folder is not None and (folder / COMPLETENESS_FILE).is_file():
        comp_obj = Completeness.model_validate(read_served(folder / COMPLETENESS_FILE))

    if comp_obj is not None:
        for u in comp_obj.urs:
            completeness_rows.append(
                ReportUrsCompleteness(
                    doc=u.doc,
                    rev=u.rev,
                    numbers=u.numbers,
                    found=u.found,
                    missed_count=len(u.missed),
                    unquoted_count=len(u.unquoted),
                )
            )

    report_diff = (
        None
        if diff is None
        else ReportRoundDiffV2(
            previous_round_number=diff.previous_round_number,
            previous_run_id=diff.previous_run_id,
            documents_added=diff.documents_added,
            documents_revised=diff.documents_revised,
            documents_unchanged=diff.documents_unchanged,
            documents_removed=diff.documents_removed,
            findings_resolved=diff.findings_resolved,
            findings_persisted=diff.findings_persisted,
            findings_persisted_changed=diff.findings_persisted_changed,
            findings_new=diff.findings_new,
            decisions_carried_forward=diff.decisions_carried_forward,
            decisions_changed=diff.decisions_changed,
            decisions_undecided=diff.decisions_undecided,
        )
    )

    snapshot = PreReviewReportSnapshotV2(
        generated_at=generated_at,
        equipment=current.equipment,
        run_id=current.run_id,
        round_number=current.round_number,
        round_status=current.status,
        documents=tuple(
            ReportDocument(
                doc_id=d.doc_id,
                rev=d.rev,
                doc_type=d.doc_type,
                source=d.source,
                sha256=d.sha256,
            )
            for d in current.documents
        ),
        coverage=_kind_summary(counts["coverage"]),
        findings_summary=_combine_kind_summaries([counts["check"], counts["ai"], counts["draft"]]),
        check_findings=tuple(check_findings),
        ai_findings=tuple(ai_findings),
        draft_findings=tuple(draft_findings),
        missing_documents=tuple(missing_docs),
        dropped_claims=tuple(dropped_claims),
        completeness=tuple(completeness_rows),
        round_diff=report_diff,
    )
    return typesettable_snapshot(snapshot)


def export_pre_review(
    session: Session,
    actor: audit.Actor,
    runs: Path,
    round_id: int,
) -> ReportExport:
    """Compiles and stores an immutable Pre-Review Report PDF export for ``round_id``."""
    _lock_round(session, round_id)
    row = (
        session.execute(select(REVIEW_ROUNDS).where(REVIEW_ROUNDS.c.id == round_id))
        .mappings()
        .first()
    )
    if row is None:
        raise NotFound(f"no review round {round_id}")
    current = _load_round(session, row)
    generated_at = session.execute(text("SELECT date_trunc('second', now())")).scalar_one()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    else:
        generated_at = generated_at.astimezone(UTC)

    snapshot = _build_snapshot(session, runs, current, generated_at)
    pdf_bytes = render_pre_review_pdf(snapshot)
    snap_hash = snapshot_hash(snapshot)
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()

    inserted = (
        session.execute(
            insert(REPORT_EXPORTS)
            .values(
                round_id=round_id,
                report_kind="pre_review",
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
                snapshot_json=snapshot.model_dump(mode="json"),
                snapshot_hash=snap_hash,
                pdf_sha256=pdf_sha,
                template_version=TEMPLATE_VERSION,
                typst_version=TYPST_VERSION,
            )
            .returning(*REPORT_EXPORTS.c)
        )
        .mappings()
        .one()
    )
    export = _export_of(inserted)
    audit.append(
        session,
        actor,
        "pre-review report exported",
        "report_export",
        str(export.id),
        new={
            "export_id": export.id,
            "round_id": round_id,
            "report_kind": "pre_review",
            "snapshot_hash": snap_hash,
            "pdf_sha256": pdf_sha,
            "template_version": TEMPLATE_VERSION,
            "typst_version": TYPST_VERSION,
        },
    )
    return export


def render_stored_export_pdf(session: Session, round_id: int, export_id: int) -> bytes:
    """Re-renders a stored export's PDF from ``snapshot_json`` without any DB writes.

    Raises ``ReportNotReproducible`` when the export's template version is not carried by this
    release, or when the re-render does not match the stored SHA-256 (a Typst version that
    differs from the running one is named as the likely cause, not a refusal by itself)."""
    row = (
        session.execute(
            select(
                REPORT_EXPORTS.c.snapshot_json,
                REPORT_EXPORTS.c.pdf_sha256,
                REPORT_EXPORTS.c.template_version,
                REPORT_EXPORTS.c.typst_version,
            ).where(
                REPORT_EXPORTS.c.id == export_id,
                REPORT_EXPORTS.c.round_id == round_id,
                REPORT_EXPORTS.c.report_kind == "pre_review",
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFound(f"no export {export_id} for review round {round_id}")
    template_version = str(row["template_version"])
    check_template_supported(template_version, PRE_REVIEW_TEMPLATE_VERSIONS)
    snapshot = parse_pre_review_snapshot(row["snapshot_json"], template_version)
    pdf_bytes = render_pre_review_pdf(snapshot, template_version=template_version)
    check_rendered_pdf(
        pdf_bytes, str(row["pdf_sha256"]), stored_typst_version=str(row["typst_version"])
    )
    return pdf_bytes
