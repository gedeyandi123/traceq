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
    VENDOR_INSPECTOR = "vendor_inspector"  # signs 3.1 material certificates
    LAB_STAFF = "lab_staff"  # calibrates and signs calibration certificates


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


class Organisation(Model):
    """Another party that issues documents, e.g. the calibration lab."""

    id: str
    name: str


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


class CalibrationPoint(Model):
    """One row of a calibration certificate's results table."""

    channel: str | None = Field(
        None, description="Measuring channel, for a system calibrated as one item."
    )
    nominal: float
    reading: float
    uncertainty: float = Field(gt=0, description="Expanded uncertainty (k = 2).")


class CalibrationResults(Model):
    """Readings printed on a calibration certificate. They are not Acceptance Criteria,
    but they are judged numbers (design principle 7): drafted, then reviewed by a human."""

    unit: str
    points: tuple[CalibrationPoint, ...] = Field(min_length=1)
    drafted_by: Literal["llm", "human"]
    reviewed_by: Literal["owner", "practitioner"] | None = None


class CalibrationCertificate(Model):
    """The current calibration certificate of a test instrument. Its ``id`` is the document
    number when the certificate is rendered."""

    id: str = Field(description="Certificate number.")
    lab: str | None = Field(
        None, description="Organisation id of the issuer: a calibration lab or the vendor."
    )
    calibrated_on: Offset
    valid_until: Offset = Field(description="Last day the calibration is valid.")
    results: CalibrationResults | None = None


class Instrument(Model):
    """A calibrated measuring instrument: a site test instrument used in FAT/SAT steps
    (scenario S2: expired calibration), or a measuring system built into the Equipment
    (the press's compression force sensors, calibrated by the vendor)."""

    id: str = Field(description="Site asset tag, e.g. 'TACH-07'.")
    name: str
    serial_no: str
    certificate: CalibrationCertificate


class Correction(Model):
    """A handwritten entry overwritten on paper with no initials, date or reason (S1,
    CPOB 10.8). ``TestEvidence.observed`` is the final value; ``original`` the value
    first written beneath it. Correctly documented corrections follow with the other
    GDP variants."""

    original: Observation


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
    instruments: tuple[str, ...] = Field((), description="Instrument ids used in the step.")
    correction: Correction | None = None

    @model_validator(mode="after")
    def _correction_same_kind(self) -> TestEvidence:
        if self.correction:
            a, b = self.correction.original, self.observed
            if a.type != b.type or getattr(a, "unit", None) != getattr(b, "unit", None):
                raise ValueError(f"{self.step}: correction must keep the observation type/unit")
        return self


class DesignEvidence(Model):
    """A design or delivered-item fact (datasheet, functional spec, material certificate).

    ``label`` is the vendor's printed wording: a datasheet row, a function heading in the
    functional spec, or a certificate's part. A datasheet prints one row per requirement; a
    functional spec one function per requirement; a material certificate one row per part.
    """

    doc_id: str
    requirement: str
    observed: Observation
    label: str | None = None
    section: str | None = Field(None, description="Datasheet or functional-spec section.")
    description: str | None = Field(
        None, description="Function description in the functional spec, in its language."
    )


# --- Documents ----------------------------------------------------------------------


class DocRef(Model):
    doc: str
    rev: int = Field(0, ge=0)


