# Audit trail and signatures "ready for Part 11 / Annex 7", enforced in the database

TraceQ is designed to meet 21 CFR Part 11, CPOB Annex 7 and the draft EU GMP Annex 11 (2025), and is labelled honestly as "designed for, not validated". The controls:

1. An append-only audit trail with a hash chain computed by a **Postgres trigger**, plus `REVOKE UPDATE, DELETE, TRUNCATE` for the application role. An application-level hook would miss writes made through raw SQL.
2. A mandatory reason for every correction of GMP data.
3. Electronic signatures with re-authentication (ADR 0005), a signature meaning (prepared / reviewed / approved / executed / witnessed), and a binding to the hash of the record's content, so a content change invalidates the signature.
4. A Witness (second-person verification) for critical Test Steps.
5. Segregation of duties enforced in code: preparer ≠ approver, performer ≠ Witness.
6. An audit-trail review screen and a periodic user-access review report.
7. The chain's head hash copied periodically to object-lock storage outside the database.

## Consequences

Schema migrations must keep the trigger and grants; integration tests verify the chain and reject direct UPDATE/DELETE.

## Amended 16 November 2026 (ADR 0010)

The controls arrive in three phases.

1. With the first write feature (step 1 of ADR 0010): the append-only Audit Trail enforced in Postgres (revoked grants for the application role and a trigger that rejects UPDATE and DELETE; no hash chain yet), the Reason for Change, Proposal Decisions, and segregation of duties in code wherever one record names two roles. Integration tests reject direct UPDATE, DELETE and TRUNCATE; the chain is tested from phase 3. Until the hash chain exists, the trail resists the application but cannot show tampering by a database administrator; the documentation says so.
2. With Electronic Signatures (step 8 of ADR 0010, the first step cut when time runs out): signatures bound to content, re-authentication (ADR 0005), and the Witness's signature. Before that, an approval is a recorded status and is labelled "not an Electronic Signature".
3. Beyond the eight steps of ADR 0010: the hash chain and its head copy, the audit-trail review screen and the access review report.

A Proposal Decision is not an Electronic Signature.

## Amended 19 November 2026 (ADR 0013)

Control 4 waits for step 6 of ADR 0010. From step 5b a Witness confirms a Result while signed in, and code refuses a Witness who is the Performer, but no Test Step requires a Witness: which ones do is a flag on the Protocol, and the owner has not yet adopted the practitioner's rule for it.

## Amended 26 November 2026 (step 8)

Step 8 of ADR 0010 is built, so the second phase above no longer describes the product. Protocol submission (`prepared`), Protocol Approval, Witness confirmation, Deviation Closure and Qualification Report approval (all `approved` or `witnessed`) are signed, each bound to the hash of the record's content. The label is "Electronic Signature" when the identity provider is Keycloak (OIDC, with re-authentication), and "Demo signature" in demo mode, which uses a demo identity without password re-authentication and is not an Electronic Signature.

A "recorded status" now applies only to records written before step 8 (labelled "a recorded status, not an Electronic Signature", which the Qualification Report snapshot and its PDF keep verbatim), to Execution completion and round closing, and to Proposal Decisions.

The claim stays "designed for, not validated". Nothing in the product says it complies with 21 CFR Part 11, CPOB Annex 7 or the draft EU GMP Annex 11 (2025).
