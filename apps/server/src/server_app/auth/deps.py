"""FastAPI auth dependencies: bearer-token → User, plus RBAC guards."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from server_app.auth.tokens import TokenError, TokenService
from server_app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Session:
    """Request-scoped session; committed/closed by the app middleware."""
    return request.state.db  # type: ignore[no-any-return]


def get_token_service(request: Request) -> TokenService:
    return request.app.state.tokens  # type: ignore[no-any-return]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Nicht angemeldet")
    try:
        payload = tokens.decode(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = db.get(User, payload.user_id)
    # is_active is enforced live, not from the token: deactivating a user
    # locks them out within one access-token lifetime at most
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Konto deaktiviert")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Nur für Administratoren")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
