"""Engine configuration.

Two layers:

* :class:`EngineConfig` — process-lifetime settings (which model, which
  device, VAD tuning). Loaded once, hot-swappable via
  :meth:`engine.transcriber.Transcriber.swap_model`.
* :class:`TranscribeOptions` — per-job settings (prompt/hotwords, beam size,
  redaction rules). Passed with every ``transcribe()`` call.

Air-gap note: with ``local_files_only: true`` the engine refuses any network
access and fails loudly if the model directory is missing — this is the
required production setting for offline deployments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

Device = Literal["auto", "cuda", "cpu"]
ComputeType = Literal["auto", "float16", "int8_float16", "int8", "float32"]


class VadConfig(BaseModel):
    """Silero VAD pre-segmentation (integrated in faster-whisper).

    Cuts hallucinations on silence and improves throughput by skipping
    non-speech before ASR ever sees it.
    """

    enabled: bool = True
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_silence_duration_ms: int = Field(default=500, ge=0)
    speech_pad_ms: int = Field(default=400, ge=0)

    def to_vad_parameters(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "min_silence_duration_ms": self.min_silence_duration_ms,
            "speech_pad_ms": self.speech_pad_ms,
        }


class RedactionRule(BaseModel):
    """Regex-based PII redaction applied after transcription."""

    pattern: str
    replacement: str = "[REDIGIERT]"


class CorrectionRule(BaseModel):
    """Whole-word correction from a custom vocabulary: replace ``wrong`` with
    ``right`` (case-insensitive, sentence-initial capitalization preserved).
    Used to fix systematic mishears, e.g. ``Kabel`` → ``Cappel``."""

    wrong: str
    right: str


class EngineConfig(BaseModel):
    model: str = "large-v3"
    """Model name (e.g. ``large-v3``, ``large-v3-turbo``, ``tiny``) or a local
    path to a CTranslate2 model directory. Local paths are how German
    fine-tuned checkpoints are plugged in — no code change required."""

    device: Device = "auto"
    compute_type: ComputeType = "auto"
    download_root: Path | None = None
    """Where model weights live / get staged. ``None`` = faster-whisper default."""

    local_files_only: bool = False
    """Hard-offline mode: never attempt a download; missing weights are an error."""

    cpu_threads: int = Field(default=0, ge=0)
    num_workers: int = Field(default=1, ge=1)
    vad: VadConfig = Field(default_factory=VadConfig)

    @field_validator("model")
    @classmethod
    def _model_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model must be a model name or a local path")
        return v.strip()


class TranscribeOptions(BaseModel):
    language: str = "de"
    """Forced transcription language. Auto-detection is deliberately not
    supported: German accuracy is the optimization target and detection adds
    latency and misdetection drift."""

    task: Literal["transcribe"] = "transcribe"
    beam_size: int = Field(default=5, ge=1)
    initial_prompt: str | None = None
    """Domain vocabulary priming (names, product terms, acronyms)."""

    hotwords: str | None = None
    """Hotword boost string, e.g. ``"Kubernetes Anthropic GmbH"``."""

    word_timestamps: bool = True
    condition_on_previous_text: bool = True
    temperature: float = Field(default=0.0, ge=0.0)
    dictation_mode: bool = False
    """Spoken-punctuation mode: convert dictated command words ("Komma",
    "Punkt", "Klammer auf", …) into the actual marks. Opt-in — it reinterprets
    common words, so only enable it when the speaker is dictating punctuation."""
    normalize_german: bool = True
    normalizer_decimal_comma: bool = False
    normalizer_thousands_grouping: bool = False
    corrections: list[CorrectionRule] = Field(default_factory=list)
    """Custom-vocabulary corrections applied after transcription."""
    redaction_rules: list[RedactionRule] = Field(default_factory=list)

    @field_validator("language")
    @classmethod
    def _language_required(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError(
                "language must be set explicitly (auto-detection is disabled by design)"
            )
        return v


def load_config(path: str | Path) -> EngineConfig:
    """Load an :class:`EngineConfig` from a YAML file."""
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} must contain a YAML mapping")
    return EngineConfig.model_validate(data)
