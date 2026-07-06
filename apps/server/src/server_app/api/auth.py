"""Login / token refresh / logout / whoami.

Security posture (Phase 4):
* per-IP sliding-window rate limit on login and refresh (429 + Retry-After),
* refresh tokens are registered server-side and rotated on use — a replayed
  refresh token is rejected and the incident is audited,
* logout revokes the presented refresh token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from server_app import audit
from server_app.auth import refresh_store
from server_app.auth.backend import AuthBackend
from server_app.auth.deps import CurrentUser, get_db, get_token_service
from server_app.auth.tokens import TokenError, TokenService
from server_app.models import User
from server_app.ratelimit import RateLimiter
from server_app.schemas import LoginRequest, RefreshRequest, TokenPairOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_backend(request: Request) -> AuthBackend:
    return request.app.state.auth_backend  # type: ignore[no-any-return]


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.auth_limiter
    retry_after = limiter.check(_ip(request))
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Zu viele Anmeldeversuche. Bitte kurz warten.",
            headers={"Retry-After": str(max(int(retry_after) + 1, 1))},
        )


@router.post("/login")
def login(
    request: Request,
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
    backend: Annotated[AuthBackend, Depends(get_auth_backend)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPairOut:
    _enforce_rate_limit(request)
    ip = _ip(request)
    user = backend.authenticate(db, body.username, body.password)
    if user is None:
        audit.record(db, audit.LOGIN_FAILED, username=body.username[:150], ip=ip)
        db.commit()  # failed-login audit must survive the 401 rollback
        # single generic message: no username/password oracle
        raise HTTPException(status_code=401, detail="Anmeldung fehlgeschlagen")
    refresh_store.purge_expired(db)
    pair = tokens.issue_pair(user.id, user.role)
    refresh_store.register(db, user.id, pair)
    audit.record(db, audit.LOGIN, user=user, ip=ip)
    return TokenPairOut(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/refresh")
def refresh(
    request: Request,
    body: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPairOut:
    _enforce_rate_limit(request)
    try:
        payload = tokens.decode(body.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = db.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Konto deaktiviert")
    if not refresh_store.consume(db, payload.jti, user.id):
        # replay of a rotated/revoked token — audit it, it may be theft
        audit.record(
            db,
            audit.TOKEN_REPLAYED,
            user=user,
            detail=f"jti {payload.jti}",
            ip=_ip(request),
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Token nicht mehr gültig")
    # role is re-read from the DB, not from the old token: demotions apply
    pair = tokens.issue_pair(user.id, user.role)
    refresh_store.register(db, user.id, pair)
    return TokenPairOut(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    body: RefreshRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> Response:
    try:
        payload = tokens.decode(body.refresh_token, expected_type="refresh")
    except TokenError:
        return Response(status_code=204)  # already dead — nothing to revoke
    if payload.user_id == user.id:
        refresh_store.revoke(db, payload.jti, user.id)
        audit.record(db, audit.LOGOUT, user=user, ip=_ip(request))
    return Response(status_code=204)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_model(user)
