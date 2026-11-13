# AI only proposes; pass/fail is decided by deterministic code

The LLM produces AI Findings only (drafted Protocols, Pre-review, extraction), and a human decides on each one. The LLM never approves, signs, changes an official record, sets an Acceptance Criterion, or decides pass/fail; a Test Step result is evaluated against its Acceptance Criterion by deterministic code. This follows the draft EU GMP Annex 22 (July 2025), which limits critical GMP applications to static, deterministic models and excludes LLMs and generative AI from critical use; Indonesia is a PIC/S member, so CPOB is likely to follow.

## Consequences

Every AI Finding stores its source document and revision, model, prompt, time and the reviewer's action, so it can be audited.
