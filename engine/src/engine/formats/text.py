"""Plain-text exporter."""

from __future__ import annotations

from engine.types import TranscriptResult


def to_txt(result: TranscriptResult) -> str:
    """One segment per line; speaker labels prefixed when diarization ran."""
    lines: list[str] = []
    for seg in result.segments:
        text = seg.text.strip()
        if not text:
            continue
        lines.append(f"{seg.speaker}: {text}" if seg.speaker else text)
    return "\n".join(lines) + ("\n" if lines else "")
