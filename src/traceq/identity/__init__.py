"""Who is acting: OIDC token verification and roles (spec #105, ADR 0005).

``Verifier`` checks a bearer token against a trusted issuer's JWKS and yields a ``Principal``.
The demo issuer (``traceq.identity.issuer``) is a separate application; the API never imports
it and knows only its URL.
"""

from traceq.identity.tokens import (
    APPROVING_ROLE,
    DECIDING_ROLE,
    EXECUTING_ROLE,
    IdentitySettings,
    InvalidToken,
    IssuerUnavailable,
    Principal,
    Verifier,
)

__all__ = [
    "APPROVING_ROLE",
    "DECIDING_ROLE",
    "EXECUTING_ROLE",
    "IdentitySettings",
    "InvalidToken",
    "IssuerUnavailable",
    "Principal",
    "Verifier",
]
