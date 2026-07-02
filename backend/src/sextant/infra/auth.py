from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import jwt
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError


@dataclass(frozen=True, slots=True)
class JwksJwtVerifier:
    issuer: str
    audience: str
    jwks_url: str
    algorithms: tuple[str, ...] = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")
    _jwk_client: PyJWKClient = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_jwk_client", PyJWKClient(self.jwks_url))

    def actor_id_for_authorization(self, authorization: str | None) -> UUID | None:
        token = _bearer_token(authorization)
        if token is None:
            return None
        try:
            key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=list(self.algorithms),
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except (InvalidTokenError, PyJWKClientError, ValueError):
            return None
        subject = claims.get("sub")
        if not isinstance(subject, str):
            return None
        try:
            return UUID(subject)
        except ValueError:
            return None


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.casefold() != "bearer" or not token.strip():
        return None
    return token.strip()
