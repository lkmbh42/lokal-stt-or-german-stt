"""Result types shared by every consumer of the engine.

These are plain pydantic models so both variants (desktop app, team server)
can serialize them losslessly to JSON / DB rows without touching
faster-whisper internals.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"
    JSON = "json"
    DOCX = "docx"


class Word(BaseModel):
    """A single recognized word with timestamps in seconds."""

    start: float
    end: float
    text: str
    probability: float = 0.0


class Segment(BaseModel):
    """A contiguous speech segment (roughly sentence/phrase sized)."""

    id: int
    start: float
    end: float
    text: str
    words: list[Word] = Field(default_factory=list)
    speaker: str | None = None
    """Speaker label — populated only when a diarization stage runs."""


class TranscriptInfo(BaseModel):
    """Metadata about how a transcript was produced."""

    language: str
    language_probability: float = 1.0
    duration: float
    """Duration of the input audio in seconds."""
    duration_after_vad: float | None = None
    model: str
    device: str
    compute_type: str
    engine_version: str = ""


class TranscriptResult(BaseModel):
    segments: list[Segment]
    info: TranscriptInfo

    @property
    def text(self) -> str:
        """Full transcript as plain text, one segment per line."""
        return "\n".join(seg.text.strip() for seg in self.segments if seg.text.strip())

    @property
    def has_speakers(self) -> bool:
        return any(seg.speaker is not None for seg in self.segments)
