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
    daily_minutes_limit: float | None = None
    monthly_minutes_limit: float | None = None

    @classmethod
    def from_model(cls, user: User) -> UserOut:
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            daily_minutes_limit=user.daily_minutes_limit,
            monthly_minutes_limit=user.monthly_minutes_limit,
        )


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=150, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=256)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=10, max_length=256)
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None
    daily_minutes_limit: float | None = Field(default=None, ge=0)
    """Explicit null resets to the server default; distinguish "not sent"
    via ``model_fields_set``."""
    monthly_minutes_limit: float | None = Field(default=None, ge=0)


class QuotaOut(BaseModel):
    daily_limit_minutes: float | None
    monthly_limit_minutes: float | None
    used_today_minutes: float
    used_month_minutes: float


class AuditEntryOut(BaseModel):
    id: str
    created_at: datetime
    username: str
    action: str
    detail: str
    ip: str | None


class VocabularyEntryOut(BaseModel):
    id: str
    term: str
    variants: str
    created_at: datetime


class VocabularyEntryCreate(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    variants: str = Field(default="", max_length=500)


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
    eta_seconds: int | None = None
    """Rough wait estimate for queued jobs — rendered as text in the UI's
    live region (never a visual-only progress bar)."""
    text_preview: str | None = None
    username: str | None = None
    """Owner name — only populated in admin listings."""

    @classmethod
    def from_model(
        cls,
        job: Job,
        queue_position: int | None = None,
        eta_seconds: int | None = None,
    ) -> JobOut:
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
            eta_seconds=eta_seconds,
        )