class Document(Model):
    """One revision of a document the renderer produces (design section 5).

    Content comes from the rest of the world data; this holds what only the document
    itself has: number, revision, issue date and signatories.
    """

    id: str = Field(description="Document number, e.g. 'URS-TP201'; a FAT is its protocol id.")
    rev: int = Field(ge=0)
    type: Literal[
        "urs",
        "fat",
        "sat",
        "datasheet",
        "material_certificate",
        "calibration_certificate",
        "dq_report",
        "functional_spec",
        "risk_assessment",
        "vmp",
        "sop",
    ]
    title: str = Field("", description="Subtitle, e.g. 'Mechanical' for a FAT protocol.")
    language: Literal["id", "en"] = Field(description="Language of the printed text.")
    entry_language: Literal["id", "en"] | None = Field(
        None,
        description="Language of handwritten entries on a paper form (SAT only): site staff "
        "write Indonesian number and date formats on an English vendor form.",
    )
    serial_no: str | None = Field(
        None,
        description="Equipment serial number as written on this document, when it differs "
        "from Equipment.serial_no (scenario S3).",
    )
    scan: Literal["light", "medium", "heavy"] | None = Field(
        None,
        description="Paper document published as a scan at this degradation level "
        "(design section 8, degrader); None = born-digital PDF.",
    )
    issued_on: Offset
    prepared_by: str = Field(description="Person id.")
    checked_by: str | None = Field(None, description="Person id.")
    approved_by: str | None = Field(
        None, description="Person id. For a FAT: site approval, dated by the protocol."
    )
    executed_by: str | None = Field(None, description="Person id (FAT/SAT only).")
    witnessed_by: str | None = Field(None, description="Person id (FAT/SAT only).")
    change_note: str = Field("", description="Revision history entry; empty for rev 0.")
    reviews: tuple[DocRef, ...] = Field(
        (),
        description="Documents a DQ report or risk assessment reviews, e.g. the URS and the "
        "datasheet.",
    )

    ROLES: ClassVar = ("prepared_by", "checked_by", "approved_by", "executed_by", "witnessed_by")
    DESIGN_TYPES: ClassVar = frozenset({"datasheet", "functional_spec", "material_certificate"})
    REVIEWING_TYPES: ClassVar = frozenset({"dq_report", "risk_assessment"})
    GOVERNING_TYPES: ClassVar = frozenset({"vmp", "sop"})
    """Site-wide documents (design section 4): they govern every Equipment, so they are
    not in an Equipment's ``required_documents``."""


# --- Risk assessment ----------------------------------------------------------------


Score = Annotated[int, Field(ge=1, le=5)]


class Risk(Model):
    """One FMEA row: the failure of one requirement, scored 1-5."""

    requirement: str
    failure_mode: str = Field(description="In the risk assessment's language.")
    effect: str
    severity: Score
    occurrence: Score
    detection: Score = Field(description="1 = almost certainly detected, 5 = hardly detected.")

    @property
    def rpn(self) -> int:
        return self.severity * self.occurrence * self.detection


class RiskAssessment(Model):
    """The site's short FMEA over every URS requirement; it marks the Critical Aspects.

    Scores and the criticality threshold are judged numbers (design principle 7): drafted,
    then reviewed by a human before freeze. A requirement is critical when its severity
    reaches ``critical_from``, and that must agree with ``Requirement.critical``.
    """

    doc_id: str
    critical_from: Score = Field(description="Least severity that marks a Critical Aspect.")
    controls: dict[str, str] = Field(
        description="Planned control and verification per requirement scope, the same for "
        "every requirement of a scope (so it gives no Coverage label away)."
    )
    rows: tuple[Risk, ...] = Field(min_length=1)
    drafted_by: Literal["llm", "human"]
    reviewed_by: Literal["owner", "practitioner"] | None = None

    def critical(self, row: Risk) -> bool:
        return row.severity >= self.critical_from


# --- Equipment (one world-data file) ------------------------------------------------


class DefectType(StrEnum):
    """Planted defect types (design section 7, taxonomy), plus the two v0 scenarios that a
    reviewer flags although they are not review errors: a delivered item that does not meet
    the URS (S6) and an ambiguous value (S7)."""

    MISSING_SIGNATURE = "missing_signature"
    IMPOSSIBLE_DATE_ORDER = "impossible_date_order"
    SEGREGATION_OF_DUTIES = "segregation_of_duties"
    OUT_OF_LIMIT_MARKED_PASS = "out_of_limit_marked_pass"
    FAILED_RESULT_NO_DEVIATION = "failed_result_no_deviation"
    AC_CHANGED_WITHOUT_DEVIATION = "ac_changed_without_deviation"
    VENDOR_PROTOCOL_NOT_APPROVED = "vendor_protocol_not_approved"
    EXPIRED_CALIBRATION = "expired_calibration"
    CALCULATION_ERROR = "calculation_error"
    WATER_USED_IN_PHASE_1 = "water_used_in_phase_1"
    MISSING_ATTACHMENT = "missing_attachment"
    OUTDATED_REFERENCE = "outdated_reference"
    INCONSISTENT_DATA = "inconsistent_data"
    AC_DEVIATES_FROM_URS = "ac_deviates_from_urs"
    GDP_CORRECTION = "gdp_correction"
    LEFTOVER_FROM_OTHER_EQUIPMENT = "leftover_from_other_equipment"
    DESIGN_CONFLICT = "design_conflict"
    AMBIGUOUS_VALUE = "ambiguous_value"


