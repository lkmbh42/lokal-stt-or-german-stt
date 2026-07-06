"""Server configuration — 12-factor: everything comes from environment
variables (prefix ``STT_``), suitable for docker-compose ``env_file``.

Secrets note: ``STT_SECRET_KEY`` has no default on purpose — the app refuses
to start without it rather than shipping a well-known key.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from engine.config import EngineConfig
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STT_", env_nested_delimiter="__")

    database_url: str = "postgresql+psycopg://stt:stt@postgres:5432/stt"
    redis_url: str = "redis://redis:6379/0"

    secret_key: str
    """JWT signing key. Generate with ``openssl rand -hex 32``. Required."""

    access_token_minutes: int = Field(default=15, ge=1)
    refresh_token_days: int = Field(default=7, ge=1)

    data_dir: Path = Path("/data")
    max_upload_mb: int = Field(default=500, ge=1)

    default_daily_minutes: float = Field(default=0, ge=0)
    """Server-wide daily quota in audio minutes (0 = unlimited). Per-user
    overrides live on the user row and win over this default."""

    default_monthly_minutes: float = Field(default=0, ge=0)

    max_concurrent_jobs: int = Field(default=1, ge=1)
    """GPU slots — must match worker concurrency and available VRAM
    (large-v3 float16 ≈ 4.7 GB per slot; int8 ≈ 3 GB)."""

    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None
    """If set and the users table is empty, this admin is created at startup."""

    engine: EngineConfig = Field(default_factory=EngineConfig)

    def user_dir(self, user_id: str) -> Path:
        """Per-user storage root — isolation boundary on disk."""
        return self.data_dir / "users" / user_id

    def uploads_dir(self, user_id: str) -> Path:
        return self.user_dir(user_id) / "uploads"

    def transcripts_dir(self, user_id: str) -> Path:
        return self.user_dir(user_id) / "transcripts"


@lru_cache(maxsize=1)
def get_settings() -> ServerSettings:
    return ServerSettings()  # type: ignore[call-arg]  # secret_key from env
