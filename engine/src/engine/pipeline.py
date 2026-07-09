"""Post-ASR processing pipeline.

Stages implement :class:`Stage` and run in order over the raw
:class:`~engine.types.TranscriptResult`. This is the plug point for the
optional speaker-diarization module planned for a later phase: a diarizer is
just another stage that fills ``Segment.speaker`` (it receives the audio path
via the stage context, so it can re-read the waveform).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from engine.config import TranscribeOptions
from engine.postprocess import (
    DictationCommands,
    GermanNormalizer,
    Redactor,
    VocabularyCorrections,
)
from engine.types import TranscriptResult


@dataclass(frozen=True)
class StageContext:
    """Everything a stage may need beyond the transcript itself."""

    options: TranscribeOptions
    audio_path: Path | None = None
    """Original audio location; ``None`` when transcribing an in-memory array."""


@runtime_checkable
class Stage(Protocol):
    def process(self, result: TranscriptResult) -> TranscriptResult: ...


@dataclass
class Pipeline:
    stages: list[Stage] = field(default_factory=list)

    def run(self, result: TranscriptResult) -> TranscriptResult:
        for stage in self.stages:
            result = stage.process(result)
        return result


def build_default_pipeline(options: TranscribeOptions) -> Pipeline:
    """Assemble the standard post-processing chain for a job.

    Order matters: dictation first (turns spoken commands into marks), then
    normalization (cleans spacing and collapses any leftover duplicate
    punctuation), then vocabulary corrections (fix mishears on clean text),
    redaction last (nothing after it may reintroduce raw text).
    """
    stages: list[Stage] = []
    if options.dictation_mode:
        stages.append(DictationCommands())
    if options.normalize_german:
        stages.append(
            GermanNormalizer(
                decimal_comma=options.normalizer_decimal_comma,
                thousands_grouping=options.normalizer_thousands_grouping,
            )
        )
    if options.corrections:
        stages.append(VocabularyCorrections(options.corrections))
    if options.redaction_rules:
        stages.append(Redactor(options.redaction_rules))
    return Pipeline(stages)
