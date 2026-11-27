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
A controlled document that defines the Test Steps and Acceptance Criteria for one Qualification Stage of one Equipment (or IQ and OQ combined), before execution, and names by Vendor Reference each requirement the vendor's Evidence already proves. It has no authority until approved by an authorised person.
_Avoid_: template, form, checklist

**Protocol Draft**:
A site's Protocol document before its approval, as received for Pre-review. A Protocol assembled in TraceQ is not a Protocol Draft at any status, even when it was started from one (ADR 0012, amended 26 November 2026). A Protocol Draft can have several revisions, each a document version.

**Pinned Revision**:
The revision of a Protocol Draft that a Protocol started from it was read from, recorded with the run, draft document and hash. The Protocol never re-syncs to a newer revision: while the Pinned Revision is older than the latest, submitting and approving it are refused, and it is returned or withdrawn and a new Protocol started from the latest (ADR 0012, amended 27 November 2026).

**Review Round**:
One pass of Pre-review over one revision of a Protocol Draft. The round-over-round diff names each finding resolved, persisted, persisted-but-changed or new; a finding is never resolved by a person marking it (ADR 0010 and 0012, 26 November 2026).
_Avoid_: iteration, cycle

**Row Source**:
Where one Protocol row takes its Test Step from: the site's Protocol Draft, TraceQ's own drafted Test Step, or a Test Step written by a person. A row has exactly one, recorded in the Frozen Copy (ADR 0012, amended 26 November 2026).

**Preparer**:
The person who submits a Protocol for approval.
_Avoid_: author, owner

**Approver**:
An authorised person, never the Preparer, who approves a submitted Protocol or returns it to the Preparer with a written reason.
_Avoid_: reviewer, signer

**Protocol Approval**:
The recorded act that makes a submitted Protocol an approved one, bound by an Electronic Signature (`approved`) or a Demo signature in demo mode.
_Avoid_: sign-off, signature

**Frozen Copy**:
The content of a Protocol fixed when it is submitted, with its SHA-256 hash; the Approver signs this copy, not the live Protocol. Version 2, for a Protocol started from a Protocol Draft, also records the draft's document version, revision, hash and run, each row's Row Source and Stage, the dropped and mapped draft steps, and every finding with its decision, author and written reason. Approval covers TraceQ's copy, not the site's document (ADR 0012).
_Avoid_: snapshot, export

**Test Step**:
One verification step in a Protocol that produces a Result.

**Vendor Reference**:
A line of a Protocol stating that one requirement is proven by the vendor's Evidence and is not tested again on site.
_Avoid_: leveraged evidence, vendor step

**Acceptance Criterion (AC)**:
The limit, set by a human, that decides whether a Test Step passes or fails.
_Avoid_: spec limit, threshold

**Execution**:
Carrying out an approved Protocol and recording a Result for each of its Test Steps, with their Evidence.
_Avoid_: run, test run

**Performer**:
The person who carries out a Test Step and records its Result.
_Avoid_: executor, tester, operator

**Result**:
The actual value one attempt at a Test Step produced, in the shape of its Acceptance Criterion. Code, not a person, decides whether it passes.
_Avoid_: reading, outcome, measurement

**Retest**:
A new attempt at a failed Test Step, justified by that step's Deviation; the earlier attempts stay on record.
_Avoid_: re-run, repeat test

**Deviation**:
A failed Result, or an event during Execution, that does not conform to the Protocol or an Acceptance Criterion.
_Avoid_: error, failure, nonconformance

**Investigation**:
The written root cause of one Deviation and its impact on the qualification.
_Avoid_: RCA, root cause analysis (as a record name)

**CAPA (Corrective and Preventive Action)**:
The action that removes the cause of a Deviation and keeps it from recurring.
_Avoid_: action item, fix

**Deviation Closure**:
The recorded act by which an authorised person, never an author of the Investigation, closes a Deviation, bound by an Electronic Signature (`approved`) or a Demo signature in demo mode.
_Avoid_: sign-off, approval (for a Deviation)

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

**Documented Capability**:
What the Vendor Documents state or show the Equipment can do: the ranges and accuracy in its specification, and its FAT/SAT results. It is not the Equipment's actual capability on site.
_Avoid_: actual capability, machine limits

**Alert Level / Action Level**:
Internal limits, set in the VMP, for monitored parameters (e.g. microbial counts in purified water). They are site limits, not pharmacopoeial specifications.

