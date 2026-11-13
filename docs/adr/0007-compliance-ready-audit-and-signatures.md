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
