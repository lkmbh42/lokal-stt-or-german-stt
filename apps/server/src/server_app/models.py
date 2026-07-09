"""ORM models.

IDs are 32-char UUID hex strings (portable across Postgres and the SQLite
test database). Timestamps are timezone-aware UTC.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server_app.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # "admin" | "user"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    daily_minutes_limit: Mapped[float | None] = mapped_column(Float, default=None)
    """Per-user daily transcription cap in audio minutes.
    None = use the server default; 0 in the server default = unlimited."""
    monthly_minutes_limit: Mapped[float | None] = mapped_column(Float, default=None)

    jobs: Mapped[list[Job]] = relationship(back_populates="user", cascade="all, delete-orphan")
    vocabulary: Mapped[list[VocabularyEntry]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class VocabularyEntry(Base):
    """A user's custom-dictionary entry: a term that is boosted for every job,
    plus optional common mishears that get auto-corrected to it."""

    __tablename__ = "vocabulary_entries"
    __table_args__ = (Index("ix_vocab_user", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    term: Mapped[str] = mapped_column(String(200))
    """Correct written form — always boosted into hotwords."""
    variants: Mapped[str] = mapped_column(String(500), default="")
    """Comma-separated common mishears, each corrected to ``term``."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="vocabulary")

    def variant_list(self) -> list[str]:
        return [v.strip() for v in self.variants.split(",") if v.strip()]


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # every user-facing query filters by owner first — this index is the
        # hot path for both listing and the isolation checks
        Index("ix_jobs_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(16), default="upload")
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration: Mapped[float | None] = mapped_column(Float, default=None)
    estimated_duration: Mapped[float | None] = mapped_column(Float, default=None)
    """Probed at upload (ffprobe) — quota accounting and ETA before the
    real duration is known."""
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    audio_path: Mapped[str | None] = mapped_column(Text, default=None)
    transcript_path: Mapped[str | None] = mapped_column(Text, default=None)

    user: Mapped[User] = relationship(back_populates="jobs")

    CANCELABLE = ("queued", "processing")

    @property
    def billable_duration(self) -> float:
        """Seconds counted against quota: real when known, else the probe."""
        return self.duration if self.duration is not None else (self.estimated_duration or 0.0)


class RefreshToken(Base):
    """Server-side refresh-token registry (denylist by omission).

    A refresh token is only honored while its ``jti`` row exists and is not
    revoked. Rotation revokes the old row; logout revokes explicitly; a
    replayed token therefore fails even though its signature is valid.
    """

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    """Append-only audit trail.

    Nothing in the application updates or deletes rows here — there are no
    such endpoints and no ORM code paths; admins get read + CSV export only.
    ``username`` is denormalized on purpose: entries stay meaningful even if
    the user row is later deleted.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_id: Mapped[str | None] = mapped_column(String(32), default=None, index=True)
    username: Mapped[str] = mapped_column(String(150), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str | None] = mapped_column(String(64), default=None)