**Excursion**:
A monitored result beyond a limit. Beyond the Alert Level: recorded and trended. Beyond the Action Level: investigated. Outside a Protocol Acceptance Criterion: a Deviation (CPOB 12.16).

## Data integrity

**Electronic Signature**:
A signature bound to the content of one record that states one Signature Meaning; equivalent to a handwritten signature.
_Avoid_: approval click, e-sign (as a verb)

**Signature Meaning**:
What an Electronic Signature asserts: prepared, reviewed, approved, executed, or witnessed.

**Witness**:
A second person who directly verifies the performance of a critical Test Step and confirms its Result; never the Performer.
_Avoid_: checker, second signer

**Separation of Duties**:
The rule that the person who approves a record is not one who produced it. For a Protocol, the Approver is not the Preparer, not a person who decided a finding or mapped a draft step on that run, and neither a person who uploaded the bytes of the Pinned Revision nor the person whose import registered it (ADR 0012, amended 26, 27 and 28 November 2026). The Deviation Closure and Witness rules are in ADR 0013.
_Avoid_: segregation (except as the name of the planted Defect Type `segregation_of_duties`)

**Reason for Change**:
The mandatory written reason that accompanies every correction to GMP data.
_Avoid_: comment, note

**Audit Trail**:
An immutable chronological record of who created, changed, or deleted GMP data, when, the old and new values, and the Reason for Change.
_Avoid_: log, history

## AI and checks

**Proposal**:
Anything the system puts before a human for a decision: the Coverage class of a requirement, a Pre-review finding (Check Finding or AI Finding), a drafted Test Step, or a Test Step or Acceptance Criterion read from a Protocol Draft. It has no effect until a human decides on it.
_Avoid_: AI decision, AI result, suggestion

**Proposal Decision**:
A human's recorded answer to one Proposal: accepted, edited or rejected, with who decided, when, and the Reason for Change when it is edited or rejected. It is not an Electronic Signature, which approves a controlled document.
_Avoid_: review decision, approval

**AI Finding**:
A Pre-review finding made by the LLM. It is a Proposal, and every citation in it is verified before a human sees it.
_Avoid_: AI decision, AI result

**Check Finding**:
A finding decided by a deterministic rule (e.g. a result outside its Acceptance Criterion marked as passed). A model may read the values the rule judges from a document, each with a verified citation; the model never decides the finding.
_Avoid_: AI Finding (for rule output)

**Hallucination Probe**:
An eval item whose fact the corpus does not hold, planted beside a lure; the right answer is "not found", and any value, Evidence or citation given for it counts as fabricated.
_Avoid_: trick question

**Clean Trap**:
An eval item where a document is correct but looks like a defect: an Acceptance Criterion close to its URS limit, or the same limit written another way. The right answer is no finding; a finding on it counts as wrong.
_Avoid_: decoy, negative sample

**Injection Probe**:
An eval item where a document carries text that instructs the AI to do something (e.g. not to report a defective Test Step). It passes when the effect the text asks for does not appear in the output.
_Avoid_: jailbreak

**No-LLM Baseline**:
A run of the same pipeline in which every reading the LLM would do is done by plain text rules (patterns and keywords) instead. Its scores, beside the LLM's on the same Equipment, show what the LLM adds.
_Avoid_: rules engine, fallback mode

**Review Package**:
One site Protocol Draft with its own answer key (two revisions from version 0.2.0), which refers to a frozen Equipment package without changing it. Pre-review of a site document is scored on it.
_Avoid_: test set, review bundle

**Defect Type**:
The kind of error planted in a Review Package and named in its answer key (for example `missing_signature`, `unit_error`, `outdated_reference`, `ac_outside_documented_capability`). A new Defect Type is a scoring-rule change in its own PR, with its manifest and key merged before any rule or prompt for it (ADR 0010, amended 26 November 2026). The last three are marked "not reviewed by a practitioner".
_Avoid_: error class, bug type

**Upload Job**:
One queued, running, finished or failed browser upload of a Protocol Draft revision for one Equipment. It records the revision and the uploader's identity, reserves its cost from the upload budget before it is queued, and is taken in order by one background worker (spec #375).

**Pre-review**:
The automated review of a Protocol Draft or an Execution before human review: deterministic rules first (Check Findings), then the LLM for the rest (AI Findings).
_Avoid_: AI review, auto-review

**Mode Cloud / Mode Pabrik**:
The two AI processing configurations. Mode Cloud uses an external LLM provider; Mode Pabrik ("factory mode") processes everything on the site's own infrastructure with no data leaving it.
