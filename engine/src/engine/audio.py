"""Audio decoding to the 16 kHz mono float32 waveform faster-whisper expects.

Primary decoder is PyAV (in-process, bundled FFmpeg libraries — the path used
inside the Linux containers). Some locked-down Windows hosts block PyAV's
native extension DLLs via application-control policy, so a subprocess
fallback to the ``ffmpeg`` CLI keeps the engine functional there. Both paths
are fully local — no network involved.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


def decode_audio(path: str | Path, sampling_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any supported container (wav/mp3/m4a/mp4/flac) to mono float32."""
    try:
        from faster_whisper.audio import decode_audio as fw_decode

        return np.asarray(fw_decode(str(path), sampling_rate=sampling_rate))
    except (ImportError, OSError) as exc:
        logger.warning(
            "PyAV decoding unavailable (%s) — falling back to ffmpeg CLI.", exc
        )
        return _decode_with_ffmpeg(path, sampling_rate)


def _decode_with_ffmpeg(path: str | Path, sampling_rate: int) -> np.ndarray:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "audio decoding unavailable: PyAV failed to load and no ffmpeg "
            "executable was found on PATH"
        )
    proc = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-threads",
            "0",
            "-i",
            str(path),
            "-f",
            "f32le",
            "-ac",
            "1",
            "-ar",
            str(sampling_rate),
            "pipe:1",
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg failed to decode {path}: {stderr[-500:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32)
