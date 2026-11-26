"""The Audit Trail: who did what to which record, when, and why (ADR 0007, spec #105).

Append-only. The application can add an entry and read entries; Postgres refuses it anything
else (``traceq.db`` migrations). The time is the database clock, never the application's.
"""

from traceq.audit.signatures import (
    DEMO_SIGNATURE_LABEL,
    ELECTRONIC_SIGNATURE_LABEL,
    UNSIGNED_STATUS_LABEL,
    ElectronicSignature,
    ElectronicSignatureView,
    RecordType,
    SignatureMeaning,
    SignatureReplayConflict,
    record_signature,
    signature_label,
    signature_view,
    signatures_by_deviation_events,
    signatures_by_protocol_events,
    signatures_by_report_exports,
    signatures_by_witness_confirmations,
    verified_against,
    verify_signature,
)
from traceq.audit.trail import Actor, Entry, JsonValue, actor_of_row, append, entries

__all__ = [
    "DEMO_SIGNATURE_LABEL",
    "ELECTRONIC_SIGNATURE_LABEL",
    "UNSIGNED_STATUS_LABEL",
    "Actor",
    "ElectronicSignature",
    "ElectronicSignatureView",
    "Entry",
    "JsonValue",
    "RecordType",
    "SignatureMeaning",
    "SignatureReplayConflict",
    "actor_of_row",
    "append",
    "entries",
    "record_signature",
    "signature_label",
    "signature_view",
    "signatures_by_deviation_events",
    "signatures_by_protocol_events",
    "signatures_by_report_exports",
    "signatures_by_witness_confirmations",
    "verified_against",
    "verify_signature",
]
