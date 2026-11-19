# Execution records Results that code judges, and code opens a Deviation for every failed one

Decided 19 November 2026 for step 5b of ADR 0010, before its spec, after a fresh-context doubt review. Execution and Deviation are thin (ADR 0010): the main path only, no AI, no Pre-review of an Execution, and no eval set. The controls below are the ones code can enforce without Electronic Signatures (ADR 0007 phase 2), so that the defects the dataset plants in site Execution records (design §7: failed result not raised as a Deviation, performer = Witness, Execution before Protocol Approval, expired instrument calibration) cannot arise in TraceQ's own.

**One Execution per approved Protocol.** An Execution starts only from an Approved Protocol and covers every row of its frozen copy (ADR 0012), IQ and OQ combined. Vendor References are shown with the vendor's Evidence and need no action. Each Test Step row needs a Result.

**Results.** The Performer records a Result in the shape of the row's Acceptance Criterion, and code decides pass or fail; the Performer cannot. These are scoring rules (ADR 0002):

- A range or a number: the Performer types a number; the unit is the Acceptance Criterion's, shown and not typed, so any conversion is the Performer's own. A range's bounds pass (inclusive). A number passes only when equal, with no rounding: the frozen Acceptance Criterion keeps no decimal places, so the rounding rule of USP General Notices 7.20 cannot apply, and a tolerance has to be written as a range.
- A one-of: the Performer picks an allowed value, or "not one of these" with the observed value typed, which fails.
- A present: present passes, absent fails.
- Any Test Step: "not performable", with a reason, fails. A row whose step cannot be carried out still gets a Result, so an Execution never waits on a row nobody can fill.

A free-text observation may go with a Result and has no effect on the outcome. The time of a Result is the database's time when it is recorded; no date is typed (ALCOA contemporaneous). Evidence is zero or more text references (a printout number, a logbook page); files arrive with document storage in step 6.

