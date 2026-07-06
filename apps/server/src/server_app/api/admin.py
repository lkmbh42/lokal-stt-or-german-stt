"""Admin endpoints — user management and cross-user job overview.

Every route requires the ``admin`` role (403 otherwise).
"""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from server_app import audit
from server_app.auth.deps import AdminUser, get_db
from server_app.auth.passwords import hash_password
from server_app.config import ServerSettings
from server_app.models import AuditLog, Job, User
from server_app.schemas import AuditEntryOut, JobOut, UserCreate, UserOut, UserUpdate
from server_app.stats import system_stats

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/users")
def list_users(_admin: AdminUser, db: Annotated[Session, Depends(get_db)]) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.created_at)).scalars().all()
    return [UserOut.from_model(u) for u in users]


@router.post("/users", status_code=201)
def create_user(
    request: Request,
    body: UserCreate,
    admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    exists = db.execute(
        select(User).where(User.username == body.username)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="Benutzername bereits vergeben")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        audit.USER_CREATED,
        user=admin,
        detail=f"{body.username} (role={body.role})",
        ip=_ip(request),
    )
    return UserOut.from_model(user)


@router.patch("/users/{user_id}")
def update_user(
    request: Request,
    user_id: str,
    body: UserUpdate,
    admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if user.id == admin.id and (body.is_active is False or body.role == "user"):
        # self-lockout guard: the last admin can't demote/deactivate themself
        raise HTTPException(
            status_code=400, detail="Eigenes Admin-Konto kann nicht herabgestuft werden"
        )
    changes: list[str] = []
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        changes.append("password")
    if body.role is not None:
        user.role = body.role
        changes.append(f"role={body.role}")
    if body.is_active is not None:
        user.is_active = body.is_active
        changes.append(f"is_active={body.is_active}")
        if not body.is_active:
            # deactivation kills every session: refresh tokens die instantly,
            # access tokens die at the live is_active check on next request
            from server_app.auth import refresh_store

            refresh_store.revoke_all_for_user(db, user.id)
    if "daily_minutes_limit" in body.model_fields_set:
        user.daily_minutes_limit = body.daily_minutes_limit
        changes.append(f"daily_minutes_limit={body.daily_minutes_limit}")
    if "monthly_minutes_limit" in body.model_fields_set:
        user.monthly_minutes_limit = body.monthly_minutes_limit
        changes.append(f"monthly_minutes_limit={body.monthly_minutes_limit}")
    audit.record(
        db,
        audit.USER_UPDATED,
        user=admin,
        detail=f"{user.username}: {', '.join(changes) or 'keine Änderung'}",
        ip=_ip(request),
    )
    return UserOut.from_model(user)


@router.get("/audit")
def list_audit(
    _admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    username: str | None = None,
) -> list[AuditEntryOut]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if action:
        query = query.where(AuditLog.action == action)
    if username:
        query = query.where(AuditLog.username == username)
    rows = db.execute(query.limit(min(limit, 500)).offset(max(offset, 0))).scalars().all()
    return [
        AuditEntryOut(
            id=r.id,
            created_at=r.created_at,
            username=r.username,
            action=r.action,
            detail=r.detail,
            ip=r.ip,
        )
        for r in rows
    ]


@router.get("/audit/export")
def export_audit(_admin: AdminUser, db: Annotated[Session, Depends(get_db)]) -> Response:
    rows = db.execute(select(AuditLog).order_by(AuditLog.created_at)).scalars().all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["created_at", "username", "action", "detail", "ip"])
    for r in rows:
        writer.writerow([r.created_at.isoformat(), r.username, r.action, r.detail, r.ip or ""])
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),  # BOM: Excel opens it correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


@router.get("/stats")
def get_stats(
    request: Request, _admin: AdminUser, db: Annotated[Session, Depends(get_db)]
) -> dict[str, object]:
    settings: ServerSettings = request.app.state.settings
    return system_stats(db, settings)


@router.get("/jobs")
def list_all_jobs(_admin: AdminUser, db: Annotated[Session, Depends(get_db)]) -> list[JobOut]:
    rows = db.execute(
        select(Job, User.username)
        .join(User, Job.user_id == User.id)
        .order_by(Job.created_at.desc())
    ).all()
    out: list[JobOut] = []
    for job, username in rows:
        item = JobOut.from_model(job)
        item.username = username
        out.append(item)
    return out
