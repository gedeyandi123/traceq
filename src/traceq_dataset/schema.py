"""World data schema (design section 4 and 6).

The world is hand-written YAML validated by these models. Every Acceptance Criterion
and technical limit carries a :class:`Source` (design principle 5).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traceq_dataset.dates import Offset


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Sources and values -------------------------------------------------------------


class SourceKind(StrEnum):
    REGULATION = "regulation"  # CPOB / PerBPOM 7/2024, EU GMP, WHO, PIC/S
    PHARMACOPOEIA = "pharmacopoeia"  # Farmakope Indonesia, USP
    LITERATURE = "literature"  # published papers, textbooks
    VENDOR_SPEC = "vendor_spec"  # the fictional vendor's own published spec
    SITE_DECISION = "site_decision"  # a fictional plant choice, with rationale


class Source(Model):
    kind: SourceKind
    ref: str = Field(min_length=3, description="Citation, e.g. 'CPOB 12.29b' or 'VMP §5.2'.")
    note: str | None = None


class RangeSpec(Model):
    """A numeric requirement; either bound may be open."""

    type: Literal["range"] = "range"
    min: float | None = None
    max: float | None = None
    unit: str

    @model_validator(mode="after")
    def _bounds(self) -> RangeSpec:
        if self.min is None and self.max is None:
            raise ValueError("range needs at least one bound")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min {self.min} > max {self.max}")
        return self


class OneOfSpec(Model):
    """A categorical requirement, e.g. product-contact material in {'SS 316L'}."""

    type: Literal["one_of"] = "one_of"
    allowed: tuple[str, ...] = Field(min_length=1)


class PresentSpec(Model):
    """A feature that must exist, e.g. an audit trail on the HMI."""

    type: Literal["present"] = "present"


Spec = Annotated[RangeSpec | OneOfSpec | PresentSpec, Field(discriminator="type")]


class NumberObs(Model):
    type: Literal["number"] = "number"
    value: float
    unit: str


class RangeObs(Model):
    """A tested range, e.g. FAT ran the turret from 10 to 60 rpm."""

    type: Literal["range"] = "range"
    min: float
    max: float
    unit: str


class TextObs(Model):
    type: Literal["text"] = "text"
    value: str


class PresentObs(Model):
    type: Literal["present"] = "present"
    value: bool


Observation = Annotated[NumberObs | RangeObs | TextObs | PresentObs, Field(discriminator="type")]


# --- Parties ------------------------------------------------------------------------


class Persona(StrEnum):
    QUALIFICATION_ENGINEER = "qualification_engineer"
    QUALIFICATION_SUPERVISOR = "qualification_supervisor"
    QA_APPROVER = "qa_approver"
    WITNESS = "witness"
    SYSTEM_ADMIN = "system_admin"
    VENDOR_ENGINEER = "vendor_engineer"


class Person(Model):
    id: str
    name: str
    persona: Persona
    employer: str = Field(description="Site or vendor id.")


class VendorAssessment(Model):
    """CPOB Ch. 12: the site may rely on vendor results only within the assessed scope."""

    assessed_on: Offset
    scope: frozenset[str] = Field(description="Requirement scopes covered, e.g. 'mechanical'.")


class Vendor(Model):
    id: str
    name: str
    assessment: VendorAssessment | None = None


# --- Requirements and Evidence ------------------------------------------------------


class CoverageClass(StrEnum):
    COVERED_BY_VENDOR = "covered_by_vendor"
    PARTIAL = "partial"
    SITE_ONLY = "site_only"
    GAP = "gap"
    CONFLICT = "conflict"


class Requirement(Model):
    id: str = Field(pattern=r"^URS-[A-Z0-9]+-\d{3}$")
    text: str
    param: str
    spec: Spec
    source: Source
    scope: str = Field(description="Matched against VendorAssessment.scope.")
    critical: bool = False
    site_only: bool = Field(False, description="Cannot be tested by the vendor at all.")
    transport_sensitive: bool = Field(
        True, description="Could transport/installation change it (CPOB 12.24)?"
    )
    also_valid: tuple[CoverageClass, ...] = ()


class Stage(StrEnum):
    FAT = "FAT"
    SAT = "SAT"


class VendorProtocol(Model):
    """A FAT or SAT protocol; CPOB 12.14 requires site approval before execution."""

    doc_id: str
    stage: Stage
    vendor: str
    site_approved_on: Offset | None
    executed_on: Offset


class TestEvidence(Model):
    """One executed FAT/SAT step that addresses a requirement."""

    step: str
    protocol: str = Field(description="VendorProtocol.doc_id")
    requirement: str
    observed: Observation
    recorded_result: Literal["pass", "fail"]


class DesignEvidence(Model):
    """A design or delivered-item fact (datasheet, material certificate, nameplate)."""

    doc_id: str
    requirement: str
    observed: Observation