**Instruments.** When the Test Step's instrument field is not empty, the Result needs at least one instrument, each with its identifier and calibration due date, and code refuses the Result when any due date is before the database's date (for a correction, the date of the attempt's first version, when the measurement was made). When no calibrated instrument applies (the field says "visual inspection", say), the Performer records that with a reason, and code opens a Deviation, since the step departs from the Protocol; the Result is judged as usual.

**Corrections and Retests.** Execution data is a GMP record. While the Execution is in progress, the Performer may correct any of their own attempts with a Reason for Change, and every earlier version stays visible. A correction is refused while a Deviation of that attempt is Submitted or Closed: an Approver returns a Submitted one to Open first, and a Closed one makes the attempt final, so data an Approver has reviewed never changes without a new review. A Retest is a new attempt at a failed Test Step; it names a Deviation linked to that step that is Open (automatic or manual) and gives a reason. A Submitted Deviation is returned to Open by an Approver first; a Closed one allows no Retest. Every attempt stays visible in order, and the latest is the row's Result.

**Witness.** A Witness confirms a Result while signed in as themselves. The confirmation is a recorded status bound to the hash of the Result's content, labelled not an Electronic Signature; a correction voids it. Code refuses a Witness who is the Performer. No Test Step requires a Witness yet. The practitioner has named the steps that should (design §12: manual tests without automatic raw data, critical interlocks and alarms, system security checks), but the owner has not adopted that rule; the dataset default `critical_aspects` governs site documents, not TraceQ's Protocol. The flag that would carry the rule is Protocol content bound to the approved hash, so it arrives with a new Protocol version in step 6, and ADR 0007's Witness control waits until then.

**Deviations.** Code opens a Deviation for every failed attempt, at most one per attempt for each cause (a failure, no calibrated instrument), the first time a version of that attempt has the cause: correcting a failed value to another failed value opens none, correcting a passing value to a failed one opens one, and correcting a failed value to a passing one leaves its Deviation open, to be closed through its Investigation like any other. Nobody can skip it. A Performer may also open a Deviation for an event (an instrument failing mid-test, a step changed in the doing), linked to one Test Step or to the Execution.

A Deviation holds a description (filled by code for a failed attempt: the Test Step, its Acceptance Criterion and the Result), a class (minor, major or critical), an Investigation (root cause and impact on the qualification) and, when needed, a CAPA as text. The Investigation's author sets the class; it is required before submission and may change while the Deviation is Open, with a Reason for Change. Its statuses are Open, Submitted (the Investigation is ready) and Closed. An Approver closes it or returns it to Open with a reason; an Approver who disagrees with the class returns it rather than changing it. The closer holds the approving role and is none of: an author of any version of the Investigation, the Performer of any attempt at the linked Test Step, the person who opened a manual Deviation. Deviation Closure is a recorded status, labelled not an Electronic Signature.

**Completion.** An Execution is In progress, then Completed. A Performer completes it when every Test Step row has a Result and every Deviation is Closed. A row whose latest attempt failed does not block: the Qualification Report of step 7 concludes on it. An unconfirmed Result does not block either, since no Test Step requires a Witness. On completion the Execution stores a copy of every Result, attempt, correction, Witness confirmation and Deviation, and the hash of that copy, for step 7 to rest on. Nothing is corrected or retested after that.

**Roles.** Two roles join the two of step 5a: an executing role (start an Execution, record, correct and retest Results, open Deviations, write Investigations) and a witnessing role (confirm Results). Code checks every separation above per person, not per role, so a person holding two roles is still refused. A Protocol's Preparer may perform its Execution and its Approver may close Deviations; neither is a separation the domain asks for.

## Considered Options

- **Separate Executions for IQ and OQ:** needs a Stage on each Test Step, which is Protocol content bound to the approved hash; it would reopen step 5a for what only step 7 uses. Setting the Stage during Execution is wrong: the Approver approves it.
- **The Performer sets pass or fail, code warns:** contradicts ADR 0002 and leaves the most common defect in site records possible.
- **The Performer types the unit, and another unit is refused:** "°C" against "degC" would fail on spelling, not on the value.
- **Rounding before comparing (USP 7.20):** needs the Acceptance Criterion's decimal places, which step 5a does not store; adding them reopens step 5a.
- **A row with no Result completes once its event Deviation is Closed:** an empty row would look finished, and a rule with an exception is harder to audit than "every row has a Result".
- **File upload as Evidence now:** builds document storage ahead of step 6. Making Evidence mandatory on every Test Step forces a reference where the recorded value is the evidence.
- **The Performer types the Witness's name:** anyone can type a name, so performer ≠ Witness could not be enforced.
- **Adopt the practitioner's Witness rule now, with a flag on each Test Step:** reopens step 5a. A Witness on every step is not the practice the practitioner described.
- **Only automatic Deviations, or only manual ones:** the first cannot record an event, which the definition of a Deviation includes; the second leaves "failed result not raised as a Deviation" possible.
- **A correction to a passing value cancels the Deviation:** retyping a failed value until it passes is the classic data-integrity breach; keeping the Deviation open makes every such correction answer to an Approver.
- **No Retest in step 5b, or a Retest only after an Approver allows it:** the first leaves a repaired failure no way to pass; the second adds a status and a screen to a thin step. Every failed attempt and its Deviation stay visible, so testing into compliance shows.
- **A typed performance date:** allows backdating, and a Result recorded before Protocol Approval would become possible.
- **A calibration warning instead of a refusal:** a warning is clicked away. Skipping the check when no instrument applies, without a Deviation, would be a silent way around it.
- **An Approver edits the class, or CAPA is mandatory:** the first makes the closer an author of what they close; the second fills the field with "N/A".
- **Completion with open Deviations:** an Investigation that ends in a Retest would find the Execution already frozen.

## Consequences

- Known limits, stated in the product: Evidence is a text reference; no Test Step requires a Witness; a Retest needs no prior permission; a number Acceptance Criterion is compared without rounding; the calibration due date is typed by a person, with no instrument register; Results are recorded live, so transcription from paper is not supported; one Execution per approved Protocol and no way to abandon one, so a demo rehearsal starts again from a reset database, as in step 5a.
- Step 7 still needs a Stage per Test Step (ADR 0012); the Execution's frozen copy carries none.
- ADR 0007 is amended: its Witness control applies from step 6.
- Status changes are appended events, since the tables refuse UPDATE.
- The demo issuer gets a fifth fictional persona holding only the witnessing role; the two deciding personas also get the executing role, and the approving persona closes Deviations.
- Eval runs never read Executions or Deviations.
