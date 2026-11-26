# Pilot readiness

Status: partial (26 November 2026). Section 5 and the new section "What changes at a real plant" state facts observed in the code at this date; sections 1, 3 and 6 wait for the practitioner session (D14, issue #245) and are not filled. This document answers "what would it take to run TraceQ at a real plant?" without running a pilot during the portfolio phase (ADR 0001). Nothing here describes a real plant.

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

## What changes at a real plant

The demo is built for local, synthetic use (ADR 0001). Each item below is a fact observed in the code, why it matters outside the demo, and the action it needs. TraceQ is designed for these changes, not validated against any of them. Paths are relative to the repository root.

1. **Demo status comes from one claim.** `is_demo` is true when the `amr` claim contains `demo` (`src/traceq/identity/tokens.py:64-66`). Token verification requires `exp`, `iss`, `aud` and `sub` and checks no `azp` (`tokens.py:142-149`). The reference realm sets no `amr` mapper (`compose/keycloak/traceq-realm.json` has no `amr` entry), so the risk applies to a plant identity provider that exposes `amr` to clients. Why it matters: such a provider could make a session look like a demo session. Action: the plant's identity provider must control `amr`, and the demo issuer must not be reachable (items 4 and 8). Whether to add an `azp` check is for the owner to decide, not part of this document.
2. **The reference realm is a demo realm.** Every account password in the Keycloak realm is `demo` (`compose/keycloak/traceq-realm.json`, five accounts, `"value": "demo"` entries from line 40), and the file configures no brute-force protection, password policy or one-time passcode. Keycloak runs as `start-dev` with an `http` hostname (`compose.yaml:26-28`). Action: use the plant's own identity provider (ADR 0005) with its own password, lockout and multi-factor policy, over TLS.
3. **Cookie settings depend on the environment.** The `Secure` attribute is automatic only when `TRACEQ_PUBLIC_URL` starts with `https://`. An explicit `TRACEQ_COOKIE_SECURE` of `true` or `false` wins, and with neither set (an unset `TRACEQ_PUBLIC_URL` included) the default is `false` (`web/src/auth/oidc.ts:18-30`). Action: deploy behind https and set `TRACEQ_PUBLIC_URL` accordingly.
4. **The demo issuer signs a token for any named persona without authentication.** `POST /demo/token` (`src/traceq/identity/issuer.py:139`) does not authenticate callers. The issuer refuses to be built for a non-loopback URL, checked once at construction (`issuer.py:32`, `issuer.py:102`). Every token it mints carries `amr: ["demo"]` (`issuer.py:153`). Action: the demo issuer must never run at a plant, and the application must not trust its keys.
5. **The ID token is read, not verified.** The normal sign-in branch of the callback decodes the ID token payload and checks only `nonce`; it does not check `iss` or `aud` of the ID token (`web/src/app/api/auth/callback/route.ts:105-106`; `decodeJwtPayload` at `web/src/auth/oidc.ts:73`). The reauth branch compares `sub` and `iss` with `tx.expectedSub` and `tx.expectedIss`, but reads them from the unverified access-token payload, falling back to the ID token (`route.ts:112-118`). The access token, the credential the API receives, is verified by the API on every call: signature through the JWKS, `exp`, `iss`, `aud` and `sub` (`src/traceq/identity/tokens.py:142-149`). The ID token serves the nonce check and is stored in a cookie. From OIDC Core 3.1.3.7, not re-checked here: validation of the TLS server may stand in for the signature check only, and the `iss` and `aud` checks still apply, so the missing checks fall short of the specification; the demo also uses `http`. Action: keep the token-endpoint channel on TLS and decide whether to add the `iss` and `aud` checks (see Open questions).
6. **Unknown signing keys do not cause unbounded JWKS refetches, by library behaviour.** An unknown `kid` forces one refresh only when PyJWT's cooldown has passed, and `cooldown_duration` defaults to 30 seconds (`jwt/jwks_client.py:45`, `jwt/jwks_client.py:281-291`; PyJWT 2.15.1 is locked at `uv.lock:1907`). The protection is a property of the locked version, not of TraceQ code. Action: keep PyJWT pinned and re-check this behaviour when upgrading.
7. **The registry list issues queries inside loops.** `list_equipment` (`src/traceq/registry/api.py:90-91`) executes queries inside its loops over review rounds, protocols, executions and Deviations (`registry/api.py:122`, `:166`, `:204`, `:232`). This is a scale issue, not a security one: the demo has a handful of Equipment. Action: measure against a plant-sized registry and batch the queries if needed.
8. **Demo mode mints fresh tokens from an unverified cookie.** In demo mode `consumeSignatureBearerHeaders` reads `preferred_username` from the stored token without verifying it and requests a new token for that user from `/demo/token` (`web/src/auth/session.ts:120-153`). This is by design for the demo, and it is the reason demo mode must not be switchable on at a plant. Action: the demo setting must be absent from a plant deployment, not merely off.
9. **The database superuser is written in the code.** The Compose Postgres uses `POSTGRES_PASSWORD: postgres` on a port bound to `127.0.0.1` (`compose.yaml:9-13`), and `ADMIN_URL` holds the same credentials (`src/traceq/app/demo.py:44`). Action: a plant database needs its own credentials and roles, held outside the code; the application role keeps read-and-append rights on the Audit Trail only.
10. **ADR 0007 phase 3 is not built.** The Audit Trail resists the application but cannot show a change made by a database administrator, as ADR 0007 says in its amendment of 16 November 2026 (items 1 and 3, `docs/adr/0007-compliance-ready-audit-and-signatures.md`). ADR 0010 lists phase 3 under "Later (design only)" (`docs/adr/0010-pre-review-of-site-documents-is-the-claim.md:14`). Action: see section 5 for what exists and what does not.

## 3. Data and permission path

Written permission from the plant's QA, IT and management comes before any real document is used. Data and models stay on site, and personal data follows UU PDP. To be completed: the steps, the documents each party needs, and what may leave the plant (scores only). Who decides on a new tool, and what they require before it may be used, is not yet known (D14, `docs/review/tp201-practitioner-q16.md:96`, issue #245).

## 4. Mode Pabrik

A local model on the plant's own server (ADR 0004). To be completed: the model, hardware, RAM and time per document, and its eval scores beside Mode Cloud.

## 5. System validation

Only facts present in the code are recorded here. The validation plan itself, against the draft Annex 11 and CPOB Annex 7, is not written. TraceQ is designed for this review, not validated.

Built:

- **Append-only Audit Trail.** The application role may read and append, triggers refuse UPDATE, DELETE and TRUNCATE, and the database clock stamps each entry (`src/traceq/db/migrations/versions/0001_audit_trail.py:3-6`, `:41-65`; ADR 0007).
- **Electronic Signatures of Step 8.** Signatures are stored in an append-only table guarded by the same `refuse_change()` triggers (`src/traceq/db/migrations/versions/0018_electronic_signatures.py:11`, `:155-167`; `src/traceq/audit/signatures.py`). A signing action without fresh authentication is refused rather than recorded unsigned (`signatures.py:80-83`, `require_signing_claims` at `signatures.py:87`).
- **Segregation of duties in code** where one record names two roles, for example Deviation close (`src/traceq/execution/deviations.py:389`) and Qualification Report approval (`src/traceq/execution/reports.py:141`).

Not built (ADR 0007 phase 3, "Later (design only)" in ADR 0010):

- the hash chain over Audit Trail entries
- the periodic copy of the chain head to storage outside the database
- the audit-trail review screen
- the periodic user-access review report

Until the chain exists, the Audit Trail cannot show tampering by a database administrator.

To be completed (nothing in the code to describe yet):

- supplier and SaaS oversight for Mode Cloud
- the URS and traceability of TraceQ itself
- periodic review
- model and prompt changes handled as change control (ADR 0009)

## 6. Private eval set

Built at the plant after permission. Data stays on site, the model runs locally, and plant experts set the labels. The set is organised by kind of variation (vendor, document type, scan quality), not by item of Equipment. To be completed: size, labelling effort, and how results are reported without exposing documents.

## 7. Open questions

- **D14, who decides on a new tool:** who at the plant decides on a new working tool for the team (head of department, QA, IT or management), and what is required before it may be used (`docs/review/tp201-practitioner-q16.md:96`). The answer decides sections 1, 3 and 6 and waits for the practitioner session (issue #245).
- **ID token checks:** whether the sign-in callback should also check `iss` and `aud` of the ID token (item 5 above). It is a small change and is not made here; the owner decides whether it becomes its own issue.
