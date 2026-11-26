"""Qualification Report generation, SoD enforcement, and Typst PDF export (Step 7, #326)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import RowMapping, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from traceq import audit
from traceq.assembly import lifecycle as assembly_lifecycle
from traceq.assembly.submission import Author
from traceq.execution import completion, lifecycle
from traceq.execution.completion import Completion, ExecutionCopy
from traceq.proposals.keys import digest
from traceq.reports import (
    QUALIFICATION_TEMPLATE_VERSION,
    QUALIFICATION_TEMPLATE_VERSIONS,
    TYPST_VERSION,
    QualificationCounts,
    QualificationReportDeviation,
    QualificationReportRow,
    QualificationReportSnapshot,
    SignatureSnapshotClaim,
    TechnicalConclusion,
    check_rendered_pdf,
    check_template_supported,
    parse_qualification_snapshot,
    qualification_snapshot_hash,
    render_qualification_pdf,
)
from traceq.rounds.store import REPORT_EXPORTS


class Refused(ValueError):
    """Input validation failed for Qualification Report approval (422)."""


@dataclass(frozen=True)
class QualificationExport:
    id: int
    execution_id: int
    revision_number: int
    at: datetime
    actor: audit.Actor
    technical_conclusion: TechnicalConclusion
    conclusion_note: str | None
    next_requalification_date: date | None
    approval_note: str
    snapshot_hash: str
    pdf_sha256: str
    template_version: str
    typst_version: str
    recomputed_snapshot_hash: str
    """``qualification_snapshot_hash`` of the stored snapshot: differs from ``snapshot_hash``
    when the snapshot was altered after the export."""
    claimed_content_hash: str | None
    """The signature ``content_hash`` the stored snapshot itself claims; ``None`` when it
    claims no Electronic Signature."""


def compute_conclusion(copy: ExecutionCopy) -> TechnicalConclusion:
    """Determines technical conclusion from ``ExecutionCopy``:
    - ``not_qualified`` if any Test Step row has no attempts or its latest attempt failed;
    - ``qualified_with_deviations`` if all Test Step rows passed and ``len(deviations) > 0``;
    - ``qualified`` if all Test Step rows passed and ``len(deviations) == 0``.
    """
    for row in copy.rows:
        if row.kind != "test_step":
            continue
        if not row.attempts or not row.attempts[-1].versions:
            return "not_qualified"
        if row.attempts[-1].versions[-1].verdict == "fail":
            return "not_qualified"
    if len(copy.deviations) > 0:
        return "qualified_with_deviations"
    return "qualified"


def compute_counts(copy: ExecutionCopy) -> QualificationCounts:
    """Computes separate counts for IQ, OQ, IQ/OQ (Belum Dipisah), and Vendor Reference."""
    iq_total = iq_passed = iq_failed = 0
    oq_total = oq_passed = oq_failed = 0
    unsplit_total = unsplit_passed = unsplit_failed = 0
    vendor_count = 0

    for row in copy.rows:
        if row.kind == "vendor_reference":
            vendor_count += 1
            continue
        stage = row.test_step.stage if row.test_step is not None else None
        verdict = (
            row.attempts[-1].versions[-1].verdict
            if row.attempts and row.attempts[-1].versions
            else "fail"
        )
        passed = verdict == "pass"
        if stage == "IQ":
            iq_total += 1
            if passed:
                iq_passed += 1
            else:
                iq_failed += 1
        elif stage == "OQ":
            oq_total += 1
            if passed:
                oq_passed += 1
            else:
                oq_failed += 1
        else:
            unsplit_total += 1
            if passed:
                unsplit_passed += 1
            else:
                unsplit_failed += 1

    return QualificationCounts(
        iq_total=iq_total,
        iq_passed=iq_passed,
        iq_failed=iq_failed,
        oq_total=oq_total,
        oq_passed=oq_passed,
        oq_failed=oq_failed,
        unsplit_total=unsplit_total,
        unsplit_passed=unsplit_passed,
        unsplit_failed=unsplit_failed,
        vendor_reference_count=vendor_count,
        total_rows=len(copy.rows),
        total_deviations=len(copy.deviations),
    )


def _same_actor(a: Author, actor: audit.Actor) -> bool:
    return (a.subject, a.issuer) == (actor.subject, actor.issuer)


def check_sod(copy: ExecutionCopy, actor: audit.Actor) -> None:
    """Enforces Separation of Duties for Qualification Report approval (409 on conflict).

    Rejects: Performer of any attempt or version, Completer, Investigation author,
    manual Deviation opener, Deviation submitter, and Witness.
    """
    if _same_actor(copy.completer, actor):
        raise lifecycle.Conflict(
            f"{actor.name} completed Execution {copy.execution_id}: an Approver cannot approve"
            " their own completed Execution"
        )
    for row in copy.rows:
        for att in row.attempts:
            if _same_actor(att.performer, actor):
                raise lifecycle.Conflict(
                    f"{actor.name} recorded attempt #{att.attempt_number} on {row.requirement}:"
                    " a Performer cannot approve the Qualification Report"
                )
            for ver in att.versions:
                if _same_actor(ver.performer, actor):
                    raise lifecycle.Conflict(
                        f"{actor.name} recorded version {ver.version} of attempt"
                        f" #{att.attempt_number} on {row.requirement}: a Performer cannot approve"
                        " the Qualification Report"
                    )
                for wit in ver.witness_confirmations:
                    if _same_actor(wit.witness, actor):
                        raise lifecycle.Conflict(
                            f"{actor.name} witnessed attempt #{att.attempt_number} on"
                            f" {row.requirement}: a Witness cannot approve the Qualification Report"
                        )
    for dev in copy.deviations:
        if dev.cause == "manual" and _same_actor(dev.opener, actor):
            raise lifecycle.Conflict(
                f"{actor.name} opened manual Deviation #{dev.deviation_number}: cannot approve"
                " the Qualification Report"
            )
        for inv in dev.investigations:
            if _same_actor(inv.actor, actor):
                raise lifecycle.Conflict(
                    f"{actor.name} authored an Investigation on Deviation #{dev.deviation_number}:"
                    " cannot approve the Qualification Report"
                )
        for ev in dev.events:
            if ev.event == "submitted" and _same_actor(ev.actor, actor):
                raise lifecycle.Conflict(
                    f"{actor.name} submitted Deviation #{dev.deviation_number}: cannot approve"
                    " the Qualification Report"
                )


def _export_of(m: RowMapping) -> QualificationExport:
    snap = QualificationReportSnapshot.model_validate(m["snapshot_json"])
    stored = parse_qualification_snapshot(m["snapshot_json"], str(m["template_version"]))
    return QualificationExport(
        id=int(m["id"]),
        execution_id=int(m["execution_id"]),
        revision_number=snap.revision_number,
        at=m["at"],
        actor=audit.actor_of_row(m),
        technical_conclusion=snap.technical_conclusion,
        conclusion_note=snap.conclusion_note,
        next_requalification_date=snap.next_requalification_date,
        approval_note=snap.approval_note,
        snapshot_hash=str(m["snapshot_hash"]),
        pdf_sha256=str(m["pdf_sha256"]),
        template_version=str(m["template_version"]),
        typst_version=str(m["typst_version"]),
        recomputed_snapshot_hash=qualification_snapshot_hash(stored),
        claimed_content_hash=(
            None if snap.electronic_signature is None else snap.electronic_signature.content_hash
        ),
    )


def signature_verified(
    export: QualificationExport, sig: audit.ElectronicSignature | None
) -> bool | None:
    """Whether the signature of ``export`` still matches what was signed: its ``content_hash``
    is the digest of its stored ``content_payload``, and the stored snapshot still hashes to
    ``snapshot_hash`` and claims that same ``content_hash``. ``None`` when nothing to recompute
    from (no signature, or none with a stored payload)."""
    if sig is None or sig.content_payload is None:
        return None
    return (
        audit.verify_signature(sig, digest(sig.content_payload))
        and export.recomputed_snapshot_hash == export.snapshot_hash
        and export.claimed_content_hash == sig.content_hash
    )


def exports_of(session: Session, execution_id: int) -> list[QualificationExport]:
    """Every Qualification Report export of ``execution_id``, oldest first."""
    return [
        _export_of(m)
        for m in session.execute(
            select(REPORT_EXPORTS)
            .where(
                REPORT_EXPORTS.c.execution_id == execution_id,
                REPORT_EXPORTS.c.report_kind == "qualification",
            )
            .order_by(REPORT_EXPORTS.c.id)
        ).mappings()
    ]


def get_completed_for_run(
    session: Session, run_id: str
) -> tuple[lifecycle.Execution, Completion, list[QualificationExport]]:
    """Loads completed Execution, Completion, and Qualification exports for ``run_id``."""
    proto = assembly_lifecycle.latest_of_run(session, run_id)
    if proto is None:
        raise lifecycle.NotFound(f"no Protocol was started from run {run_id}")
    ex = lifecycle.of_protocol(session, proto.id)
    if ex is None or ex.status != "completed":
        raise lifecycle.NotFound(f"no completed Execution for run {run_id}")
    comp = completion.get_completion(session, ex.id)
    if comp is None:
        raise lifecycle.NotFound(f"no completion record for Execution {ex.id}")
    return ex, comp, exports_of(session, ex.id)


def _stage_label(kind: str, stage: str | None) -> str:
    if kind == "vendor_reference":
        return "Vendor Reference"
    if stage in ("IQ", "OQ"):
        return stage
    return "IQ/OQ (Belum Dipisah)"


def _build_substance(
    *,
    comp: Completion,
    revision_number: int,
    conclusion: TechnicalConclusion,
    conclusion_note: str | None,
    next_requalification_date: date | None,
) -> tuple[
    QualificationCounts,
    tuple[QualificationReportRow, ...],
    tuple[QualificationReportDeviation, ...],
    dict[str, Any],
]:
    copy = comp.copy
    counts = compute_counts(copy)
    rows: list[QualificationReportRow] = []
    for r in copy.rows:
        stage = r.test_step.stage if r.test_step is not None else None
        witness_required = r.test_step.witness_required if r.test_step is not None else False
        latest_verdict: str | None = None
        witness_names: tuple[str, ...] = ()
        if r.attempts and r.attempts[-1].versions:
            latest_ver = r.attempts[-1].versions[-1]
            latest_verdict = latest_ver.verdict
            witness_names = tuple(
                w.witness.name for w in latest_ver.witness_confirmations if not w.voided
            )
        rows.append(
            QualificationReportRow(
                requirement=r.requirement,
                text=r.text,
                kind=r.kind,
                stage_label=_stage_label(r.kind, stage),
                witness_required=witness_required,
                latest_verdict=latest_verdict,
                attempt_count=len(r.attempts),
                witness_names=witness_names,
            )
        )
    devs = tuple(
        QualificationReportDeviation(
            deviation_number=d.deviation_number,
            requirement=d.requirement,
            cause=d.cause,
            deviation_class=d.deviation_class,
            status=d.status,
            description=d.description,
        )
        for d in copy.deviations
    )
    rows_tuple = tuple(rows)
    payload: dict[str, Any] = {
        "equipment": copy.equipment,
        "run_id": copy.run_id,
        "protocol_id": copy.protocol_id,
        "execution_id": copy.execution_id,
        "revision_number": revision_number,
        "protocol_submission_hash": copy.submission_hash,
        "execution_copy_hash": comp.copy_hash,
        "completed_at": copy.completed_at.isoformat(),
        "completer_name": copy.completer.name,
        "technical_conclusion": conclusion,
        "conclusion_note": conclusion_note,
        "next_requalification_date": (
            None if next_requalification_date is None else next_requalification_date.isoformat()
        ),
        "counts": counts.model_dump(mode="json"),
        "rows": [r.model_dump(mode="json") for r in rows_tuple],
        "deviations": [d.model_dump(mode="json") for d in devs],
    }
    return counts, rows_tuple, devs, payload


def _build_snapshot(
    *,
    generated_at: datetime,
    comp: Completion,
    actor: audit.Actor,
    revision_number: int,
    conclusion: TechnicalConclusion,
    conclusion_note: str | None,
    next_requalification_date: date | None,
    counts: QualificationCounts,
    rows: tuple[QualificationReportRow, ...],
    devs: tuple[QualificationReportDeviation, ...],
    approval_note: str,
    electronic_signature: SignatureSnapshotClaim | None,
) -> QualificationReportSnapshot:
    copy = comp.copy
    return QualificationReportSnapshot(
        generated_at=generated_at,
        equipment=copy.equipment,
        run_id=copy.run_id,
        protocol_id=copy.protocol_id,
        execution_id=copy.execution_id,
        revision_number=revision_number,
        protocol_submission_hash=copy.submission_hash,
        execution_copy_hash=comp.copy_hash,
        completed_at=copy.completed_at,
        completer_name=copy.completer.name,
        approver_name=actor.name,
        approver_subject=actor.subject,
        approver_issuer=actor.issuer,
        approval_note=approval_note,
        technical_conclusion=conclusion,
        conclusion_note=conclusion_note,
        next_requalification_date=next_requalification_date,
        counts=counts,
        rows=rows,
        deviations=devs,
        electronic_signature=electronic_signature,
    )


def approve_qualification_report(
    session: Session,
    actor: audit.Actor,
    execution_id: int,
    *,
    conclusion_note: str | None = None,
    next_requalification_date: date | None = None,
    expected_revision_number: int | None = None,
    expected_execution_copy_hash: str | None = None,
    auth_time: datetime | None,
    jti: str | None,
    is_demo: bool = False,
) -> tuple[Completion, list[QualificationExport]]:
    """Approves a Qualification Report for a completed Execution, creating an immutable export.
    Signs it: ``SignatureAuthRequired`` without a fresh ``auth_time`` and ``jti``, before anything
    is written."""
    auth_time, jti = audit.require_signing_claims(auth_time, jti)
    lifecycle.lock_execution(session, execution_id)
    ex = lifecycle.get(session, execution_id)
    if ex is None:
        raise lifecycle.NotFound(f"no Execution {execution_id}")
    if ex.status != "completed":
        raise lifecycle.Conflict(
            f"Execution {execution_id} is {ex.status}: Qualification Report requires a completed"
            " Execution"
        )
    comp = completion.get_completion(session, execution_id)
    if comp is None:
        raise lifecycle.NotFound(f"no completion record for Execution {execution_id}")

    if expected_execution_copy_hash is not None and comp.copy_hash != expected_execution_copy_hash:
        raise lifecycle.Conflict(
            f"Execution {execution_id} copy hash mismatch: reload the Qualification Report"
        )

    check_sod(comp.copy, actor)
    conclusion = compute_conclusion(comp.copy)

    db_now_raw: Any = session.execute(select(text("date_trunc('second', now())"))).scalar_one()
    db_now = (
        db_now_raw.replace(tzinfo=UTC) if db_now_raw.tzinfo is None else db_now_raw.astimezone(UTC)
    )
    db_utc_date = db_now.date()

    if next_requalification_date is not None:
        if conclusion == "not_qualified":
            raise Refused(
                "next_requalification_date cannot be set when technical_conclusion is not_qualified"
            )
        if next_requalification_date < db_utc_date:
            raise Refused("next_requalification_date cannot be before today's UTC date")

    clean_note = conclusion_note.strip() if conclusion_note is not None else None
    if clean_note == "":
        clean_note = None

    existing = exports_of(session, execution_id)
    revision_number = len(existing) + 1
    if expected_revision_number is not None and revision_number != expected_revision_number:
        raise lifecycle.Conflict(
            f"Qualification Report revision changed (expected {expected_revision_number}, "
            f"current next is {revision_number}): reload and try again"
        )

    counts, rows, devs, substance_payload = _build_substance(
        comp=comp,
        revision_number=revision_number,
        conclusion=conclusion,
        conclusion_note=clean_note,
        next_requalification_date=next_requalification_date,
    )
    content_hash = digest(substance_payload)
    approval_note = audit.DEMO_SIGNATURE_LABEL if is_demo else audit.ELECTRONIC_SIGNATURE_LABEL
    sig_claim = SignatureSnapshotClaim(
        record_type="qualification_report",
        signature_meaning="approved",
        content_hash=content_hash,
        hash_scheme_version=1,
        signer_subject=actor.subject,
        signer_issuer=actor.issuer,
        signer_name=actor.name,
        auth_time=auth_time,
        signed_at=db_now,
        is_demo=is_demo,
        label=approval_note,
    )

    snapshot = _build_snapshot(
        generated_at=db_now,
        comp=comp,
        actor=actor,
        revision_number=revision_number,
        conclusion=conclusion,
        conclusion_note=clean_note,
        next_requalification_date=next_requalification_date,
        counts=counts,
        rows=rows,
        devs=devs,
        approval_note=approval_note,
        electronic_signature=sig_claim,
    )
    pdf_bytes = render_qualification_pdf(snapshot, template_version=QUALIFICATION_TEMPLATE_VERSION)
    snap_hash = qualification_snapshot_hash(snapshot)
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()

    inserted = (
        session.execute(
            insert(REPORT_EXPORTS)
            .values(
                round_id=None,
                execution_id=execution_id,
                report_kind="qualification",
                subject=actor.subject,
                issuer=actor.issuer,
                name=actor.name,
                snapshot_json=snapshot.model_dump(mode="json"),
                snapshot_hash=snap_hash,
                pdf_sha256=pdf_sha,
                template_version=QUALIFICATION_TEMPLATE_VERSION,
                typst_version=TYPST_VERSION,
            )
            .returning(*REPORT_EXPORTS.c)
        )
        .mappings()
        .one()
    )
    export = _export_of(inserted)
    sig = audit.record_signature(
        session,
        actor,
        record_type="qualification_report",
        signature_meaning="approved",
        content_hash=content_hash,
        auth_time=auth_time,
        jti=jti,
        is_demo=is_demo,
        report_export_id=export.id,
        content_payload=substance_payload,
    )
    new_audit: dict[str, audit.JsonValue] = {
        "export_id": export.id,
        "execution_id": execution_id,
        "revision_number": revision_number,
        "report_kind": "qualification",
        "technical_conclusion": conclusion,
        "conclusion_note": clean_note,
        "next_requalification_date": (
            None if next_requalification_date is None else next_requalification_date.isoformat()
        ),
        "approval_note": approval_note,
        "snapshot_hash": snap_hash,
        "pdf_sha256": pdf_sha,
        "template_version": QUALIFICATION_TEMPLATE_VERSION,
        "typst_version": TYPST_VERSION,
        "signature_id": sig.id,
    }
    audit.append(
        session,
        actor,
        "qualification report approved",
        "report_export",
        str(export.id),
        new=new_audit,
    )
    return comp, [*existing, export]


def render_stored_qualification_pdf(
    session: Session, execution_id: int, export_id: int
) -> tuple[bytes, int]:
    """Re-renders a stored Qualification Report PDF from ``snapshot_json`` without any DB writes.

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
                REPORT_EXPORTS.c.execution_id == execution_id,
                REPORT_EXPORTS.c.report_kind == "qualification",
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise lifecycle.NotFound(
            f"no qualification report export {export_id} for Execution {execution_id}"
        )
    template_version = str(row["template_version"])
    check_template_supported(template_version, QUALIFICATION_TEMPLATE_VERSIONS)
    snapshot = parse_qualification_snapshot(row["snapshot_json"], template_version)
    pdf_bytes = render_qualification_pdf(snapshot, template_version=template_version)
    check_rendered_pdf(
        pdf_bytes, str(row["pdf_sha256"]), stored_typst_version=str(row["typst_version"])
    )
    return pdf_bytes, snapshot.revision_number