class Anchor(Model):
    """Where a finding sits in a document: a string the renderer placed (``field``, a key of
    ``Rendered.placed``) or printed text found on the page (``text``). An anchor in a
    document that is not rendered yet names only the document."""

    doc: str
    rev: int = Field(0, ge=0)
    field: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _one_locator(self) -> Anchor:
        if self.field is not None and self.text is not None:
            raise ValueError(f"{self.doc}: anchor takes field or text, not both")
        return self


class Finding(Model):
    """The expected Pre-review finding of a planted scenario (defect manifest).

    Layer and default reference follow from ``type`` (design section 7 taxonomy)."""

    type: DefectType
    severity: Literal["critical", "major", "minor"]
    detail: str = Field(description="The expected finding, as a reviewer would write it.")
    at: tuple[Anchor, ...] = Field(min_length=1)


class Scenario(Model):
    """A planted defect or test situation (design section 7, v0 scenarios)."""

    id: str = Field(pattern=r"^S\d+$")
    summary: str
    reference: str = Field(
        "", description="Rule it breaks, primary first, '; ' between equivalents."
    )
    targets: tuple[str, ...] = Field(
        description="Requirement ids, protocol doc ids or test steps it is planted in."
    )
    note: str | None = None
    finding: Finding | None = Field(
        None, description="Expected Pre-review finding; None for a situation that is not one."
    )


class Probe(Model):
    """A hallucination probe (design section 9): a fact the corpus does not hold, beside a
    lure that invites a system to make it up. The expected answer is "not found".

    ``absent`` says what is missing for the requirement:

    - ``evidence``: no FAT/SAT step or certificate proves it, so a submission offers no
      Evidence, no ``covered_by_vendor``/``partial`` class and no unverified citation;
    - ``acceptance``: no document states a value to test against beyond the URS sentence,
      so a drafted Test Step leaves its Acceptance Criterion empty or copies the URS value.

    Probes ride on the requirements and Test Steps a submission already answers, so a system
    cannot tell them from other items.
    """

    id: str = Field(pattern=r"^P\d+$")
    requirement: str
    absent: Literal["evidence", "acceptance"]
    detail: str = Field(description="What the corpus does not say, as a reviewer would put it.")
    lures: tuple[Anchor, ...] = Field(
        min_length=1, description="Nearby text that invites the made-up answer."
    )


class SiteRules(Model):
    """Site rules the qualification SOP states that discovery may change (design section
    12, **[D]**). Each changes the SOP text and is applied by re-rendering."""

    witness: Literal["critical_aspects", "all"] = Field(
        description="Test Steps that need a Witness: those that verify a Critical Aspect "
        "(design default) or every Test Step."
    )
    protocols: Literal["template", "copied"] = Field(
        description="How the site writes IQ/OQ protocols: from its template (design "
        "default, no 'leftover from another Equipment' defect) or copied from similar "
        "Equipment."
    )


class RequiredDocument(Model):
    """A document the VMP requires for this Equipment (design section 6, "Documents that
    should exist"). ``missing`` says why it is not in the corpus."""

    id: str
    type: Literal[
        "urs",
        "risk_assessment",
        "datasheet",
        "functional_spec",
        "material_certificate",
        "calibration_certificate",
        "dq_report",
        "fat",
        "sat",
        "iq_protocol",
        "oq_protocol",
    ]
    stage: Literal["design", "FAT", "SAT", "IQ", "OQ"]
    missing: Literal["planned", "expected_gap", "withheld"] | None = Field(
        None,
        description="planned: not rendered yet; expected_gap: the document TraceQ drafts "
        "(IQ/OQ); withheld: deliberately left out, for missing-document recall.",
    )
    note: str | None = None


