from __future__ import annotations

from dataclasses import dataclass

from engine.config import TranscribeOptions
from engine.pipeline import Pipeline, Stage, build_default_pipeline
from engine.postprocess import GermanNormalizer, Redactor
from engine.types import Segment, TranscriptResult


class TestBuildDefaultPipeline:
    def test_normalizer_then_redactor(self) -> None:
        options = TranscribeOptions(redaction_rules=[{"pattern": r"\d+"}])  # type: ignore[list-item]
        pipeline = build_default_pipeline(options)
        assert [type(s) for s in pipeline.stages] == [GermanNormalizer, Redactor]

    def test_normalization_can_be_disabled(self) -> None:
        pipeline = build_default_pipeline(TranscribeOptions(normalize_german=False))
        assert pipeline.stages == []

    def test_redaction_sees_normalized_text(self, sample_result: TranscriptResult) -> None:
        # " 5 ." is normalized to "5." first, so a rule targeting "5." matches
        sample_result.segments[1].text = "Die Prüfung findet am 5 . Juli statt."
        options = TranscribeOptions(
            redaction_rules=[{"pattern": r"5\. Juli", "replacement": "[DATUM]"}]  # type: ignore[list-item]
        )
        out = build_default_pipeline(options).run(sample_result)
        assert out.segments[1].text == "Die Prüfung findet am [DATUM] statt."


@dataclass
class FakeDiarizer:
    """Demonstrates the diarization plug point: a stage filling Segment.speaker."""

    label: str = "Sprecher 1"

    def process(self, result: TranscriptResult) -> TranscriptResult:
        segments = [
            Segment(**{**seg.model_dump(), "speaker": self.label}) for seg in result.segments
        ]
        return TranscriptResult(segments=segments, info=result.info)


class TestCustomStage:
    def test_stage_protocol_accepts_custom_stage(self) -> None:
        assert isinstance(FakeDiarizer(), Stage)

    def test_diarizer_stage_populates_speakers(self, sample_result: TranscriptResult) -> None:
        out = Pipeline([FakeDiarizer()]).run(sample_result)
        assert out.has_speakers
        assert all(seg.speaker == "Sprecher 1" for seg in out.segments)
