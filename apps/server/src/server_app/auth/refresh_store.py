"""Persistence for refresh-token rotation and revocation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from server_app.auth.tokens import IssuedPair
from server_app.models import RefreshToken


def register(session: Session, user_id: str, pair: IssuedPair) -> None:
    session.add(
        RefreshToken(
            jti=pair.refresh_jti,
            user_id=user_id,
            expires_at=pair.refresh_expires_at,
        )
    )


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes for tz-aware columns; stored values
    are always UTC, so attach the zone instead of guessing."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def consume(session: Session, jti: str, user_id: str) -> bool:
    """Validate-and-revoke in one step (rotation). False = unknown/replayed."""
    row = session.get(RefreshToken, jti)
    if row is None or row.revoked or row.user_id != user_id:
        return False
    if _aware(row.expires_at) <= datetime.now(timezone.utc):
        return False
    row.revoked = True
    return True


def revoke(session: Session, jti: str, user_id: str) -> bool:
    """Explicit logout. Returns False for unknown/foreign tokens."""
    row = session.get(RefreshToken, jti)
    if row is None or row.user_id != user_id:
        return False
    row.revoked = True
    return True


def revoke_all_for_user(session: Session, user_id: str) -> None:
    """Used when an account is deactivated: kill every session."""
    for row in session.query(RefreshToken).filter(RefreshToken.user_id == user_id):
        row.revoked = True


def purge_expired(session: Session) -> None:
    """Opportunistic cleanup (called on login) — the table stays small."""
    session.execute(
        delete(RefreshToken).where(
            RefreshToken.expires_at <= datetime.now(timezone.utc)
        )
    )
