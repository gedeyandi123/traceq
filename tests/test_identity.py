"""Token verification and the demo issuer (spec #105, "Identity and roles"; ADR 0005).

The demo issuer runs as its own application on a free local port (``tests/conftest.py``); the
verifier knows only its URL and fetches the discovery document and the JWKS over HTTP, as it
will from Keycloak.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from conftest import DemoIssuer
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from traceq.app.api import create_app
from traceq.identity import (
    DECIDING_ROLE,
    WITNESSING_ROLE,
    IdentitySettings,
    InvalidToken,
    Principal,
    Verifier,
)
from traceq.identity.issuer import create_issuer, new_signing_key


def _token(issuer: DemoIssuer, username: str) -> str:
    r = httpx.post(f"{issuer.url}/demo/token", json={"username": username})
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture
def verifier(demo_issuer: DemoIssuer) -> Verifier:
    return Verifier(IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience))


def test_a_persona_token_yields_subject_issuer_name_and_roles(
    demo_issuer: DemoIssuer, verifier: Verifier
) -> None:
    persona = httpx.get(f"{demo_issuer.url}/demo/personas").json()[0]
    p = verifier.verify(_token(demo_issuer, persona["username"]))
    assert p.subject == persona["subject"]
    assert p.issuer == demo_issuer.url
    assert p.name == persona["name"]
    assert p.roles == frozenset(persona["roles"])
    assert p.auth_time is not None
    assert p.jti is not None and len(p.jti) > 0
    assert p.amr == frozenset({"demo"})
    assert p.is_demo is True
    assert p.may_decide is (DECIDING_ROLE in persona["roles"])


def _kid(issuer: DemoIssuer) -> str:
    return httpx.get(f"{issuer.url}/jwks").json()["keys"][0]["kid"]


def _forged(
    issuer: DemoIssuer, claims: dict[str, object] | None = None, key: RSAPrivateKey | None = None
) -> str:
    """A token as the demo issuer signs it, with ``claims`` overriding its own."""
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "iss": issuer.url,
        "sub": "demo-0001",
        "aud": issuer.audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "name": "Ayu Kartika Sari",
        "roles": [DECIDING_ROLE],
        **(claims or {}),
    }
    return jwt.encode(payload, key or issuer.key, algorithm="RS256", headers={"kid": _kid(issuer)})


def test_a_forged_token_with_the_issuers_own_claims_verifies(
    demo_issuer: DemoIssuer, verifier: Verifier
) -> None:
    # The control for the refusals below: each changes one thing only.
    assert verifier.verify(_forged(demo_issuer)).subject == "demo-0001"


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"exp": datetime.now(UTC) - timedelta(minutes=1)}, "expired"),
        ({"aud": "another-api"}, "audience"),
        ({"iss": "http://127.0.0.1:1"}, "issuer"),
    ],
    ids=["expired", "wrong audience", "wrong issuer"],
)
def test_a_token_with_a_bad_claim_is_refused(
    demo_issuer: DemoIssuer, verifier: Verifier, change: dict[str, object], why: str
) -> None:
    with pytest.raises(InvalidToken, match=f"(?i){why}"):
        verifier.verify(_forged(demo_issuer, change))


def test_a_token_signed_by_another_key_is_refused(
    demo_issuer: DemoIssuer, verifier: Verifier
) -> None:
    with pytest.raises(InvalidToken, match=r"(?i)signature"):
        verifier.verify(_forged(demo_issuer, key=new_signing_key()))


def test_a_token_naming_an_unpublished_key_is_refused(
    demo_issuer: DemoIssuer, verifier: Verifier
) -> None:
    other = jwt.encode(
        {"iss": demo_issuer.url, "sub": "x", "aud": demo_issuer.audience, "exp": 2**40},
        new_signing_key(),
        algorithm="RS256",
        headers={"kid": "not-published"},
    )
    with pytest.raises(InvalidToken):
        verifier.verify(other)


def test_an_unsigned_token_is_refused(demo_issuer: DemoIssuer, verifier: Verifier) -> None:
    unsigned = jwt.encode(
        {"iss": demo_issuer.url, "sub": "x", "aud": demo_issuer.audience, "exp": 2**40},
        "",
        algorithm="none",
        headers={"kid": _kid(demo_issuer)},
    )
    with pytest.raises(InvalidToken):
        verifier.verify(unsigned)


def test_the_role_claim_is_a_setting(demo_issuer: DemoIssuer) -> None:
    nested = Verifier(
        IdentitySettings(
            issuer=demo_issuer.url,
            audience=demo_issuer.audience,
            role_claim="realm_access.roles",
        )
    )
    token = _forged(demo_issuer, {"roles": None, "realm_access": {"roles": [DECIDING_ROLE]}})
    assert nested.verify(token).may_decide
    # The same token read with the default claim has no roles: it may read, not decide.
    flat = Verifier(IdentitySettings(issuer=demo_issuer.url, audience=demo_issuer.audience))
    assert flat.verify(token).roles == frozenset()


def test_personas_hold_two_deciders_and_one_reader(demo_issuer: DemoIssuer) -> None:
    personas = httpx.get(f"{demo_issuer.url}/demo/personas").json()
    deciders = [p for p in personas if DECIDING_ROLE in p["roles"]]
    assert len(deciders) >= 2
    assert len(personas) - len(deciders) >= 1
    assert len({p["subject"] for p in personas}) == len(personas)


def test_personas_include_witness_only_eko(demo_issuer: DemoIssuer, verifier: Verifier) -> None:
    personas = httpx.get(f"{demo_issuer.url}/demo/personas").json()
    eko = next((p for p in personas if p["username"] == "eko"), None)
    assert eko is not None
    assert eko["roles"] == [WITNESSING_ROLE]
    principal = verifier.verify(_token(demo_issuer, "eko"))
    assert principal.may_witness is True
    assert principal.may_execute is False
    assert principal.may_decide is False
    assert principal.may_approve is False


def test_an_unknown_persona_gets_no_token(demo_issuer: DemoIssuer) -> None:
    r = httpx.post(f"{demo_issuer.url}/demo/token", json={"username": "nobody"})
    assert r.status_code == 404


def test_the_api_serves_none_of_the_issuers_routes(tmp_path: Path) -> None:
    # The issuer is its own application, so Keycloak replaces it by changing the issuer URL.
    issuer = set(create_issuer("http://127.0.0.1:9000", audience="traceq").openapi()["paths"])
    assert issuer == {"/.well-known/openid-configuration", "/jwks", "/demo/personas", "/demo/token"}
    assert issuer.isdisjoint(create_app(tmp_path).openapi()["paths"])


def test_the_demo_issuer_runs_on_the_local_machine_only() -> None:
    with pytest.raises(ValueError, match="local machine"):
        create_issuer("http://0.0.0.0:9000", audience="traceq")
    with pytest.raises(ValueError, match="local machine"):
        create_issuer("http://issuer.example:9000", audience="traceq")


def test_issuer_unavailable_returns_generic_503() -> None:
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    from traceq.identity import IssuerUnavailable
    from traceq.identity.http import authenticate

    class _DownVerifier:
        def verify(self, token: str) -> Principal:
            raise IssuerUnavailable("cannot read http://127.0.0.1:9000/.well-known: [Errno 111]")

    principal = authenticate(_DownVerifier())  # type: ignore[arg-type]
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any-token")
    with pytest.raises(HTTPException) as exc:
        principal(creds)
    assert exc.value.status_code == 503
    assert exc.value.detail == "the identity issuer is temporarily unavailable"


@pytest.mark.parametrize(
    "bad_auth_time",
    [True, False, "1700000000", float("nan"), float("inf"), float("-inf"), 1e20],
    ids=["true", "false", "string", "nan", "inf", "ninf", "overflow"],
)
def test_bad_auth_time_is_refused(
    demo_issuer: DemoIssuer, verifier: Verifier, bad_auth_time: object
) -> None:
    # Note: json.dumps in PyJWT rejects NaN/Inf by default unless allow_nan, so encode raw if needed
    # For nan/inf we test _parse_auth_time directly as well as JWT-encoded values.
    from traceq.identity.tokens import _parse_auth_time

    with pytest.raises(InvalidToken, match="auth_time"):
        _parse_auth_time(bad_auth_time)
    if isinstance(bad_auth_time, bool | str) or bad_auth_time == 1e20:
        with pytest.raises(InvalidToken, match="auth_time"):
            verifier.verify(_forged(demo_issuer, {"auth_time": bad_auth_time}))


@pytest.mark.parametrize("bad_jti", [123, "", "   ", ["a"]], ids=["int", "empty", "blank", "list"])
def test_bad_jti_is_refused(demo_issuer: DemoIssuer, verifier: Verifier, bad_jti: object) -> None:
    with pytest.raises(InvalidToken, match=r"jti|JWT ID"):
        verifier.verify(_forged(demo_issuer, {"jti": bad_jti}))


def test_require_fresh_auth_checks_age_leeway_and_rfc9470(
    demo_issuer: DemoIssuer, verifier: Verifier
) -> None:
    from fastapi import HTTPException

    from traceq.identity.http import require_fresh_auth

    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    checker = require_fresh_auth(verifier, clock=lambda: now)

    fresh = Principal(
        subject="u1",
        issuer=demo_issuer.url,
        name="User",
        roles=frozenset(),
        auth_time=now - timedelta(seconds=64),  # within 60 + 5 leeway
        jti="jti-1",
    )
    assert checker(fresh) == fresh

    stale = Principal(
        subject="u1",
        issuer=demo_issuer.url,
        name="User",
        roles=frozenset(),
        auth_time=now - timedelta(seconds=66),  # > 60 + 5 leeway
        jti="jti-2",
    )
    with pytest.raises(HTTPException) as exc:
        checker(stale)
    assert exc.value.status_code == 401
    assert exc.value.headers == {
        "WWW-Authenticate": 'Bearer error="insufficient_user_authentication", max_age=60'
    }

    future = Principal(
        subject="u1",
        issuer=demo_issuer.url,
        name="User",
        roles=frozenset(),
        auth_time=now + timedelta(seconds=10),  # > 5s future leeway
        jti="jti-3",
    )
    with pytest.raises(HTTPException) as exc_future:
        checker(future)
    assert exc_future.value.status_code == 401
    assert exc_future.value.headers == {
        "WWW-Authenticate": 'Bearer error="insufficient_user_authentication", max_age=60'
    }

    # verifier=None is preserved for openapi_schema()
    none_checker = require_fresh_auth(None, clock=lambda: now)
    with pytest.raises(HTTPException) as exc_none:
        none_checker(fresh)
    assert exc_none.value.status_code == 401
