"""The bearer token of a request, as a FastAPI dependency.

``authenticate(None)`` is the API with default settings: it trusts no issuer, so every route
that depends on it answers 401, also for a token the demo issuer signed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from traceq.identity.tokens import InvalidToken, IssuerUnavailable, Principal, Verifier

_LOG = logging.getLogger(__name__)
_BEARER = HTTPBearer(auto_error=False)
_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def authenticate(verifier: Verifier | None) -> Callable[..., Principal]:
    """A dependency yielding the verified ``Principal`` of the request's bearer token."""

    def principal(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)],
    ) -> Principal:
        if verifier is None:
            raise HTTPException(401, "no trusted issuer is configured", _CHALLENGE)
        if credentials is None:
            raise HTTPException(401, "a bearer token is required", _CHALLENGE)
        try:
            return verifier.verify(credentials.credentials)
        except InvalidToken as e:
            raise HTTPException(401, f"invalid token: {e}", _CHALLENGE) from e
        except IssuerUnavailable as e:
            _LOG.warning("identity issuer unavailable: %s", e)
            raise HTTPException(503, "the identity issuer is temporarily unavailable") from e

    return principal


def reauthentication_required(detail: str, max_age: int | None = None) -> HTTPException:
    """The 401 asking the client to authenticate the user again (RFC 9470), for a signing
    action whose token has no usable ``auth_time`` or ``jti``."""
    challenge = 'Bearer error="insufficient_user_authentication"'
    if max_age is not None:
        challenge += f", max_age={max_age}"
    return HTTPException(401, detail, {"WWW-Authenticate": challenge})


def require_fresh_auth(
    verifier: Verifier | None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Callable[[Principal], Principal]:
    """Return a checker enforcing fresh ``auth_time`` and non-null ``jti`` on ``Principal``.

    Preserves ``verifier=None`` for ``openapi_schema()``. Run AFTER 403 role checks so callers
    without the required role receive 403 before 401 re-authentication challenges.
    """
    max_age = 60 if verifier is None else verifier.settings.max_auth_age_seconds
    leeway = 5 if verifier is None else verifier.settings.clock_skew_leeway_seconds
    challenge = {
        "WWW-Authenticate": (f'Bearer error="insufficient_user_authentication", max_age={max_age}')
    }

    def check(principal: Principal) -> Principal:
        if verifier is None:
            raise HTTPException(401, "no trusted issuer is configured", _CHALLENGE)
        if principal.auth_time is None:
            raise HTTPException(401, "re-authentication required: missing auth_time", challenge)
        if principal.jti is None:
            raise HTTPException(401, "re-authentication required: missing jti", challenge)
        now = clock()
        age = (now - principal.auth_time).total_seconds()
        if age < -leeway:
            raise HTTPException(
                401,
                "re-authentication required: auth_time is in the future",
                challenge,
            )
        if age > max_age + leeway:
            raise HTTPException(
                401,
                f"re-authentication required: auth_time is older than {max_age}s",
                challenge,
            )
        return principal

    return check
