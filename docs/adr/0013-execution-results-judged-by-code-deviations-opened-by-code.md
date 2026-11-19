# Execution records Results that code judges, and code opens a Deviation for every failed one

Decided 19 November 2026 for step 5b of ADR 0010, before its spec. Execution and Deviation are thin (ADR 0010): the main path only, no AI, no Pre-review of an Execution, and no eval set. The controls below are the ones code can enforce without Electronic Signatures (ADR 0007 phase 2), so that the defects the dataset plants in site Execution records (design §7: failed result not raised as a Deviation, performer = Witness, Execution before Protocol Approval, expired instrument calibration) cannot arise in TraceQ's own.

**One Execution per approved Protocol.** It covers every row of the Protocol's frozen copy (ADR 0012), IQ and OQ combined. Vendor References are shown with the vendor's Evidence and need no action. Each Test Step row needs a Result.

**Results.** The Performer records a Result in the shape of the row's Acceptance Criterion: a number with exactly the unit of a range or a number (another unit is refused; nothing is converted), an observed value for a one-of, present or absent for a present. Code decides pass or fail; the Performer cannot. A free-text observation may go with it and has no effect on the outcome. The time of a Result is the database's time when it is recorded; no date is typed (ALCOA contemporaneous). When the Test Step names an instrument, the Result needs the instrument's identifier and its calibration due date, and code refuses it when that date is before the database's date. Evidence is zero or more text references (a printout number, a logbook page); files arrive with document storage in step 6.

**Corrections and Retests.** Execution data is a GMP record: the Performer may correct their own Result while the Execution is in progress, with a Reason for Change, and every earlier version stays visible. A Retest is a new attempt at a failed Test Step: it names that step's Deviation and gives a reason, and every attempt stays visible in order. The latest attempt is the row's Result.

**Witness.** A Witness confirms a Result while signed in as themselves. The confirmation is a recorded status bound to the hash of the Result's content, labelled not an Electronic Signature; a correction voids it. Code refuses a Witness who is the Performer. No Test Step requires a Witness yet: which ones do is the Witness rule, open for the practitioner session (design §12; its [D] default applies after 5 December 2026), and the flag that would carry it is Protocol content, so it arrives with a new Protocol version in step 6.

**Deviations.** Code opens a Deviation for every Result it judges failed, including a failed Retest; nobody can skip it. A Performer may also open one for an event (an instrument failing mid-test, a step not performable as written), linked to one Test Step or to the Execution. A Deviation holds a description (filled by code for a failed Result: the Test Step, its Acceptance Criterion and the Result), a class set by a human (minor, major or critical), an Investigation (root cause and impact on the qualification) and CAPA as text. Its statuses are Open, Submitted (the Investigation is ready) and Closed. An Approver closes it or returns it to Open with a reason; the closer holds the approving role and did not write any version of the Investigation. Closure is a recorded status, labelled not an Electronic Signature. A correction that turns a failed Result into a passing one does not close its Deviation: the Deviation is closed through its Investigation like any other.

**Completion.** An Execution is In progress, then Completed. A Performer completes it when every Test Step row has a Result and every Deviation is Closed; an unconfirmed Result does not block, since no Test Step requires a Witness. On completion the Execution stores a copy of every Result, attempt, correction, Witness confirmation and Deviation, and the hash of that copy, for the Qualification Report of step 7 to rest on. Nothing is corrected or retested after that.

**Roles.** Two roles join the two of step 5a: an executing role (start an Execution, record, correct and retest Results, open Deviations, write Investigations) and a witnessing role (confirm Results). Code checks the separations per person, not per role, so a person holding two roles is still refused.

## Considered Options

- **Separate Executions for IQ and OQ:** needs a Stage on each Test Step, which is Protocol content bound to the approved hash; it would reopen step 5a for what only step 7 uses. Setting the Stage during Execution is wrong: the Approver approves it.
- **The Performer sets pass or fail, code warns:** contradicts ADR 0002 and leaves the most common defect in site records possible.
- **File upload as Evidence now:** builds document storage ahead of step 6. Making Evidence mandatory on every Test Step forces a reference where the recorded value is the evidence.
- **The Performer types the Witness's name:** anyone can type a name, so performer ≠ Witness could not be enforced.
- **A Witness flag on each Test Step now, or a Witness on every step:** the first reopens step 5a on a rule not yet decided; the second is not the practice the practitioner described.
- **Only automatic Deviations, or only manual ones:** the first cannot record an event, which the definition of a Deviation includes; the second leaves "failed result not raised as a Deviation" possible.
- **A correction to a passing value cancels the Deviation:** retyping a failed value until it passes is the classic data-integrity breach; keeping the Deviation open makes every such correction answer to an Approver.
- **No Retest in step 5b, or a Retest only after an Approver allows it:** the first leaves a repaired failure no way to pass; the second adds a status and a screen to a thin step. Every failed attempt and its Deviation stay visible, so testing into compliance shows.
- **A typed performance date:** allows backdating, and a Result recorded before Protocol Approval would become possible.
- **A calibration warning instead of a refusal:** a warning is clicked away.
- **Completion with open Deviations:** an Investigation that ends in a Retest would find the Execution already frozen.

## Consequences

- Known limits, stated in the product: Evidence is a text reference; no Test Step requires a Witness; a Retest needs no prior permission; the calibration due date is typed by a person, with no instrument register; Results are recorded live, so transcription from paper is not supported; one Execution per approved Protocol and no way to abandon one, so a demo rehearsal starts again from a reset database, as in step 5a.
- Step 7 still needs a Stage per Test Step (ADR 0012); the Execution's frozen copy carries none.
- Status changes are appended events, since the tables refuse UPDATE.
- The demo issuer gets a fifth fictional persona holding only the witnessing role; the two deciding personas also get the executing role, and the approving persona closes Deviations.
- Eval runs never read Executions or Deviations.
