"""Append-only Electronic Signatures store and honest dynamic labelling (Step 8, #333, #334).

Sibling to ``traceq.identity`` (ADR 0008): accepts ``audit.Actor`` and primitives only, never
imports ``traceq.identity``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    RowMapping,
    Table,
    Text,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from traceq.audit.trail import Actor, JsonValue

type RecordType = Literal[
    "protocol_submission",
    "protocol_approval",
    "deviation_closure",
    "witness_confirmation",
    "qualification_report",
]
type SignatureMeaning = Literal["prepared", "approved", "witnessed"]

UNSIGNED_STATUS_LABEL = "a recorded status, not an Electronic Signature"
DEMO_SIGNATURE_LABEL = (
    "Demo signature — demo identity without password re-authentication, not an Electronic Signature"
)
ELECTRONIC_SIGNATURE_LABEL = (
    "Electronic Signature — designed for 21 CFR Part 11, CPOB Annex 7, "
    "and draft EU GMP Annex 11 (2025), not validated (ADR 0007)"
)

_REPLAY_CONSTRAINT = "electronic_signatures_signer_issuer_jti_key"

_TABLE = Table(
    "electronic_signatures",
    MetaData(),
    Column("id", BigInteger, primary_key=True),
    Column("at", DateTime(timezone=True)),
    Column("protocol_event_id", BigInteger),
    Column("deviation_event_id", BigInteger),
    Column("witness_confirmation_id", BigInteger),
    Column("report_export_id", BigInteger),
    Column("record_type", Text),
    Column("signature_meaning", Text),
    Column("content_hash", Text),
    Column("hash_scheme_version", Integer),
    Column("content_payload", JSONB(none_as_null=True)),
    Column("signer_subject", Text),
    Column("signer_issuer", Text),
    Column("signer_name", Text),
    Column("auth_time", DateTime(timezone=True)),
    Column("jti", Text),
    Column("is_demo", Boolean),
)


class SignatureReplayConflict(Exception):
    """Raised when a token's ``(signer_issuer, jti)`` has already signed a record."""


class SignatureAuthRequired(Exception):
    """Raised when a signing action has no ``auth_time`` or no ``jti`` to sign with: the token
    carries no fresh authentication, so the action is refused rather than recorded unsigned
    (ADR 0007)."""


def require_signing_claims(auth_time: datetime | None, jti: str | None) -> tuple[datetime, str]:
    """The ``(auth_time, jti)`` of the signer's token, or ``SignatureAuthRequired`` when either
    is missing. Called before a signing action writes anything, so no event is left unsigned."""
    if auth_time is None:
        raise SignatureAuthRequired("re-authentication required: missing auth_time")
    if jti is None:
        raise SignatureAuthRequired("re-authentication required: missing jti")
    return auth_time, jti


@dataclass(frozen=True)
class ElectronicSignature:
    id: int
    at: datetime
    protocol_event_id: int | None
    deviation_event_id: int | None
    witness_confirmation_id: int | None
    report_export_id: int | None
    record_type: RecordType
    signature_meaning: SignatureMeaning
    content_hash: str
    hash_scheme_version: int
    content_payload: JsonValue
    signer_subject: str
    signer_issuer: str
    signer_name: str
    auth_time: datetime
    jti: str
    is_demo: bool


