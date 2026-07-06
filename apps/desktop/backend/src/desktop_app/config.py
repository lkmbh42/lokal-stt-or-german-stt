"""Desktop app configuration (config.yaml).

Security invariant: the server binds to the loopback interface only. The
``host`` field is validated, not merely defaulted — a config file cannot
expose the app on ``0.0.0.0``.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path

import yaml
from engine.config import EngineConfig
from engine.types import OutputFormat
from pydantic import BaseModel, Field, field_validator

ALLOWED_UPLOAD_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".flac"}


class LiveConfig(BaseModel):
    """Live microphone transcription tuning."""

    tick_seconds: float = Field(default=3.0, ge=0.5, le=15.0)
    """How often the pending audio window is (re)transcribed for partials."""

    silence_commit_seconds: float = Field(default=0.8, ge=0.2, le=5.0)
    """Trailing silence after the last recognized segment that finalizes it."""

    max_pending_seconds: float = Field(default=30.0, ge=5.0, le=120.0)
    """Force-commit horizon so the rolling window can't grow unbounded."""

    max_session_seconds: float = Field(default=3600.0, ge=60.0)


class AppConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8710, ge=1024, le=65535)
    data_dir: Path = Path("data")
    max_upload_mb: int = Field(default=500, ge=1)
    default_formats: list[OutputFormat] = Field(
        default_factory=lambda: [OutputFormat.TXT]
    )
    frontend_dist: Path | None = None
    """Directory of built frontend assets; defaults to the sibling
    ``frontend/dist`` of this repository layout."""

    engine: EngineConfig = Field(default_factory=EngineConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, v: str) -> str:
        v = v.strip()
        if v == "localhost":
            return "127.0.0.1"
        try:
            addr = ipaddress.ip_address(v)
        except ValueError as exc:
            raise ValueError(f"host must be a loopback address, got {v!r}") from exc
        if not addr.is_loopback:
            raise ValueError(
                f"Variant A binds to loopback only (got {v!r}). "
                "Use Variant B (the team server) for network exposure."
            )
        return v

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def transcripts_dir(self) -> Path:
        return self.data_dir / "transcripts"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.sqlite3"

    def ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)


def load_app_config(path: str | Path | None) -> AppConfig:
    if path is None:
        return AppConfig()
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} must contain a YAML mapping")
    return AppConfig.model_validate(data)
