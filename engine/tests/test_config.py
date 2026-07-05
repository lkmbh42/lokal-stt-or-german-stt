from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.config import EngineConfig, TranscribeOptions, VadConfig, load_config


class TestEngineConfig:
    def test_defaults(self) -> None:
        cfg = EngineConfig()
        assert cfg.model == "large-v3"
        assert cfg.device == "auto"
        assert cfg.compute_type == "auto"
        assert cfg.local_files_only is False
        assert cfg.vad.enabled is True

    def test_empty_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EngineConfig(model="   ")

    def test_local_path_model(self, tmp_path: Path) -> None:
        cfg = EngineConfig(model=str(tmp_path / "whisper-german-ct2"))
        assert "whisper-german-ct2" in cfg.model

    def test_invalid_device_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EngineConfig(device="tpu")  # type: ignore[arg-type]


class TestVadConfig:
    def test_to_vad_parameters(self) -> None:
        vad = VadConfig(threshold=0.6, min_silence_duration_ms=300, speech_pad_ms=100)
        assert vad.to_vad_parameters() == {
            "threshold": 0.6,
            "min_silence_duration_ms": 300,
            "speech_pad_ms": 100,
        }

    def test_threshold_bounds(self) -> None:
        with pytest.raises(ValidationError):
            VadConfig(threshold=1.5)


class TestTranscribeOptions:
    def test_language_defaults_to_german(self) -> None:
        assert TranscribeOptions().language == "de"

    def test_empty_language_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TranscribeOptions(language="  ")

    def test_language_normalized(self) -> None:
        assert TranscribeOptions(language=" DE ").language == "de"

    def test_redaction_rules_coerced(self) -> None:
        opts = TranscribeOptions(redaction_rules=[{"pattern": r"\d+"}])  # type: ignore[list-item]
        assert opts.redaction_rules[0].replacement == "[REDIGIERT]"


class TestLoadConfig:
    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(
            "model: small\ndevice: cpu\nlocal_files_only: true\nvad:\n  threshold: 0.7\n",
            encoding="utf-8",
        )
        cfg = load_config(path)
        assert cfg.model == "small"
        assert cfg.device == "cpu"
        assert cfg.local_files_only is True
        assert cfg.vad.threshold == 0.7

    def test_empty_file_gives_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        assert load_config(path) == EngineConfig()

    def test_non_mapping_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("- just\n- a list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapping"):
            load_config(path)
