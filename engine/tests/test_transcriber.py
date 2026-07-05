"""Unit tests for the Transcriber with a fake faster-whisper backend.

These verify the engine's contract (forced language, VAD wiring, prompt and
hotword pass-through, hot-swap, lazy loading) without any model weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from engine.config import EngineConfig, TranscribeOptions
from engine.transcriber import Transcriber


@dataclass
class FakeWord:
    start: float
    end: float
    word: str
    probability: float


@dataclass
class FakeSegment:
    start: float
    end: float
    text: str
    words: list[FakeWord] | None


@dataclass
class FakeInfo:
    language: str = "de"
    language_probability: float = 0.99
    duration: float = 6.0
    duration_after_vad: float = 5.0


@dataclass
class FakeWhisperModel:
    """Records constructor and transcribe() kwargs for assertions."""

    init_args: tuple[Any, ...]
    init_kwargs: dict[str, Any]
    transcribe_calls: list[dict[str, Any]] = field(default_factory=list)

    def transcribe(self, audio: Any, **kwargs: Any):
        self.transcribe_calls.append({"audio": audio, **kwargs})
        segments = iter(
            [
                FakeSegment(
                    start=0.0,
                    end=2.0,
                    text=" Guten Tag , Frau Müller . ",
                    words=[FakeWord(0.0, 0.5, " Guten", 0.99), FakeWord(0.5, 2.0, " Tag", 0.98)],
                )
            ]
        )
        return segments, FakeInfo()


class Recorder:
    def __init__(self) -> None:
        self.instances: list[FakeWhisperModel] = []

    def __call__(self, *args: Any, **kwargs: Any) -> FakeWhisperModel:
        model = FakeWhisperModel(args, kwargs)
        self.instances.append(model)
        return model


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    import faster_whisper
    import numpy as np

    recorder = Recorder()
    monkeypatch.setattr(faster_whisper, "WhisperModel", recorder)
    # keep device resolution and decoding deterministic on any test host
    import engine.transcriber as transcriber_mod

    monkeypatch.setattr(transcriber_mod, "resolve_device", lambda d, c: ("cpu", "int8"))
    monkeypatch.setattr(
        transcriber_mod, "decode_audio", lambda p: np.zeros(16_000, dtype=np.float32)
    )
    return recorder


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    path = tmp_path / "input.wav"
    path.write_bytes(b"RIFF0000WAVE")
    return path


class TestTranscribe:
    def test_language_forced_to_german_by_default(self, fake_backend: Recorder, wav: Path) -> None:
        Transcriber(EngineConfig()).transcribe(wav)
        call = fake_backend.instances[0].transcribe_calls[0]
        assert call["language"] == "de"
        assert call["task"] == "transcribe"

    def test_vad_enabled_with_config_parameters(self, fake_backend: Recorder, wav: Path) -> None:
        config = EngineConfig()
        config.vad.threshold = 0.7
        Transcriber(config).transcribe(wav)
        call = fake_backend.instances[0].transcribe_calls[0]
        assert call["vad_filter"] is True
        assert call["vad_parameters"]["threshold"] == 0.7

    def test_vad_can_be_disabled(self, fake_backend: Recorder, wav: Path) -> None:
        config = EngineConfig()
        config.vad.enabled = False
        Transcriber(config).transcribe(wav)
        call = fake_backend.instances[0].transcribe_calls[0]
        assert call["vad_filter"] is False
        assert call["vad_parameters"] is None

    def test_prompt_and_hotwords_passed_through(self, fake_backend: Recorder, wav: Path) -> None:
        options = TranscribeOptions(
            initial_prompt="Anthropic, Kubernetes", hotwords="Müller GmbH", beam_size=3
        )
        Transcriber(EngineConfig()).transcribe(wav, options)
        call = fake_backend.instances[0].transcribe_calls[0]
        assert call["initial_prompt"] == "Anthropic, Kubernetes"
        assert call["hotwords"] == "Müller GmbH"
        assert call["beam_size"] == 3
        assert call["word_timestamps"] is True

    def test_result_mapping_and_postprocessing(self, fake_backend: Recorder, wav: Path) -> None:
        result = Transcriber(EngineConfig()).transcribe(wav)
        # raw " Guten Tag , Frau Müller . " normalized by the German pipeline
        assert result.segments[0].text == "Guten Tag, Frau Müller."
        assert result.segments[0].words[0].text == "Guten"
        assert result.info.language == "de"
        assert result.info.device == "cpu"
        assert result.info.duration == 6.0
        assert result.info.duration_after_vad == 5.0

    def test_missing_file_raises_before_model_load(self, fake_backend: Recorder) -> None:
        with pytest.raises(FileNotFoundError):
            Transcriber(EngineConfig()).transcribe("does-not-exist.wav")
        assert fake_backend.instances == []


class TestModelLifecycle:
    def test_lazy_loading_and_reuse(self, fake_backend: Recorder, wav: Path) -> None:
        transcriber = Transcriber(EngineConfig())
        assert not transcriber.is_loaded
        transcriber.transcribe(wav)
        transcriber.transcribe(wav)
        assert len(fake_backend.instances) == 1  # one model, two jobs

    def test_swap_model_reloads_with_new_path(self, fake_backend: Recorder, wav: Path) -> None:
        transcriber = Transcriber(EngineConfig(model="large-v3"))
        transcriber.transcribe(wav)
        transcriber.swap_model("./models/whisper-german-ct2")
        assert not transcriber.is_loaded
        transcriber.transcribe(wav)
        assert len(fake_backend.instances) == 2
        assert fake_backend.instances[1].init_args[0] == "./models/whisper-german-ct2"

    def test_offline_settings_reach_backend(self, fake_backend: Recorder, wav: Path) -> None:
        config = EngineConfig(local_files_only=True, download_root=Path("./models"))
        Transcriber(config).transcribe(wav)
        kwargs = fake_backend.instances[0].init_kwargs
        assert kwargs["local_files_only"] is True
        assert kwargs["download_root"] == "models"
