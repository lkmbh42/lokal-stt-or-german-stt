"""Admin endpoints — user management and cross-user job overview.

Every route requires the ``admin`` role (403 otherwise).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from server_app.auth.deps import AdminUser, get_db
from server_app.auth.passwords import hash_password
from server_app.models import Job, User
from server_app.schemas import JobOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(_admin: AdminUser, db: Annotated[Session, Depends(get_db)]) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.created_at)).scalars().all()
    return [UserOut.from_model(u) for u in users]


@router.post("/users", status_code=201)
def create_user(
    body: UserCreate, _admin: AdminUser, db: Annotated[Session, Depends(get_db)]
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
    return UserOut.from_model(user)


@router.patch("/users/{user_id}")
def update_user(
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
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    return UserOut.from_model(user)


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