class ElectronicSignatureView(BaseModel):
    """Public API view of an Electronic Signature binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    at: datetime
    record_type: RecordType
    signature_meaning: SignatureMeaning
    content_hash: str
    hash_scheme_version: int
    signer_subject: str
    signer_issuer: str
    signer_name: str
    auth_time: datetime
    is_demo: bool
    label: str
    verified: bool | None = None
    """``True``: the bound ``content_hash`` matches the hash recomputed from the stored source
    data. ``False``: it does not (the data changed after signing). ``None``: not checked."""


def signature_label(record: ElectronicSignature | None) -> str:
    """Honest dynamic label for a signature record (or absence of one)."""
    if record is None:
        return UNSIGNED_STATUS_LABEL
    if record.is_demo:
        return DEMO_SIGNATURE_LABEL
    return ELECTRONIC_SIGNATURE_LABEL


def verify_signature(record: ElectronicSignature, expected_content_hash: str) -> bool:
    """Return True iff the recorded ``content_hash`` matches ``expected_content_hash``."""
    return record.content_hash == expected_content_hash


def verified_against(
    record: ElectronicSignature | None, recomputed_hash: str | None
) -> bool | None:
    """``verify_signature`` for a record that may be absent and a recompute that may not have
    been made: ``None`` ("not checked") when either is missing."""
    if record is None or recomputed_hash is None:
        return None
    return verify_signature(record, recomputed_hash)


def signature_view(
    record: ElectronicSignature | None,
    *,
    verified: bool | None,
) -> ElectronicSignatureView | None:
    """Convert an ``ElectronicSignature`` into its public API view.

    ``verified`` is the outcome of comparing ``record.content_hash`` with a hash the caller
    recomputed from the source data (``verify_signature``), or ``None`` when no such recompute
    was made: a signature is never reported verified because nothing was compared."""
    if record is None:
        return None
    return ElectronicSignatureView(
        id=record.id,
        at=record.at,
        record_type=record.record_type,
        signature_meaning=record.signature_meaning,
        content_hash=record.content_hash,
        hash_scheme_version=record.hash_scheme_version,
        signer_subject=record.signer_subject,
        signer_issuer=record.signer_issuer,
        signer_name=record.signer_name,
        auth_time=record.auth_time,
        is_demo=record.is_demo,
        label=signature_label(record),
        verified=verified,
    )


def _row_to_signature(m: RowMapping) -> ElectronicSignature:
    return ElectronicSignature(
        id=int(m["id"]),
        at=m["at"],
        protocol_event_id=m["protocol_event_id"],
        deviation_event_id=m["deviation_event_id"],
        witness_confirmation_id=m["witness_confirmation_id"],
        report_export_id=m["report_export_id"],
        record_type=cast(RecordType, m["record_type"]),
        signature_meaning=cast(SignatureMeaning, m["signature_meaning"]),
        content_hash=str(m["content_hash"]),
        hash_scheme_version=int(m["hash_scheme_version"]),
        content_payload=m["content_payload"],
        signer_subject=str(m["signer_subject"]),
        signer_issuer=str(m["signer_issuer"]),
        signer_name=str(m["signer_name"]),
        auth_time=m["auth_time"],
        jti=str(m["jti"]),
        is_demo=bool(m["is_demo"]),
    )


def _is_replay_error(exc: IntegrityError) -> bool:
    orig: Any = exc.orig
    if orig is None:
        return False
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code != "23505":
        return False
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    return constraint == _REPLAY_CONSTRAINT


def record_signature(
    session: Session,
    actor: Actor,
    *,
    record_type: RecordType,
    signature_meaning: SignatureMeaning,
    content_hash: str,
    auth_time: datetime,
    jti: str,
    is_demo: bool,
    protocol_event_id: int | None = None,
    deviation_event_id: int | None = None,
    witness_confirmation_id: int | None = None,
    report_export_id: int | None = None,
    hash_scheme_version: int = 1,
    content_payload: JsonValue = None,
) -> ElectronicSignature:
    """Append an Electronic Signature row in the current transaction.

    Raises ``SignatureReplayConflict`` if ``(signer_issuer, jti)`` was already used.
    """
    try:
        row = session.execute(
            insert(_TABLE)
            .values(
                protocol_event_id=protocol_event_id,
                deviation_event_id=deviation_event_id,
                witness_confirmation_id=witness_confirmation_id,
                report_export_id=report_export_id,
                record_type=record_type,
                signature_meaning=signature_meaning,
                content_hash=content_hash,
                hash_scheme_version=hash_scheme_version,
                content_payload=content_payload,
                signer_subject=actor.subject,
                signer_issuer=actor.issuer,
                signer_name=actor.name,
                auth_time=auth_time,
                jti=jti,
                is_demo=is_demo,
            )
            .returning(*_TABLE.c)
        )
        return _row_to_signature(row.mappings().one())
    except IntegrityError as exc:
        if _is_replay_error(exc):
            raise SignatureReplayConflict(
                "This authentication token has already been used to sign a record; "
                "re-authenticate for a fresh token."
            ) from exc
        raise


def _signatures_by_fk(
    session: Session, column: Column[Any], ids: Sequence[int]
) -> dict[int, ElectronicSignature]:
    if not ids:
        return {}
    rows = session.execute(select(_TABLE).where(column.in_(ids))).mappings()
    return {int(m[column.name]): _row_to_signature(m) for m in rows}


def signatures_by_protocol_events(
    session: Session, event_ids: Sequence[int]
) -> dict[int, ElectronicSignature]:
    return _signatures_by_fk(session, _TABLE.c.protocol_event_id, event_ids)


def signatures_by_deviation_events(
    session: Session, event_ids: Sequence[int]
) -> dict[int, ElectronicSignature]:
    return _signatures_by_fk(session, _TABLE.c.deviation_event_id, event_ids)


def signatures_by_witness_confirmations(
    session: Session, confirmation_ids: Sequence[int]
) -> dict[int, ElectronicSignature]:
    return _signatures_by_fk(session, _TABLE.c.witness_confirmation_id, confirmation_ids)


def signatures_by_report_exports(
    session: Session, export_ids: Sequence[int]
) -> dict[int, ElectronicSignature]:
    return _signatures_by_fk(session, _TABLE.c.report_export_id, export_ids)
