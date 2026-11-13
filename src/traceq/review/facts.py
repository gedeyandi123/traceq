"""What Pre-review reads from the corpus, each fact with its verified citation.

The rules in ``traceq.review.rules`` decide over these facts only; how they were read (the
LLM, then the citation check) is ``traceq.review.records`` and ``traceq.review.governing``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from traceq.traceability import Citation
from traceq.traceability.coverage import Date

Role = Literal["prepared", "checked", "approved", "executed", "witnessed", "other"]
Operation = Literal["mean", "sum", "difference", "min", "max", "range"]
SiteRule = Literal[
    "signature_name_and_date",
    "vendor_protocol_approved_before_execution",
    "preparer_not_approver",
    "checker_not_approver",
    "performer_not_witness",
]


@dataclass(frozen=True)
class Signature:
    role_printed: str
    role: Role
    site: bool
    name: str
    """As printed; empty when blank."""
    signed: bool
    date: Date
    """``None`` when blank or unreadable."""
    citation: Citation

    @property
    def complete(self) -> bool:
        return bool(self.name.strip()) and self.signed and self.date is not None


@dataclass(frozen=True)
class Calibration:
    """A calibration validity printed on a protocol or a certificate."""

    instrument: str
    valid_until: Date
    citation: Citation


@dataclass(frozen=True)
class InstrumentUse:
    step: str
    instrument: str
    citation: Citation


@dataclass(frozen=True)
class Deviation:
    id: str
    steps: tuple[str, ...]
    citation: Citation


@dataclass(frozen=True)
class Calculation:
    step: str
    operation: Operation
    inputs: tuple[float, ...]
    result: float
    decimals: int
    """Decimal places of the printed result: the rounding the rule tolerates."""
    citation: Citation


@dataclass
class Record:
    """What one qualification record (a protocol and report, a certificate) prints."""

    doc: str
    rev: int
    type: str
    signatures: list[Signature] = field(default_factory=list[Signature])
    calibrations: list[Calibration] = field(default_factory=list[Calibration])
    uses: list[InstrumentUse] = field(default_factory=list[InstrumentUse])
    deviations: list[Deviation] = field(default_factory=list[Deviation])
    calculations: list[Calculation] = field(default_factory=list[Calculation])

    @property
    def vendor_protocol(self) -> bool:
        return self.type in ("fat", "sat")

    def first(self, role: Role) -> Signature | None:
        return next((s for s in self.signatures if s.role == role), None)


@dataclass(frozen=True)
class RequiredDocument:
    """A row of the VMP annex for this Equipment."""

    doc_id: str
    type: str
    """Type code of submission schema version 1 (``iq_protocol``)."""
    stage: Literal["design", "FAT", "SAT", "IQ", "OQ"]
    citation: Citation
