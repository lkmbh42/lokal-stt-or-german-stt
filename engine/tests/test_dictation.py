from __future__ import annotations

import pytest

from engine.config import TranscribeOptions
from engine.pipeline import build_default_pipeline
from engine.postprocess.dictation import DictationCommands
from engine.postprocess.german import GermanNormalizer
from engine.types import Segment, TranscriptInfo, TranscriptResult


@pytest.fixture
def dictation() -> DictationCommands:
    return DictationCommands()


class TestBasicMarks:
    def test_comma_and_period(self, dictation: DictationCommands) -> None:
        assert dictation.apply("Ach Komma du meine Güte Punkt") == "Ach, du meine Güte."

    def test_question_and_exclamation(self, dictation: DictationCommands) -> None:
        assert dictation.apply("wie geht es Fragezeichen") == "Wie geht es?"
        assert dictation.apply("pass auf Ausrufezeichen") == "Pass auf!"

    def test_parentheses_and_colon(self, dictation: DictationCommands) -> None:
        assert (
            dictation.apply("Klammer auf oder besser Doppelpunkt Himmel Ausrufezeichen Klammer zu")
            == "(oder besser: Himmel!)"
        )

    def test_semicolon_and_quotes(self, dictation: DictationCommands) -> None:
        assert dictation.apply("eins Semikolon zwei") == "Eins; zwei"
        assert (
            dictation.apply("er sagte Anführungszeichen auf hallo Anführungszeichen zu")
            == "Er sagte „hallo“"
        )

    def test_newline_command(self, dictation: DictationCommands) -> None:
        assert dictation.apply("erste Zeile neue Zeile zweite Zeile") == (
            "Erste Zeile\nZweite Zeile"
        )


class TestContentWordDisambiguation:
    """The exact-singular-form rule: only 'Komma' is a command, not 'Kommas'."""

    def test_plural_content_words_survive(self, dictation: DictationCommands) -> None:
        assert (
            dictation.apply("ein Text mit Doppelpunkt Kommas Semikolon Punkten")
            == "Ein Text mit: Kommas; Punkten"
        )

    def test_inflected_forms_are_not_commands(self, dictation: DictationCommands) -> None:
        # "Klammern" (plural) is a word; only "Klammer auf/zu" is a command
        assert dictation.apply("viele Klammern") == "Viele Klammern"


class TestSplitCompounds:
    """The ASR may split long command words; glue them back before matching."""

    def test_ausrufezeichen_split_by_asr(self, dictation: DictationCommands) -> None:
        # Whisper transcribed "Ausrufezeichen" as two words "Ausrufe Zeichen"
        assert dictation.apply("Himmel Ausrufe Zeichen") == "Himmel!"

    def test_various_split_compounds(self, dictation: DictationCommands) -> None:
        assert dictation.apply("was Frage Zeichen") == "Was?"
        assert dictation.apply("eins Doppel Punkt zwei") == "Eins: zwei"


class TestWhisperPunctuationAroundCommands:
    """Real-world: natural pauses make Whisper attach its own punctuation to
    the command words ("… ich, Gedankenstrich, nachdem …"). That must not stop
    the command from matching, and Whisper's stray marks are dropped."""

    def test_dashes_wrapped_in_whisper_commas(self, dictation: DictationCommands) -> None:
        spoken = "Als ich, Gedankenstrich, nachdem ich gelernt hatte, Gedankenstrich, am Abend"
        assert dictation.apply(spoken) == "Als ich – nachdem ich gelernt hatte – am Abend"

    def test_parens_and_trailing_comma(self, dictation: DictationCommands) -> None:
        spoken = "Heimweg Klammer auf, es war dunkel, Klammer zu, Komma, bemerkte ich"
        assert dictation.apply(spoken) == "Heimweg (es war dunkel), bemerkte ich"

    def test_command_with_trailing_period(self, dictation: DictationCommands) -> None:
        # "neue Zeile." — Whisper put a period on the second word
        assert dictation.apply("erste Zeile Neue Zeile. zweite") == "Erste Zeile\nZweite"


class TestCapitalization:
    def test_first_word_and_after_period(self, dictation: DictationCommands) -> None:
        assert dictation.apply("hallo Punkt wie geht es dir Fragezeichen") == (
            "Hallo. Wie geht es dir?"
        )

    def test_no_capitalization_after_comma(self, dictation: DictationCommands) -> None:
        assert dictation.apply("erstens Komma zweitens") == "Erstens, zweitens"


class TestPipelineIntegration:
    def _result(self, text: str) -> TranscriptResult:
        return TranscriptResult(
            segments=[Segment(id=0, start=0.0, end=1.0, text=text)],
            info=TranscriptInfo(
                language="de", duration=1.0, model="t", device="cpu", compute_type="int8"
            ),
        )

    def test_only_runs_when_enabled(self) -> None:
        options = TranscribeOptions(dictation_mode=False)
        out = build_default_pipeline(options).run(self._result("Ach Komma du"))
        assert out.segments[0].text == "Ach Komma du"

    def test_runs_before_normalizer(self) -> None:
        options = TranscribeOptions(dictation_mode=True)
        stages = build_default_pipeline(options).stages
        assert isinstance(stages[0], DictationCommands)
        assert isinstance(stages[1], GermanNormalizer)

    def test_end_to_end_mixed_sentence(self) -> None:
        # a big chunk of the user's stress sentence, dictated
        spoken = (
            "Ach Komma du meine Güte Auslassungspunkte "
            "Klammer auf oder besser Doppelpunkt Himmel Ausrufezeichen Klammer zu "
            "ist das etwa wirklich "
            "ein Text mit Doppelpunkt Kommas Semikolon Punkten Semikolon Klammern"
        )
        options = TranscribeOptions(dictation_mode=True)
        out = build_default_pipeline(options).run(self._result(spoken))
        assert out.segments[0].text == (
            "Ach, du meine Güte… (oder besser: Himmel!) ist das etwa wirklich "
            "ein Text mit: Kommas; Punkten; Klammern"
        )

    def test_duplicate_punctuation_from_whisper_is_collapsed(self) -> None:
        # Whisper often keeps its own comma AND the spoken word: "Ach, Komma du"
        options = TranscribeOptions(dictation_mode=True)
        out = build_default_pipeline(options).run(self._result("Ach, Komma du Punkt"))
        assert out.segments[0].text == "Ach, du."
