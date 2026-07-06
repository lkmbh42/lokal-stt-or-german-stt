"""JWT access/refresh token service (HS256, PyJWT).

* Access tokens: short-lived, carry ``sub`` (user id) and ``role``.
* Refresh tokens: longer-lived, exchanged for a fresh pair (rotation).
* ``type`` claim prevents cross-use — a refresh token is never accepted
  where an access token is required and vice versa.
* Refresh tokens are additionally tracked server-side by ``jti`` (see
  ``server_app.auth.refresh_store``): rotation revokes the old token, logout
  revokes explicitly, and a replayed (already-rotated) refresh token is
  rejected — closing the Phase 2 "stolen refresh token lives until expiry"
  tradeoff.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class IssuedPair:
    access_token: str
    refresh_token: str
    refresh_jti: str
    refresh_expires_at: datetime


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    role: str
    token_type: str
    jti: str
    expires_at: datetime


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

    def _issue(
        self, user_id: str, role: str, token_type: str, ttl: timedelta
    ) -> tuple[str, str, datetime]:
        now = datetime.now(timezone.utc)
        jti = uuid.uuid4().hex
        expires_at = now + ttl
        token = jwt.encode(
            {
                "sub": user_id,
                "role": role,
                "type": token_type,
                "iat": now,
                "exp": expires_at,
                "jti": jti,
            },
            self._secret,
            algorithm="HS256",
        )
        return token, jti, expires_at

    def issue_pair(self, user_id: str, role: str) -> IssuedPair:
        access, _, _ = self._issue(user_id, role, "access", self._access_ttl)
        refresh, refresh_jti, refresh_expires = self._issue(
            user_id, role, "refresh", self._refresh_ttl
        )
        return IssuedPair(
            access_token=access,
            refresh_token=refresh,
            refresh_jti=refresh_jti,
            refresh_expires_at=refresh_expires,
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
        sub, role, jti = claims.get("sub"), claims.get("role"), claims.get("jti")
        if not isinstance(sub, str) or not isinstance(role, str) or not isinstance(jti, str):
            raise TokenError("Ungültiges Token")
        return TokenPayload(
            user_id=sub,
            role=role,
            token_type=expected_type,
            jti=jti,
            expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        )
