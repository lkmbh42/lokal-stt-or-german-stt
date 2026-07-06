"""Login / token refresh / whoami."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from server_app import audit
from server_app.auth.backend import AuthBackend
from server_app.auth.deps import CurrentUser, get_db, get_token_service
from server_app.auth.tokens import TokenError, TokenService
from server_app.models import User
from server_app.schemas import LoginRequest, RefreshRequest, TokenPairOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_backend(request: Request) -> AuthBackend:
    return request.app.state.auth_backend  # type: ignore[no-any-return]


@router.post("/login")
def login(
    request: Request,
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
    backend: Annotated[AuthBackend, Depends(get_auth_backend)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPairOut:
    ip = request.client.host if request.client else None
    user = backend.authenticate(db, body.username, body.password)
    if user is None:
        audit.record(
            db, audit.LOGIN_FAILED, username=body.username[:150], ip=ip
        )
        db.commit()  # failed-login audit must survive the 401 rollback
        # single generic message: no username/password oracle
        raise HTTPException(status_code=401, detail="Anmeldung fehlgeschlagen")
    audit.record(db, audit.LOGIN, user=user, ip=ip)
    access, refresh = tokens.issue_pair(user.id, user.role)
    return TokenPairOut(access_token=access, refresh_token=refresh)


@router.post("/refresh")
def refresh(
    body: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPairOut:
    try:
        payload = tokens.decode(body.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = db.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Konto deaktiviert")
    # role is re-read from the DB, not from the old token: demotions apply
    access, new_refresh = tokens.issue_pair(user.id, user.role)
    return TokenPairOut(access_token=access, refresh_token=new_refresh)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_model(user)
