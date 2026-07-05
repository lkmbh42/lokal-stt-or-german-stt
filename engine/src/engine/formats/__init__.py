"""Transcript exporters.

Every exporter renders a :class:`~engine.types.TranscriptResult` to bytes so
callers (CLI, HTTP download endpoints) can stream or write them uniformly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from engine.formats.docxfmt import to_docx
from engine.formats.jsonfmt import to_json
from engine.formats.subtitles import to_srt, to_vtt
from engine.formats.text import to_txt
from engine.types import OutputFormat, TranscriptResult

_RENDERERS: dict[OutputFormat, Callable[[TranscriptResult], bytes]] = {
    OutputFormat.TXT: lambda r: to_txt(r).encode("utf-8"),
    OutputFormat.SRT: lambda r: to_srt(r).encode("utf-8"),
    OutputFormat.VTT: lambda r: to_vtt(r).encode("utf-8"),
    OutputFormat.JSON: lambda r: to_json(r).encode("utf-8"),
    OutputFormat.DOCX: to_docx,
}


def render(result: TranscriptResult, fmt: OutputFormat) -> bytes:
    return _RENDERERS[fmt](result)


def write_outputs(
    result: TranscriptResult,
    formats: list[OutputFormat],
    out_dir: str | Path,
    stem: str,
) -> list[Path]:
    """Write one file per requested format; returns the written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        path = out / f"{stem}.{fmt.value}"
        path.write_bytes(render(result, fmt))
        written.append(path)
    return written


__all__ = ["render", "write_outputs", "to_txt", "to_srt", "to_vtt", "to_json", "to_docx"]
