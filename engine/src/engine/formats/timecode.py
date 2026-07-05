"""Subtitle timecode formatting."""

from __future__ import annotations


def _split(seconds: float) -> tuple[int, int, int, int]:
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    ms = total_ms % 1000
    total_s = total_ms // 1000
    return total_s // 3600, (total_s // 60) % 60, total_s % 60, ms


def srt_time(seconds: float) -> str:
    """``HH:MM:SS,mmm`` (SRT uses a comma)."""
    h, m, s, ms = _split(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def vtt_time(seconds: float) -> str:
    """``HH:MM:SS.mmm`` (WebVTT uses a dot)."""
    h, m, s, ms = _split(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
