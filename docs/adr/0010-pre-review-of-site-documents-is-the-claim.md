# Pre-review of site documents is the claim; the lifecycle is built in thin slices

Decided 16 November 2026, after the thin slice (#29) and the discovery answers (design §12, one practitioner, n = 1). The slice put its depth in Coverage from Vendor Documents. Discovery named something else: review-and-revision loops as the largest time sink, and Deviations caused by approved Acceptance Criteria that the Equipment or a utility could not meet as the main frustration. Reuse of vendor evidence is real but narrow.

**Working thesis.** TraceQ pre-reviews equipment qualification documents against the URS, the vendor's evidence and the site's rules before a human reviews them, each finding with its citation. AI proposes; people decide.

This is a hypothesis until the practitioner session answers two questions: whether review loops are caused by defects a check can find, and whether an unreachable Acceptance Criterion is usually visible in the documents. If the answer is "mostly queueing for signatures", the review workflow gets the depth and the claim shrinks. The README carries a claim sentence only once Pre-review of a site Protocol Draft has its first scored run.

## What is built, and how deep

- **Deep** (AI or rules measured against an eval set): Traceability and Coverage, and Pre-review with Proposal Decisions. Coverage is the foundation, not the headline: the matrix tells Pre-review what an Acceptance Criterion must be compared with, so its reading accuracy bounds Pre-review. Drafted Test Steps stay as built and measured; they are not extended.
- **Thin** (the main path only, stored and tested to the same standard, no edge cases): document upload and versions, review rounds and approval, Protocol, Execution, Deviation, Qualification Report, Equipment Registry, risk assessment (Critical Aspect), identity, roles and Audit Trail.
- **Seam** (a field or status in the data, no screen of its own): Requalification and Change Control, cross-department scheduling, audit preparation.
- **Later** (design only): Mode Pabrik self-hosting, phase 3 of ADR 0007, and whatever the order below cuts. The SEA-LION spike of ADR 0004 (about week 5) stays: it is a measurement, not a step in the order.

A module moves up one level only when it supports the thesis or the practitioner names it after a demo, the previous slice is merged with green checks, and, for an AI touchpoint, an eval set fits the owner's label-review time.

**Order** (amended 18 November 2026, below). (1) Proposal Decisions on the Proposals that exist today. (2) Reading quality on TP-201 after the freeze. (3) PW-001 as a held-out Equipment package, and its reading figures. (4) A review package with a site Protocol Draft, and Pre-review of it: TP-201 first, PW-001's after the practitioner session. (5a) The Protocol in TraceQ: a human sets each missing Acceptance Criterion and decides on the drafted Test Steps, and someone other than the preparer approves it as a recorded status. (5b) Execution and Deviation. (6) Document versions, review rounds, export of the Pre-review report. (7) Qualification Report and Equipment Registry. (8) Keycloak and Electronic Signatures. This order replaces the cut line of #29.

**Cutting.** When time runs out the cut starts from the end: 8, then 7, then the approval part of 6. Steps 1–5 carry the thesis and its figures and are not cut. Cutting a step shrinks it to the minimum flow and does not remove it: every stage of the lifecycle keeps at least one screen and one stored status (for step 7, one Qualification Report generated from Execution data and one list of Equipment). Only step 8 may be absent, and the product then says so.

**Audience.** The user in the demo story is the Qualification Engineer or Supervisor. When two pieces of work compete for time, depth in AI, evals and deployment wins, because the project is a portfolio (ADR 0001); every module still keeps its thin path.

## Amended 18 November 2026: work goes on without waiting for the practitioner session

Decided by the owner on #133 (comment 6966596617), after a fresh-context doubt review of the change.

- **PW-001 moves ahead of the review package.** The held-out figure for the thesis is the PW-001 review package, and that still waits for the practitioner session. A clean held-out *reading* figure at a usable n does not wait, and reading accuracy bounds Pre-review. TP-202 cannot give that figure: it is small (13 requirements, 3 defects), LLM-drafted and partly exposed. A separate session writes PW-001 (design §9). The owner first reviews the labels of about ten requirements; the measured time sets how many more fit.
- **The TP-201 review package is written before the session**, with only the defect types that do not wait (design §11). It is labelled "defect types chosen before the practitioner session; dev only". The session's answers land as its next version, and each new defect type's manifest is merged before any rule or prompt for it. Its label review does not run in parallel with PW-001's.
- **The session has a deadline: 5 December 2026.** If it has not taken place by then, what waits for it goes ahead with its [D] default, labelled "not reviewed by a practitioner". The exception is "AC outside Documented Capability", which is not built from a default: it would be a defect type without domain evidence. Defaults cannot answer the two questions above, so without the session the thesis stays a hypothesis.
- **Merges into `main`.** Until 25 November 2026, code for the system under test (`src/traceq`, `web/`) is built on branches and merged afterwards, so the rehearsed demo does not move. Dataset and scorer PRs may merge earlier when the recorded r10 runs replay unchanged and the TP-201 and TP-202 documents keep their bytes.
- **A no-LLM baseline** on TP-201 measures what the LLM adds. Like the SEA-LION spike it is a measurement, not a step in the order. Its rules are frozen before they run on held-out data, and it never replaces an accepted baseline.

Considered: keeping PW-001 at step 5, after Execution. Without a practitioner date that leaves every figure dev-only until December.

## Rules that follow

- No AI touchpoint without an eval set. Wherever a defect rate is reported, wrong findings are reported beside missed ones; a threshold on either is a scoring rule, decided in its own PR.
- Execution runs only from an approved Protocol. An Acceptance Criterion the system read from a document is a Proposal and needs a Proposal Decision before that Protocol can be approved; one a human typed into TraceQ needs no second confirmation (ADR 0002).
- Wherever one record names two roles (preparer and approver, performer and Witness), code refuses the same person, from the first write feature. How a Witness is recorded before Electronic Signatures exist is decided in the Execution spec.
- Eval runs never read Proposal Decisions; a human correction must not raise a score.
- A Proposal keeps its identity across runs, so a decision is not asked twice for the same content.
- What the citation check drops is shown to the reviewer, not only written to the run metadata (ADR 0009).
- Every URS requirement reaches the matrix or is shown as missing: printed requirement numbers are compared with the segmented ones, and URS text that no requirement quotes is listed for the reviewer. Both checks are deterministic (ADR 0009).
- A comparison of numbers is decided by rules over values read with a verified citation; the LLM reads, it does not judge the limit.

## Claims

Allowed: system quality as k/n with the split; cost and duration of one Pre-review; a practitioner's verdict on findings shown in a demo, stated as "one practitioner judged k of N useful"; the number of Proposal Decisions one package needs and the share a human changed. Not allowed: time or review rounds saved, and "compliant". The practitioner's figures describe the problem; they are not results.

## Limits stated openly

Pre-review sees the Documented Capability only: what the Vendor Documents state or show. The capability of the utilities that supply an Equipment (compressed air, HVAC) is out of reach unless their own documents are in the package. Documents are read as PDF, XLSX and scans, not as word-processor files. The evidence for the problem is one qualification team.

## Considered Options

- **Coverage from vendor evidence stays the headline:** built and measured, but no practitioner named it, and suggesting which tests need not be repeated is the AI use with the most direct effect on what gets tested.
- **Full digitisation of the lifecycle as the headline:** almost no AI, commercial products exist, and saved time cannot be measured without users.
