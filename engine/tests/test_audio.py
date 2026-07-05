from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

import engine.audio as audio_mod
from engine.audio import decode_audio

FIXTURES = Path(__file__).parent / "fixtures"

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg CLI not on PATH"
)


def _tone_fixture() -> Path:
    path = FIXTURES / "tone.wav"
    if not path.is_file():
        pytest.skip("run engine/scripts/make_fixtures.py first")
    return path


def test_decode_returns_16khz_mono_float32() -> None:
    waveform = decode_audio(_tone_fixture())
    assert waveform.dtype == np.float32
    assert waveform.ndim == 1
    # tone.wav is 2 s at 16 kHz
    assert abs(len(waveform) - 32_000) < 1_000
    assert float(np.abs(waveform).max()) > 0.1


@requires_ffmpeg
def test_ffmpeg_fallback_matches_expectations(monkeypatch: pytest.MonkeyPatch) -> None:
    waveform = audio_mod._decode_with_ffmpeg(_tone_fixture(), 16_000)
    assert waveform.dtype == np.float32
    assert abs(len(waveform) - 32_000) < 1_000


def test_error_when_no_decoder_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio_mod.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="no ffmpeg"):
        audio_mod._decode_with_ffmpeg("x.wav", 16_000)


@requires_ffmpeg
def test_ffmpeg_failure_reports_stderr(tmp_path: Path) -> None:
    bad = tmp_path / "broken.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        audio_mod._decode_with_ffmpeg(bad, 16_000)
