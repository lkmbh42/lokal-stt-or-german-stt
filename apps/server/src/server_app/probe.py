"""Cheap audio-duration probe (ffprobe) used at upload time.

Quotas are counted in audio minutes, which are only truly known after
transcription — the probe closes that gap so limits are enforced *before*
the GPU does any work, and rejects non-audio uploads early as a bonus.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ProbeError(Exception):
    pass


def probe_duration_seconds(path: str | Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ProbeError("ffprobe nicht gefunden (ffmpeg-Installation unvollständig)")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise ProbeError("Datei ist keine lesbare Audiodatei")
    try:
        duration = float(proc.stdout.strip())
    except ValueError as exc:
        raise ProbeError("Audiodauer konnte nicht ermittelt werden") from exc
    if duration <= 0:
        raise ProbeError("Audiodatei ist leer")
    return duration
