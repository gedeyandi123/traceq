# Pilot readiness

Status: skeleton (14 November 2026). The sections are filled in during weeks 9–10. This document answers "what would it take to run TraceQ at a real plant?" without running a pilot during the portfolio phase (ADR 0001). Nothing here describes a real plant.

## 1. Regulatory position

TraceQ is a non-critical, human-in-the-loop aid: the LLM drafts and the engineer decides (ADR 0002, ADR 0009). To be completed: how the plant's QA classifies the use, the intended-use statement, and what changes once the final Annex 22 and Annex 11 are published.

## 2. What stays and what changes

- **Expected to stay:** UI, backend, decision table, citation check, eval harness.
- **Measured again, likely to change:**
  - the document reader (vendor formats, scans, handwriting)
  - the prompts
  - the model (local, ADR 0004)
  - plant-specific rules, kept as configuration
  - login (the plant's identity provider, ADR 0005)
- **Large work outside the code:** a real answer key, system validation, permissions and infrastructure.

To be completed: the measurements from the public real documents (ADR 0001) and the held-out set.

## 3. Data and permission path

Written permission from the plant's QA, IT and management comes before any real document is used. Data and models stay on site, and personal data follows UU PDP. To be completed: the steps, the documents each party needs, and what may leave the plant (scores only).

## 4. Mode Pabrik

A local model on the plant's own server (ADR 0004). To be completed: the model, hardware, RAM and time per document, and its eval scores beside Mode Cloud.

## 5. System validation

To be completed, against the draft Annex 11 and CPOB Annex 7:

- a risk-based validation plan
- supplier and SaaS oversight for Mode Cloud
- the URS and traceability of TraceQ itself
- audit trail and e-signatures (ADR 0007)
- periodic review
- model and prompt changes handled as change control (ADR 0009)

## 6. Private eval set

Built at the plant after permission. Data stays on site, the model runs locally, and plant experts set the labels. The set is organised by kind of variation (vendor, document type, scan quality), not by item of Equipment. To be completed: size, labelling effort, and how results are reported without exposing documents.

## 7. Open questions

To be completed.
