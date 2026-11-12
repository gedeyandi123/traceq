# Glossary

Domain language for TraceQ: pharmaceutical equipment qualification under CPOB (Indonesian GMP, PerBPOM 7/2024) and equivalent GMP rules. Use these terms in code, documents, and UI copy.

## Objects

**Equipment**:
One unit of equipment, facility, or utility that must be qualified before GMP production use (e.g. tablet press, purified water system).
_Avoid_: machine, asset

**Equipment Registry**:
The official list of all Equipment with its latest qualification status and next Requalification date.
_Avoid_: asset list, master data

**URS (User Requirement Specification)**:
The user's requirements for a piece of Equipment; the starting point of Traceability. Indonesian: **SKP** (Spesifikasi Kebutuhan Pengguna).
_Avoid_: spec, requirements doc

**Vendor Document**:
A document from the Equipment supplier (manual, specification, certificate, FAT/SAT results) that can serve as Evidence.
_Avoid_: manual (as a general term)

**Vendor Assessment**:
The site's documented evaluation of a supplier, including the scope of activities whose results the site may rely on.

**Validation Master Plan (VMP)**:
The site document that sets qualification policy: Equipment categories, Requalification intervals, required documents, signing responsibilities, and internal alert/action levels.

## Qualification lifecycle

**Qualification Stage**:
One documented proof stage: DQ, FAT, SAT, IQ, OQ, or PQ (Indonesian KD/KI/KO/KK for DQ/IQ/OQ/PQ).
_Avoid_: phase, step

**Protocol**:
A controlled document that defines the Test Steps and Acceptance Criteria for one Qualification Stage, before execution.
_Avoid_: template, form, checklist

**Protocol Draft**:
A Protocol that is not yet approved, including one drafted by AI. It has no authority until approved by an authorised person.

**Test Step**:
One verification step in a Protocol that produces a measured or observed result.

**Acceptance Criterion (AC)**:
The limit, set by a human, that decides whether a Test Step passes or fails.
_Avoid_: spec limit, threshold

**Execution**:
Carrying out an approved Protocol and recording actual results with their Evidence.
_Avoid_: run, test run

**Deviation**:
A result or event during Execution that does not conform to the Protocol or an Acceptance Criterion.
_Avoid_: error, failure, nonconformance

**Qualification Report**:
A summary of Execution that concludes the status of one Qualification Stage, approved by an authorised person.

**Requalification**:
Scheduled or change-triggered qualification of Equipment that is already qualified.
_Avoid_: revalidation (for Equipment)

**Change Control**:
The formal process for proposing, assessing, and approving a change to qualified Equipment; may trigger Requalification.

## Evidence and traceability

**Evidence**:
A record that proves a Test Step or requirement is met (data, photo, printout, certificate).

**Traceability**:
The traceable link from a URS requirement → Critical Aspect → Test Step → Evidence.
_Avoid_: mapping, linkage

**Critical Aspect**:
A function or feature of the Equipment that directly affects product quality and must be verified.

**Coverage**:
How well existing Evidence proves a requirement. Exactly one of five classes:
`covered_by_vendor`, `partial`, `site_only`, `gap`, `conflict`. See the decision table in [`docs/design/synthetic-dataset.md`](docs/design/synthetic-dataset.md).

**Alert Level / Action Level**:
Internal limits, set in the VMP, for monitored parameters (e.g. microbial counts in purified water). They are site limits, not pharmacopoeial specifications.

**Excursion**:
A monitored result beyond a limit. Beyond the Alert Level: recorded and trended. Beyond the Action Level: investigated. Outside a Protocol Acceptance Criterion: a Deviation (CPOB 12.16).

## Data integrity

**Electronic Signature**:
A signature bound to the content of one record that states one Signature Meaning; equivalent to a handwritten signature.
_Avoid_: approval click, e-sign (as a verb)

**Signature Meaning**:
What an Electronic Signature asserts: authored, reviewed, approved, executed, or witnessed.

**Witness**:
A second person who directly verifies the performance of a critical Test Step; never the same person as the performer.
_Avoid_: checker, second signer

**Reason for Change**:
The mandatory written reason that accompanies every correction to GMP data.
_Avoid_: comment, note

**Audit Trail**:
An immutable chronological record of who created, changed, or deleted GMP data, when, the old and new values, and the Reason for Change.
_Avoid_: log, history

## AI and checks

**AI Finding**:
An AI proposal (draft, Pre-review finding, extraction result) that a human must accept, edit, or reject before it has any effect.
_Avoid_: AI decision, AI result

**Check Finding**:
A finding produced by a deterministic rule, with no model involved (e.g. a result outside its Acceptance Criterion marked as passed).
_Avoid_: AI Finding (for rule output)

**Pre-review**:
The automated review of a Protocol or Execution before human review: deterministic rules first (Check Findings), then the LLM for the rest (AI Findings).
_Avoid_: AI review, auto-review

**Mode Cloud / Mode Pabrik**:
The two AI processing configurations. Mode Cloud uses an external LLM provider; Mode Pabrik ("factory mode") processes everything on the site's own infrastructure with no data leaving it.
