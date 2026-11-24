"""Verifying standard OIDC tokens through the issuer's JWKS (ADR 0005).

Nothing here is specific to one identity provider: the verifier is given an issuer URL, reads
its discovery document, and checks a token's signature against the published keys, then its
issuer, audience and expiry. Which claim holds the roles is a setting, since OIDC fixes none.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, cast

import jwt

# The one role that may import a run and record Proposal Decisions in slice 1 (spec #105).
DECIDING_ROLE = "qualification-decider"
# The role that approves or returns a submitted Protocol (spec #247, ADR 0012); kept apart
# from deciding, so no demo persona holds both.
APPROVING_ROLE = "qualification-approver"
# The role that executes an Approved Protocol (ADR 0013, spec #270).
EXECUTING_ROLE = "qualification-executor"


class InvalidToken(Exception):
    """The token is not one this API accepts: bad signature, issuer, audience or expiry."""


class IssuerUnavailable(Exception):
    """The issuer's discovery document or JWKS could not be read."""


@dataclass(frozen=True)
class IdentitySettings:
    """``issuer``: the trusted issuer URL, exactly as its tokens name it. ``audience``: what a
    token must be issued for. ``role_claim``: the claim holding the roles, a dotted path for a
    nested claim (Keycloak's realm roles are ``realm_access.roles``)."""

    issuer: str
    audience: str
    role_claim: str = "roles"
    algorithms: tuple[str, ...] = ("RS256",)


@dataclass(frozen=True)
class Principal:
    """Who a verified token names: subject and issuer, the name to show, and the roles."""

    subject: str
    issuer: str
    name: str
    roles: frozenset[str]

    @property
    def may_decide(self) -> bool:
        return DECIDING_ROLE in self.roles

    @property
    def may_approve(self) -> bool:
        return APPROVING_ROLE in self.roles

    @property
    def may_execute(self) -> bool:
        return EXECUTING_ROLE in self.roles


def _get_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data: object = json.load(r)
    except (OSError, ValueError) as e:
        raise IssuerUnavailable(f"cannot read {url}: {e}") from e
    if not isinstance(data, dict):
        raise IssuerUnavailable(f"{url} is not a JSON object")
    return cast(dict[str, Any], data)


def _roles(payload: dict[str, Any], path: str) -> frozenset[str]:
    """The strings at the dotted ``path``; none when the claim is missing or not a list."""
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return frozenset()
        value = cast(dict[str, Any], value).get(part)
    if not isinstance(value, list):
        return frozenset()
    return frozenset(r for r in cast(list[Any], value) if isinstance(r, str))


class Verifier:
    """Verifies bearer tokens of one trusted issuer. The discovery document is read on the
    first token; the JWKS is cached and read again when a token names an unknown key."""

    def __init__(self, settings: IdentitySettings) -> None:
        self.settings = settings
        self._keys: jwt.PyJWKClient | None = None

    def _jwks(self) -> jwt.PyJWKClient:
        if self._keys is None:
            issuer = self.settings.issuer.rstrip("/")
            discovery = _get_json(f"{issuer}/.well-known/openid-configuration")
            if discovery.get("issuer") != self.settings.issuer:
                raise IssuerUnavailable(
                    f"the discovery document names issuer {discovery.get('issuer')!r},"
                    f" not {self.settings.issuer!r}"
                )
            jwks_uri = discovery.get("jwks_uri")
            if not isinstance(jwks_uri, str):
                raise IssuerUnavailable("the discovery document has no jwks_uri")
            self._keys = jwt.PyJWKClient(jwks_uri, timeout=10)
        return self._keys

    def verify(self, token: str) -> Principal:
        s = self.settings
        try:
            key = self._jwks().get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as e:
            raise IssuerUnavailable(str(e)) from e
        except jwt.PyJWKClientError as e:
            raise InvalidToken(f"no published key verifies this token: {e}") from e
        except jwt.InvalidTokenError as e:
            raise InvalidToken(str(e)) from e
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=list(s.algorithms),
                audience=s.audience,
                issuer=s.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as e:
            raise InvalidToken(str(e)) from e
        subject = str(payload["sub"])
        name = payload.get("name") or payload.get("preferred_username") or subject
        return Principal(
            subject=subject,
            issuer=str(payload["iss"]),
            name=str(name),
            roles=_roles(payload, s.role_claim),
        )
