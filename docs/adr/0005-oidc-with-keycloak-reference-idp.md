# The app speaks standard OIDC; Keycloak is the reference IdP

TraceQ knows only standard OpenID Connect (tokens verified through JWKS), not a Keycloak-specific API. Keycloak is the reference IdP in the demo because it can be self-hosted on-premises and can broker to the Microsoft Entra ID / Active Directory common in plants, and it provides MFA, lockout and an event log, which answer the Identity and Access Management section of the draft EU GMP Annex 11 (2025).

An electronic signature requires re-authentication at the moment of signing: the frontend asks for a fresh login (`prompt=login` / `max_age=0`), and FastAPI itself refuses a signature whose `auth_time` claim is older than a short window (about 60 seconds). The server-side check is mandatory because Keycloak's `prompt=login` behaviour is reported to be inconsistent.

## Considered Options

- Entra ID directly: cannot be demonstrated self-hosted.
- Zitadel / Authentik: weaker AD federation for the plant case.
- Better Auth: ties auth to Next.js, while the domain and signatures live in FastAPI.
