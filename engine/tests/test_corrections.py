from __future__ import annotations

from engine.config import CorrectionRule, TranscribeOptions
from engine.pipeline import build_default_pipeline
from engine.postprocess.corrections import VocabularyCorrections
from engine.types import Segment, TranscriptInfo, TranscriptResult, Word


def _rules(*pairs: tuple[str, str]) -> list[CorrectionRule]:
    return [CorrectionRule(wrong=w, right=r) for w, r in pairs]


class TestCorrectText:
    def test_simple_replacement(self) -> None:
        c = VocabularyCorrections(_rules(("Kabel", "Cappel")))
        assert c.correct_text("Heimweg nach Kabel") == "Heimweg nach Cappel"

    def test_case_insensitive_match(self) -> None:
        c = VocabularyCorrections(_rules(("marbon", "Marburg")))
        assert c.correct_text("in Marbon gelernt") == "in Marburg gelernt"

    def test_preserves_leading_capitalization(self) -> None:
        c = VocabularyCorrections(_rules(("kabel", "cappel")))
        assert c.correct_text("Kabel ist ein Ort") == "Cappel ist ein Ort"
        assert c.correct_text("nach kabel") == "nach cappel"

    def test_whole_word_only(self) -> None:
        c = VocabularyCorrections(_rules(("Kabel", "Cappel")))
        # must not touch "Kabelbaum"
        assert c.correct_text("der Kabelbaum") == "der Kabelbaum"

    def test_multiple_rules(self) -> None:
        c = VocabularyCorrections(_rules(("Marbon", "Marburg"), ("Kabel", "Cappel")))
        assert c.correct_text("von Marbon nach Kabel") == "von Marburg nach Cappel"

    def test_multi_word_variant(self) -> None:
        c = VocabularyCorrections(_rules(("New Jork", "New York")))
        assert c.correct_text("aus New Jork") == "aus New York"

    def test_empty_rules_are_skipped(self) -> None:
        c = VocabularyCorrections(_rules(("", "x"), ("  ", "y")))
        assert c.correct_text("nichts ändert sich") == "nichts ändert sich"


class TestProcess:
    def _result(self, text: str, words: list[Word]) -> TranscriptResult:
        return TranscriptResult(
            segments=[Segment(id=0, start=0.0, end=1.0, text=text, words=words)],
            info=TranscriptInfo(
                language="de", duration=1.0, model="t", device="cpu", compute_type="int8"
            ),
        )

    def test_corrects_segment_and_word_text(self) -> None:
        result = self._result(
            "nach Kabel",
            [Word(start=0.0, end=0.5, text="nach"), Word(start=0.5, end=1.0, text="Kabel")],
        )
        out = VocabularyCorrections(_rules(("Kabel", "Cappel"))).process(result)
        assert out.segments[0].text == "nach Cappel"
        assert out.segments[0].words[1].text == "Cappel"

    def test_no_rules_is_identity(self) -> None:
        result = self._result("unverändert", [])
        assert VocabularyCorrections([]).process(result) is result


class TestPipelineIntegration:
    def test_corrections_run_before_redaction(self) -> None:
        from engine.postprocess.redaction import Redactor

        options = TranscribeOptions(
            corrections=_rules(("Kabel", "Cappel")),
            redaction_rules=[{"pattern": r"\d{4}"}],  # type: ignore[list-item]
        )
        stages = build_default_pipeline(options).stages
        assert any(isinstance(s, VocabularyCorrections) for s in stages)
        vocab_idx = next(
            i for i, s in enumerate(stages) if isinstance(s, VocabularyCorrections)
        )
        redact_idx = next(i for i, s in enumerate(stages) if isinstance(s, Redactor))
        assert vocab_idx < redact_idx

    def test_not_added_when_no_corrections(self) -> None:
        stages = build_default_pipeline(TranscribeOptions()).stages
        assert not any(isinstance(s, VocabularyCorrections) for s in stages)