class Equipment(Model):
    """All world data for one Equipment item: the content of one ``world/*.yaml`` file."""

    tag: str = Field(pattern=r"^[A-Z]+-\d{3}$")
    name: str
    serial_no: str | None = Field(None, description="True serial number, as on the nameplate.")
    model: str | None = Field(None, description="Vendor's model designation.")
    site: str
    site_name: str | None = Field(None, description="Plant name printed on certificates.")
    vendor: Vendor
    labs: tuple[Organisation, ...] = ()
    people: tuple[Person, ...]
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    protocols: tuple[VendorProtocol, ...] = ()
    tests: tuple[TestEvidence, ...] = ()
    instruments: tuple[Instrument, ...] = ()
    designs: tuple[DesignEvidence, ...] = ()
    risk_assessment: RiskAssessment | None = None
    scenarios: tuple[Scenario, ...] = ()
    probes: tuple[Probe, ...] = ()
    documents: tuple[Document, ...] = ()
    required_documents: tuple[RequiredDocument, ...] = ()
    site_rules: SiteRules | None = Field(None, description="Rendered by the SOP.")

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
        dupes([i.id for i in self.instruments], "instrument")
        dupes([f"{d.id} rev {d.rev}" for d in self.documents], "document")
        errors += [f"{r} does not start with {prefix}" for r in req_ids if not r.startswith(prefix)]

        reqs, protocols = set(req_ids), {p.doc_id for p in self.protocols}
        labs = {o.id for o in self.labs}
        employers = {self.site, self.vendor.id} | labs
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
        instruments = {i.id for i in self.instruments}
        issuers = labs | {self.vendor.id}
        errors += [
            f"{i.id}: unknown issuer {i.certificate.lab}"
            for i in self.instruments
            if i.certificate.lab is not None and i.certificate.lab not in issuers
        ]
        for t in self.tests:
            errors += [
                f"{t.step}: unknown instrument {i}" for i in t.instruments if i not in instruments
            ]
            if t.requirement not in reqs:
                errors.append(f"{t.step}: unknown requirement {t.requirement}")
            if t.protocol not in protocols:
                errors.append(f"{t.step}: unknown protocol {t.protocol}")
        errors += [
            f"{d.doc_id}: unknown requirement {d.requirement}"
            for d in self.designs
            if d.requirement not in reqs
        ]
        for d in self.documents:
            errors += self._document_errors(d)
        errors += self._risk_errors()
        known = (
            reqs
            | protocols
            | instruments
            | {t.step for t in self.tests}
            | {d.doc_id for d in self.designs}
        )
        for s in self.scenarios:
            errors += [f"{s.id}: unknown target {x}" for x in s.targets if x not in known]
        dupes([p.id for p in self.probes], "probe")
        errors += self._probe_errors()
        errors += self._document_list_errors()
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def _document_errors(self, d: Document) -> list[str]:
        """Signatories and the type-specific content a document needs to be rendered."""
        name = f"{d.id} rev {d.rev}"
        people = {p.id: p for p in self.people}
        errors = [
            f"{name}: unknown {role} {pid}"
            for role in Document.ROLES
            if (pid := getattr(d, role)) is not None and pid not in people
        ]
        if d.rev > 0 and not d.change_note:
            errors.append(f"{name}: needs a change_note")
        if d.type in ("fat", "sat"):
            return errors + self._protocol_document_errors(d, name)
        if d.entry_language is not None:
            errors.append(f"{name}: entry_language is for SAT only")
        if d.type not in Document.REVIEWING_TYPES and d.reviews:
            errors.append(f"{name}: only a DQ report or risk assessment reviews documents")
        errors += [
            f"{name}: {d.type} has no {r}" for r in ("executed_by", "witnessed_by") if getattr(d, r)
        ]
        if d.type == "sop" and self.site_rules is None:
            errors.append(f"{name}: sop needs site_rules")
        if d.type == "vmp" and not self.required_documents:
            errors.append(f"{name}: vmp needs required_documents")
        if d.type in ("urs", "dq_report", "risk_assessment", *Document.GOVERNING_TYPES):
            errors += [
                f"{name}: {d.type} needs {r}"
                for r in ("checked_by", "approved_by")
                if not getattr(d, r)
            ]
        if d.type in Document.DESIGN_TYPES and not any(e.doc_id == d.id for e in self.designs):
            errors.append(f"{name}: {d.type} needs design facts (designs[].doc_id)")
        if d.type == "material_certificate":
            for e in self.designs:
                if e.doc_id == d.id and (e.label is None or not isinstance(e.observed, TextObs)):
                    errors.append(f"{name}: each part needs a label and a text material")
        if d.type == "datasheet":
            errors += [
                f"{name}: {e.requirement} needs a label and section"
                for e in self.designs
                if e.doc_id == d.id and (e.label is None or e.section is None)
            ]
        if d.type == "functional_spec":
            errors += [
                f"{name}: {e.requirement} needs a label, section and description"
                for e in self.designs
                if e.doc_id == d.id
                and (e.label is None or e.section is None or e.description is None)
            ]
        if d.type == "risk_assessment" and (
            self.risk_assessment is None or self.risk_assessment.doc_id != d.id
        ):
            errors.append(f"{name}: needs risk_assessment with doc_id {d.id}")
        if d.type in Document.REVIEWING_TYPES:
            rendered = {(x.id, x.rev) for x in self.documents}
            errors += [
                f"{name}: reviews {r.doc} rev {r.rev}, which is not rendered"
                for r in d.reviews
                if (r.doc, r.rev) not in rendered
            ]
        if d.type == "calibration_certificate":
            cert = next((i.certificate for i in self.instruments if i.certificate.id == d.id), None)
            if cert is None:
                errors.append(f"{name}: no instrument has certificate {d.id}")
            elif cert.lab is None or cert.results is None:
                errors.append(f"{name}: certificate needs a lab and results")
            elif people.get(d.prepared_by) and people[d.prepared_by].employer != cert.lab:
                errors.append(f"{name}: prepared_by must work for {cert.lab}")
            elif d.issued_on < cert.calibrated_on:
                errors.append(f"{name}: issued before calibration")
        return errors

    def _risk_errors(self) -> list[str]:
        """One FMEA row per requirement; its criticality agrees with the URS."""
        ra = self.risk_assessment
        if ra is None:
            return []
        reqs = {r.id: r for r in self.requirements}
        rows = [row.requirement for row in ra.rows]
        errors = [f"{ra.doc_id}: unknown requirement {r}" for r in rows if r not in reqs]
        errors += [
            f"{ra.doc_id}: {r} has more than one row" for r, n in Counter(rows).items() if n > 1
        ]
        errors += [f"{ra.doc_id}: no row for {r}" for r in reqs if r not in rows]
        scopes = sorted({r.scope for r in self.requirements} - set(ra.controls))
        errors += [f"{ra.doc_id}: no control for scope {s!r}" for s in scopes]
        errors += [
            f"{ra.doc_id}: {row.requirement} severity {row.severity} disagrees with "
            f"critical={reqs[row.requirement].critical}"
            for row in ra.rows
            if row.requirement in reqs and ra.critical(row) != reqs[row.requirement].critical
        ]
        return errors

    def _protocol_document_errors(self, d: Document, name: str) -> list[str]:
        stage = Stage(d.type.upper())
        protocol = next((p for p in self.protocols if p.doc_id == d.id), None)
        if protocol is None or protocol.stage is not stage:
            return [f"{name}: no {stage} protocol {d.id}"]
        errors = []
        if (d.entry_language is None) != (stage is Stage.FAT):
            errors.append(f"{name}: entry_language is required for SAT and absent for FAT")
        errors += [
            f"{name}: {stage} needs {r}"
            for r in ("executed_by", "witnessed_by")
            if not getattr(d, r)
        ]
        if (d.approved_by is None) != (protocol.site_approved_on is None):
            errors.append(f"{name}: approved_by must match the protocol's site approval")
        return errors

    def _probe_errors(self) -> list[str]:
        """A probe's fact really is absent from world data, so the corpus cannot hold it."""
        errors: list[str] = []
        reqs = {r.id: r for r in self.requirements}
        types = {d.id: d.type for d in self.documents}
        for p in self.probes:
            r = reqs.get(p.requirement)
            if r is None:
                errors.append(f"{p.id}: unknown requirement {p.requirement}")
                continue
            if p.absent == "evidence":
                errors += [
                    f"{p.id}: {t.step} tests {r.id}, so its Evidence is not absent"
                    for t in self.tests
                    if t.requirement == r.id
                ]
                errors += [
                    f"{p.id}: {d.doc_id} certifies {r.id}"
                    for d in self.designs
                    if d.requirement == r.id and types.get(d.doc_id) == "material_certificate"
                ]
                continue
            if not isinstance(r.spec, PresentSpec):
                errors.append(f"{p.id}: {r.id} states a value, so a test value is not absent")
            errors += [
                f"{p.id}: {x} states a value for {r.id}"
                for x, req, obs in (
                    *((t.step, t.requirement, t.observed) for t in self.tests),
                    *((d.doc_id, d.requirement, d.observed) for d in self.designs),
                )
                if req == r.id and obs.type != "present"
            ]
        return errors

    def _document_list_errors(self) -> list[str]:
        """Required documents agree with the rendered ones; finding anchors point at them."""
        errors: list[str] = []
        rendered = {(d.id, d.rev) for d in self.documents}
        rendered_ids = {d.id for d in self.documents}
        governing = {d.id for d in self.documents if d.type in Document.GOVERNING_TYPES}
        required = {d.id: d for d in self.required_documents}
        if len(required) != len(self.required_documents):
            errors.append("duplicate required document")
        if self.required_documents:
            errors += [
                f"{i}: rendered but not in required_documents"
                for i in sorted(rendered_ids - governing - set(required))
            ]
        for d in self.required_documents:
            if d.missing is None and d.id not in rendered_ids:
                errors.append(f"{d.id}: required, not missing, but not rendered")
            if d.missing is not None and d.id in rendered_ids:
                errors.append(f"{d.id}: marked {d.missing} but rendered")
        errors += [
            f"{e.doc_id}: design fact in a document that is neither rendered nor required"
            for e in self.designs
            if e.doc_id not in rendered_ids and e.doc_id not in required
        ]
        for s in self.scenarios:
            for a in s.finding.at if s.finding else ():
                where = f"{s.id}: anchor {a.doc} rev {a.rev}"
                if (a.doc, a.rev) in rendered:
                    if a.field is None and a.text is None:
                        errors.append(f"{where} needs a field or text")
                elif a.doc not in required or required[a.doc].missing is None:
                    errors.append(f"{where} is neither rendered nor a missing required document")
        for p in self.probes:
            for a in p.lures:
                if (a.doc, a.rev) not in rendered or (a.field is None and a.text is None):
                    errors.append(f"{p.id}: lure {a.doc} rev {a.rev} needs a rendered text")
        return errors

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
        """Judged requirement values without human sign-off. A frozen dataset has none."""
        return [r for r in self.requirements if r.source.judged and r.source.reviewed_by is None]

    def unreviewed_risks(self) -> bool:
        """The FMEA scores (judged numbers) lack human sign-off."""
        return self.risk_assessment is not None and self.risk_assessment.reviewed_by is None

    def unreviewed_results(self) -> list[Instrument]:
        """Instruments whose calibration readings (judged numbers) lack human sign-off."""
        return [
            i
            for i in self.instruments
            if i.certificate.results and i.certificate.results.reviewed_by is None
        ]
