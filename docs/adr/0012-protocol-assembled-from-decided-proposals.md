# The Protocol in TraceQ is assembled from decided Proposals and frozen when submitted

Decided 19 November 2026 for step 5a of ADR 0010, before its spec, after a fresh-context doubt review.

Execution (step 5b) is judged by code (ADR 0002), so it needs a Protocol whose Test Steps and Acceptance Criteria are structured data. A site's Protocol Draft is a document that Pre-review reads but cannot execute, so the Protocol is assembled inside TraceQ: one row per requirement of one run, for one Equipment, IQ and OQ combined (the drafted Test Steps are drafted for "IQ/OQ" and carry no Stage, and ADR 0010 does not extend them).

**Rows.** A requirement whose human-decided Coverage is `covered_by_vendor` is a Vendor Reference, and its drafted Test Step, if any, needs no decision; accepting it anyway makes the row a Test Step (tested again on site). Every other requirement needs exactly one Test Step: a drafted one accepted or edited, or one a human wrote because none was accepted. A written Test Step keeps every earlier version (who, when, old and new content) without a Reason for Change while the Protocol is a Draft, since it is not yet a GMP record (ADR 0009); a draft cannot be accepted while a written Test Step exists for its requirement.

**Submission** needs: every Coverage class decided by a human; every drafted Test Step of a non-vendor row decided; every non-vendor row with its one Test Step; every Acceptance Criterion in a shape code can judge (range, number, one of, present), free text refused; and every printed requirement number the run missed (the URS completeness check) answered by a human as "not a requirement" or "a requirement this Protocol does not test", each with a written justification. URS text no requirement quotes is shown, not answered. A row with no Test Step blocks; a missed requirement may be excluded with a justification, because a row always has a way to get a Test Step and a missed requirement has none.

**Freezing and approval.** Proposal Decisions are only added and are shared across runs, so a Protocol that read them live could change under its Approver. On submission the Protocol stores a copy of every row, the answers on missed requirements and the unquoted URS text, and the hash of that copy. Protocol Approval is a recorded status bound to that hash, labelled not an Electronic Signature (ADR 0007 phase 2; signed from step 8, see ADR 0007 amendment of 26 November 2026); later decisions only affect a later Protocol. The Approver holds an approving role, is not the Preparer, and recorded none of what the copy rests on: the decisions in force (Coverage decisions included), the answers on missed requirements, and the written Test Steps.

**Statuses:** Draft, Submitted, Approved, and Withdrawn (a Draft given up with a reason, so a newer run can get a Protocol). An Approver may return a Submitted Protocol to Draft with a reason; the returned copy stays as history. One Protocol per Equipment may be open at a time, and none may be started once one is approved: a new version is step 6.

## Amended 26 November 2026: the Protocol may start from the site's reviewed Protocol Draft

Decided by the owner in chat on 26 November 2026 ("Ya, ketiganya", an answer to a question that listed this change together with the two amendments of ADR 0010 of the same date). Until now the Protocol was assembled from TraceQ's own drafted Test Steps, so the draft that Pre-review reviewed was never the document that Execution ran. The Considered Option "Execute the site's Protocol Draft" is reversed in part: its objection (no human decides the rows) is met, because every row below is decided by a human.

- **Source.** For a run with a Review Package, a Protocol may start from the site's Protocol Draft instead: each Test Step the system read from the draft with a verified citation becomes a candidate row. The Test Step and its Acceptance Criterion are Proposals, as before: a human accepts or edits each, and an Acceptance Criterion read from a document needs a Proposal Decision before approval (ADR 0010).
- **Submission.** The rules of Submission above apply unchanged to a draft-sourced Protocol. For every draft-sourced row a human decides both the Test Step and its Acceptance Criterion (accept or edit); a row left unread, or a criterion only displayed, blocks submission. One Protocol uses one source: the draft or the system's own drafted Test Steps, never both, so a row never carries two Test Steps.
- **What stays.** Every Coverage class decided by a human, every missed requirement number answered, one open Protocol per Equipment, the shape rule for Acceptance Criteria (code must be able to judge it, free text refused), answers on missed requirements, the frozen copy and its hash (the copy also records the draft's document version, revision and hash it was read from, so the Approver and the Audit Trail can trace the source), preparer is not approver, and approval as a signed status (ADR 0007, step 8).
- **Findings carry over.** An accepted finding about a draft row ("this is a real defect and will be fixed") is shown on that row until the Test Step is edited or a later revision of the draft resolves it. A later revision resolves it only when the round-over-round diff says so, never by a person marking it silently. The carry-over reads Proposal Decisions only for display; Eval runs never read them. Whether it blocks submission or only warns is a gate: the owner decides it on the spec.
- **Stage.** The draft carries no Stage; a human sets IQ or OQ per Test Step, as the consequence of this ADR already anticipated.
- **Marking.** The draft-sourced path is marked in the UI and the demo runbook as awaiting the practitioner's answer (#245).
- **Open question, not settled by this amendment:** whether a plant executes the draft it reviewed is a question for the practitioner (#245). If the answer is no, this path is removed, not patched.

## Considered Options

- **Execute the site's Protocol Draft (reversed in part, see Amended 26 November 2026):** its Test Steps and Acceptance Criteria are read with verified citations, but no human decides them, and the Review Package holds only an OQ draft.
- **Read decisions live until approval:** simpler, but an Approver could approve content other than what they read.
- **Separate IQ and OQ Protocols:** the drafts carry no Stage, so a requirement whose draft belongs to the other Stage would block submission with no honest way out.
- **Block submission on any missed requirement number:** a replayed run misses the same numbers again, and a URS numbered `4.1` over-reports by design, so submission could never happen.
- **Approver only differs from the Preparer:** allows deciding rows and then approving them.

## Consequences

- Known limits, stated in the product: one Test Step per requirement; no printed or exported Protocol (not in the order of ADR 0010; on the practitioner agenda, #245); no new version after approval until step 6.
- The document Pre-review reviewed is not the one executed: a site Protocol Draft finding accepted as "will be fixed" leads nowhere in TraceQ unless the Protocol is started from the draft (amendment of 26 November 2026). Whether a site executes the draft it reviewed is a question for the practitioner session.
- Execution and the Qualification Report (steps 5b and 7) are per Stage, so a combined IQ/OQ Protocol is debt for step 7; a Stage set by a human per Test Step is the likely way out.
- Status changes are appended events, since the tables refuse UPDATE. A demo rehearsal starts again from a reset database, because an approved Protocol blocks a new one.
- The demo issuer gets a fourth fictional persona holding only the approving role.
- Eval runs never read Protocols, decisions or written Test Steps.
