"""World data schema (design section 4 and 6).

The world is YAML validated by these models. Every Acceptance Criterion and technical
limit carries a :class:`Source` (design principle 5). Values are copied from a cited
public source with a verbatim quote, or recorded as a site decision with a written
rationale (principle 7). A skeleton may hold ``pending`` values and sources; a frozen
dataset may not (:meth:`Equipment.pending`).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from traceq_dataset.dates import Offset

QUOTE_MAX = 200  # design section 9, "Citations"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Sources and values -------------------------------------------------------------


class SourceKind(StrEnum):
    REGULATION = "regulation"  # CPOB / PerBPOM 7/2024, EU GMP, WHO, PIC/S, Permenaker
    PHARMACOPOEIA = "pharmacopoeia"  # Farmakope Indonesia, USP
    LITERATURE = "literature"  # published papers, textbooks, trade press without brands
    VENDOR_SPEC = "vendor_spec"  # the fictional vendor's own spec, derived with rationale
    SITE_DECISION = "site_decision"  # a fictional plant choice, with rationale
    PENDING = "pending"  # skeleton only: not filled yet


QUOTED_KINDS = frozenset({SourceKind.REGULATION, SourceKind.PHARMACOPOEIA, SourceKind.LITERATURE})
"""Kinds whose value must appear in a verbatim quote from a public URL."""


class Source(Model):
    """Where a value comes from.

    Quoted kinds need ``url``, ``quote`` and ``accessed``; the quote is checked against
    the live page by ``scripts/verify_quotes.py``. Site decisions and fictional vendor
    specs need a ``rationale`` and may add a quote showing the value is realistic.

    A quote proves only that the text exists at the URL. A site decision's value is a
    judgement, so it records who drafted it and stays unreviewed (blocking freeze, see
    :meth:`Equipment.unreviewed`) until a human signs it off.
    """

    kind: SourceKind
    ref: str = Field(
        "", description="Citation, e.g. 'PerBPOM 7/2024 Ch. 12 §12.14' or a DOI with section."
    )
    url: HttpUrl | None = None
    quote: str | None = Field(None, max_length=QUOTE_MAX)
    accessed: dt.date | None = None
    rationale: str | None = None
    note: str | None = None
    drafted_by: Literal["llm", "human"] | None = Field(
        None, description="Who chose a judged value (site decision / vendor spec)."
    )
    reviewed_by: Literal["owner", "practitioner"] | None = Field(
        None, description="Human sign-off of a judged value; required before freeze."
    )

    @model_validator(mode="after")
    def _complete(self) -> Source:
        if self.kind is SourceKind.PENDING:
            return self
        if len(self.ref) < 3:
            raise ValueError("ref needs a citation")
        if self.kind in QUOTED_KINDS:
            missing = [f for f in ("url", "quote", "accessed") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"{self.kind} source needs {', '.join(missing)}")
            if self.drafted_by or self.reviewed_by:
                raise ValueError(f"{self.kind} values are copied, not drafted or reviewed")
        else:
            if not self.rationale:
                raise ValueError(f"{self.kind} source needs a rationale")
            if self.drafted_by is None:
                raise ValueError(f"{self.kind} source needs drafted_by")
        if (self.url is None) != (self.quote is None):
            raise ValueError("url and quote go together")
        return self

    @property
    def judged(self) -> bool:
        """A value chosen by someone, not copied from a quote."""
        return self.kind in {SourceKind.SITE_DECISION, SourceKind.VENDOR_SPEC}


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


class PendingSpec(Model):
    """Skeleton only: the value is not filled yet. ``expected`` is the spec type it becomes."""

    type: Literal["pending"] = "pending"
    expected: Literal["range", "one_of", "present"]
    unit: str | None = None


Spec = Annotated[RangeSpec | OneOfSpec | PresentSpec | PendingSpec, Field(discriminator="type")]


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


class PendingObs(Model):
    """Skeleton only: the observed value follows once the URS value is filled."""

    type: Literal["pending"] = "pending"
    expected: Literal["number", "range", "text", "present"]
    unit: str | None = None


Observation = Annotated[
    NumberObs | RangeObs | TextObs | PresentObs | PendingObs, Field(discriminator="type")
]


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
    section: str = Field("", description="URS section heading, e.g. '4. Kinerja'.")
    text: str = Field(
        description="Requirement sentence; '{min}', '{max}', '{allowed}' are filled from spec."
    )
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
    intended_coverage: CoverageClass = Field(
        description="Design intent. Once nothing is pending, the decision table must agree."
    )
    superseded_spec: Spec | None = Field(
        None, description="Value in the superseded URS revision (scenario: rev 0 -> rev 1)."
    )

    @model_validator(mode="after")
    def _value_in_quote(self) -> Requirement:
        """A quoted source must contain the numbers it is cited for (design section 9)."""
        if self.source.kind in QUOTED_KINDS and isinstance(self.spec, RangeSpec):
            quote = self.source.quote or ""
            for bound in (self.spec.min, self.spec.max):
                if bound is not None and not any(f in quote for f in number_forms(bound)):
                    raise ValueError(f"{self.id}: value {bound:g} not found in source quote")
        return self


def number_forms(value: float) -> set[str]:
    """Ways a number may be written in an English or Indonesian source."""
    text = f"{value:g}"
    forms = {text, text.replace(".", ",")}
    if value == int(value) and abs(value) >= 1000:
        n = int(value)
        forms |= {f"{n:,}", f"{n:,}".replace(",", "."), f"{n:,}".replace(",", " ")}
    return forms


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

    __test__ = False  # not a pytest class

    step: str
    protocol: str = Field(description="VendorProtocol.doc_id")
    requirement: str
    observed: Observation
    recorded_result: Literal["pass", "fail"]
    description: str | None = Field(
        None, description="Test as written in the protocol, in the protocol's language."
    )
    acceptance: Spec | None = Field(
        None,
        description="The protocol's Acceptance Criterion when it is not the URS spec, e.g. a "
        "vendor FAT that tests a narrower range (Coverage `partial`, not a defect).",
    )


class DesignEvidence(Model):
    """A design or delivered-item fact (datasheet, material certificate, nameplate)."""

    doc_id: str
    requirement: str
    observed: Observation


# --- Documents ----------------------------------------------------------------------


class Document(Model):
    """One revision of a document the renderer produces (design section 5).

    Content comes from the rest of the world data; this holds what only the document
    itself has: number, revision, issue date and signatories.
    """

    id: str = Field(description="Document number, e.g. 'URS-TP201'; a FAT is its protocol id.")
    rev: int = Field(ge=0)
    type: Literal["urs", "fat"]
    title: str = Field("", description="Subtitle, e.g. 'Mechanical' for a FAT protocol.")
    language: Literal["id", "en"]
    issued_on: Offset
    prepared_by: str = Field(description="Person id.")
    checked_by: str | None = Field(None, description="Person id.")
    approved_by: str | None = Field(
        None, description="Person id. For a FAT: site approval, dated by the protocol."
    )
    executed_by: str | None = Field(None, description="Person id (FAT only).")
    witnessed_by: str | None = Field(None, description="Person id (FAT only).")
    change_note: str = Field("", description="Revision history entry; empty for rev 0.")

    ROLES: ClassVar = ("prepared_by", "checked_by", "approved_by", "executed_by", "witnessed_by")


# --- Equipment (one world-data file) ------------------------------------------------


class Scenario(Model):
    """A planted defect or test situation (design section 7, v0 scenarios)."""

    id: str = Field(pattern=r"^S\d+$")
    summary: str
    reference: str = Field("", description="Rule it breaks, e.g. 'CPOB 10.8'.")
    targets: tuple[str, ...] = Field(
        description="Requirement ids, protocol doc ids or test steps it is planted in."
    )
    note: str | None = None


class Equipment(Model):
    """All world data for one Equipment item: the content of one ``world/*.yaml`` file."""

    tag: str = Field(pattern=r"^[A-Z]+-\d{3}$")
    name: str
    serial_no: str | None = Field(None, description="True serial number, as on the nameplate.")
    site: str
    vendor: Vendor
    people: tuple[Person, ...]
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    protocols: tuple[VendorProtocol, ...] = ()
    tests: tuple[TestEvidence, ...] = ()
    designs: tuple[DesignEvidence, ...] = ()
    scenarios: tuple[Scenario, ...] = ()
    documents: tuple[Document, ...] = ()

    @model_validator(mode="after")
    def _references(self) -> Equipment:
        errors: list[str] = []
        prefix = f"URS-{self.tag.replace('-', '')}-"

        def dupes(ids: list[str], what: str) -> None:
            errors.extend(f"duplicate {what} {i}" for i, n in Counter(ids).items() if n > 1)

        req_ids = [r.id for r in self.requirements]
        dupes(req_ids, "requirement")
        dupes([p.id for p in self.people], "person")
        dupes([p.doc_id for p in self.protocols], "protocol")
        dupes([t.step for t in self.tests], "test step")
        dupes([s.id for s in self.scenarios], "scenario")
        dupes([f"{d.id} rev {d.rev}" for d in self.documents], "document")
        errors += [f"{r} does not start with {prefix}" for r in req_ids if not r.startswith(prefix)]

        reqs, protocols = set(req_ids), {p.doc_id for p in self.protocols}
        employers = {self.site, self.vendor.id}
        errors += [
            f"{p.id}: unknown employer {p.employer}"
            for p in self.people
            if p.employer not in employers
        ]
        errors += [
            f"{p.doc_id}: vendor {p.vendor} is not {self.vendor.id}"
            for p in self.protocols
            if p.vendor != self.vendor.id
        ]
        for t in self.tests:
            if t.requirement not in reqs:
                errors.append(f"{t.step}: unknown requirement {t.requirement}")
            if t.protocol not in protocols:
                errors.append(f"{t.step}: unknown protocol {t.protocol}")
        errors += [
            f"{d.doc_id}: unknown requirement {d.requirement}"
            for d in self.designs
            if d.requirement not in reqs
        ]
        people = {p.id for p in self.people}
        by_protocol = {p.doc_id: p for p in self.protocols}
        for d in self.documents:
            name = f"{d.id} rev {d.rev}"
            for role in Document.ROLES:
                pid = getattr(d, role)
                if pid is not None and pid not in people:
                    errors.append(f"{name}: unknown {role} {pid}")
            if d.rev > 0 and not d.change_note:
                errors.append(f"{name}: needs a change_note")
            if d.type == "urs":
                errors += [
                    f"{name}: URS needs {r}"
                    for r in ("checked_by", "approved_by")
                    if not getattr(d, r)
                ]
                errors += [
                    f"{name}: URS has no {r}"
                    for r in ("executed_by", "witnessed_by")
                    if getattr(d, r)
                ]
            else:
                protocol = by_protocol.get(d.id)
                if protocol is None or protocol.stage is not Stage.FAT:
                    errors.append(f"{name}: no FAT protocol {d.id}")
                    continue
                errors += [
                    f"{name}: FAT needs {r}"
                    for r in ("executed_by", "witnessed_by")
                    if not getattr(d, r)
                ]
                if (d.approved_by is None) != (protocol.site_approved_on is None):
                    errors.append(f"{name}: approved_by must match the protocol's site approval")
        known = reqs | protocols | {t.step for t in self.tests} | {d.doc_id for d in self.designs}
        for s in self.scenarios:
            errors += [f"{s.id}: unknown target {x}" for x in s.targets if x not in known]
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def pending(self) -> list[str]:
        """Paths still to be filled. A frozen dataset has none."""
        out: list[str] = []
        for r in self.requirements:
            if isinstance(r.spec, PendingSpec):
                out.append(f"{r.id}.spec")
            if isinstance(r.superseded_spec, PendingSpec):
                out.append(f"{r.id}.superseded_spec")
            if r.source.kind is SourceKind.PENDING:
                out.append(f"{r.id}.source")
        out += [f"{t.step}.observed" for t in self.tests if isinstance(t.observed, PendingObs)]
        out += [f"{d.doc_id}.observed" for d in self.designs if isinstance(d.observed, PendingObs)]
        return out

    def unreviewed(self) -> list[Requirement]:
        """Judged values without human sign-off. A frozen dataset has none."""
        return [r for r in self.requirements if r.source.judged and r.source.reviewed_by is None]
