"""The demo issuer: a small OIDC issuer of its own, for demo identities only (spec #105).

A separate application from the API: the API knows only its URL, so Keycloak replaces it by
changing that URL (ADR 0005). It publishes a discovery document and a JWKS and signs tokens
for the seeded personas, whose names are fictional. There is no password: the web server asks
for a named persona's token (``POST /demo/token``). That is why it is off by default, started
only by an explicit command, and listens on the local machine only.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import FastAPI, HTTPException
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

from traceq.identity.tokens import (
    APPROVING_ROLE,
    DECIDING_ROLE,
    EXECUTING_ROLE,
    WITNESSING_ROLE,
)

LOOPBACK = ("127.0.0.1", "localhost")


class Persona(BaseModel):
    """A seeded demo account. ``subject`` is stable, as an identity provider's would be."""

    username: str
    subject: str
    name: str
    roles: list[str]


# Fictional people. Two hold the deciding and executing roles, one may only read, one holds
# only the approving role (ADR 0012, ADR 0013), and one holds only the witnessing role (ADR 0013,
# spec #274): no persona both decides and approves.
PERSONAS = (
    Persona(
        username="ayu",
        subject="demo-0001",
        name="Ayu Kartika Sari",
        roles=[DECIDING_ROLE, EXECUTING_ROLE],
    ),
    Persona(
        username="bima",
        subject="demo-0002",
        name="Bima Arya Nugraha",
        roles=[DECIDING_ROLE, EXECUTING_ROLE],
    ),
    Persona(username="citra", subject="demo-0003", name="Citra Maharani Putri", roles=[]),
    Persona(
        username="dewi",
        subject="demo-0004",
        name="Dewi Anggraini Lestari",
        roles=[APPROVING_ROLE],
    ),
    Persona(
        username="eko",
        subject="demo-0005",
        name="Eko Prasetyo Wijaya",
        roles=[WITNESSING_ROLE],
    ),
)


class TokenRequest(BaseModel):
    username: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


def new_signing_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def create_issuer(
    url: str,
    *,
    audience: str,
    key: RSAPrivateKey | None = None,
    role_claim: str = "roles",
    lifetime: timedelta = timedelta(hours=8),
    personas: tuple[Persona, ...] = PERSONAS,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    """The issuer application for ``url`` (``http://127.0.0.1:<port>``), signing tokens for
    ``audience``. A new signing key per start unless one is given."""
    if urlsplit(url).hostname not in LOOPBACK:
        raise ValueError(f"the demo issuer runs on the local machine only, not at {url}")
    signing_key = key or new_signing_key()
    kid = uuid.uuid4().hex
    jwk: dict[str, Any] = {
        **RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True),
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
    }
    by_username = {p.username: p for p in personas}

    app = FastAPI(
        title="TraceQ demo issuer",
        version="0.1.0",
        summary="Demo identities only: signs tokens for seeded personas, no password.",
    )

    @app.get("/.well-known/openid-configuration")
    def discovery() -> dict[str, Any]:
        return {
            "issuer": url,
            "jwks_uri": f"{url}/jwks",
            "token_endpoint": f"{url}/demo/token",
            "response_types_supported": ["token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    @app.get("/jwks")
    def jwks() -> dict[str, Any]:
        return {"keys": [jwk]}

    @app.get("/demo/personas")
    def list_personas() -> list[Persona]:
        return list(personas)

    @app.post("/demo/token")
    def token(request: TokenRequest) -> TokenResponse:
        p = by_username.get(request.username)
        if p is None:
            raise HTTPException(404, f"no persona {request.username!r}")
        now = clock()
        claims: dict[str, Any] = {
            "iss": url,
            "sub": p.subject,
            "aud": audience,
            "iat": now,
            "auth_time": int(now.timestamp()),
            "exp": now + lifetime,
            "jti": uuid.uuid4().hex,
            "amr": ["demo"],
            "name": p.name,
            "preferred_username": p.username,
            role_claim: p.roles,
        }
        signed = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": kid})
        return TokenResponse(access_token=signed, expires_in=int(lifetime.total_seconds()))

    return app
