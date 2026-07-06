"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from server_app.models import Job, User


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(cls, user: User) -> UserOut:
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=150, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=256)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=10, max_length=256)
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None


class JobOut(BaseModel):
    id: str
    source: str
    filename: str
    status: str
    progress: float
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    duration: float | None
    queue_position: int | None = None
    text_preview: str | None = None
    username: str | None = None
    """Owner name — only populated in admin listings."""

    @classmethod
    def from_model(cls, job: Job, queue_position: int | None = None) -> JobOut:
        return cls(
            id=job.id,
            source=job.source,
            filename=job.original_filename,
            status=job.status,
            progress=job.progress,
            error=job.error,
            created_at=job.created_at,
            finished_at=job.finished_at,
            duration=job.duration,
            queue_position=queue_position,
        )
