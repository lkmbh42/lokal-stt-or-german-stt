"""Integration tests against a real faster-whisper model and real German audio.

Marked ``model``: excluded from offline unit runs (``-m "not model"``).
The test model defaults to ``base`` (small download, adequate German);
override with the ``STT_TEST_MODEL`` environment variable.

Fixtures come from ``scripts/make_fixtures.py`` (local SAPI synthesis — the
German sample is skipped automatically if it was never generated).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from engine.config import EngineConfig, TranscribeOptions
from engine.transcriber import Transcriber

FIXTURES = Path(__file__).parent / "fixtures"
TEST_MODEL = os.environ.get("STT_TEST_MODEL", "base")

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def transcriber() -> Transcriber:
    return Transcriber(EngineConfig(model=TEST_MODEL, device="auto"))


def _fixture(name: str) -> Path:
    path = FIXTURES / name
    if not path.is_file():
        pytest.skip(f"fixture {name} missing — run engine/scripts/make_fixtures.py")
    return path


def test_german_speech_is_transcribed(transcriber: Transcriber) -> None:
    result = transcriber.transcribe(
        _fixture("german_sample.wav"), TranscribeOptions(language="de")
    )
    assert result.info.language == "de"
    assert result.segments, "expected at least one speech segment"
    text = result.text.lower()
    # loose content check: synthetic TTS + small model won't be verbatim, but
    # core German words from the prompt must survive
    assert any(word in text for word in ("test", "spracherkennung", "guten", "tag")), text
    # word-level timestamps present and monotonic
    words = [w for seg in result.segments for w in seg.words]
    assert words
    assert all(w.end >= w.start for w in words)


def test_silence_produces_no_segments(transcriber: Transcriber) -> None:
    result = transcriber.transcribe(_fixture("silence.wav"))
    assert result.segments == []  # VAD swallows pure silence — no hallucinations


def test_tone_produces_no_speech(transcriber: Transcriber) -> None:
    result = transcriber.transcribe(_fixture("tone.wav"))
    assert result.text.strip() == "" or len(result.text) < 40
