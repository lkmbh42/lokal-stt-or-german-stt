"""JWT access/refresh token service (HS256, PyJWT).

* Access tokens: short-lived, carry ``sub`` (user id) and ``role``.
* Refresh tokens: longer-lived, exchanged for a fresh pair (rotation).
* ``type`` claim prevents cross-use — a refresh token is never accepted
  where an access token is required and vice versa.

Known tradeoff (documented for the Phase 4 security pass): there is no
server-side refresh-token denylist yet, so a stolen refresh token stays
valid until expiry. Mitigations today: 7-day default TTL and per-user
``is_active`` (deactivation is checked on every request, killing access
within one access-token lifetime).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    role: str
    token_type: str


class TokenService:
    def __init__(
        self,
        secret_key: str,
        access_ttl: timedelta = timedelta(minutes=15),
        refresh_ttl: timedelta = timedelta(days=7),
    ):
        self._secret = secret_key
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl

    def _issue(self, user_id: str, role: str, token_type: str, ttl: timedelta) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": user_id,
                "role": role,
                "type": token_type,
                "iat": now,
                "exp": now + ttl,
                "jti": uuid.uuid4().hex,
            },
            self._secret,
            algorithm="HS256",
        )

    def issue_pair(self, user_id: str, role: str) -> tuple[str, str]:
        return (
            self._issue(user_id, role, "access", self._access_ttl),
            self._issue(user_id, role, "refresh", self._refresh_ttl),
        )

    def decode(self, token: str, expected_type: str) -> TokenPayload:
        try:
            claims = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("Token abgelaufen") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError("Ungültiges Token") from exc
        if claims.get("type") != expected_type:
            raise TokenError("Falscher Token-Typ")
        sub, role = claims.get("sub"), claims.get("role")
        if not isinstance(sub, str) or not isinstance(role, str):
            raise TokenError("Ungültiges Token")
        return TokenPayload(user_id=sub, role=role, token_type=expected_type)
