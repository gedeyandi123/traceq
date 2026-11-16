"""The bearer token of a request, as a FastAPI dependency.

``authenticate(None)`` is the API with default settings: it trusts no issuer, so every route
that depends on it answers 401, also for a token the demo issuer signed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from traceq.identity.tokens import InvalidToken, IssuerUnavailable, Principal, Verifier

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
            raise HTTPException(503, f"the issuer cannot be reached: {e}") from e

    return principal
