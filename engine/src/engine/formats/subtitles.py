"""SRT and WebVTT exporters."""

from __future__ import annotations

from engine.formats.timecode import srt_time, vtt_time
from engine.types import Segment, TranscriptResult


def _cue_text(seg: Segment) -> str:
    text = seg.text.strip()
    return f"{seg.speaker}: {text}" if seg.speaker else text


def to_srt(result: TranscriptResult) -> str:
    blocks: list[str] = []
    index = 1
    for seg in result.segments:
        text = _cue_text(seg)
        if not text:
            continue
        blocks.append(f"{index}\n{srt_time(seg.start)} --> {srt_time(seg.end)}\n{text}")
        index += 1
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(result: TranscriptResult) -> str:
    lines = ["WEBVTT", ""]
    for seg in result.segments:
        text = _cue_text(seg)
        if not text:
            continue
        lines.append(f"{vtt_time(seg.start)} --> {vtt_time(seg.end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
