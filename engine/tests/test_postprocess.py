from __future__ import annotations

import pytest

from engine.postprocess.german import GermanNormalizer
from engine.types import TranscriptResult


@pytest.fixture
def normalizer() -> GermanNormalizer:
    return GermanNormalizer()


class TestSpacing:
    def test_space_before_punctuation_removed(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("Guten Tag , Frau Müller .") == "Guten Tag, Frau Müller."

    def test_missing_space_after_sentence_end(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("Hallo.Wie geht es?") == "Hallo. Wie geht es?"

    def test_numbers_untouched_by_spacing_rule(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("Es kostet 3,50 Euro.") == "Es kostet 3,50 Euro."
        assert normalizer.normalize_text("Version 1.2.3 ist da.") == "Version 1.2.3 ist da."

    def test_multiple_spaces_collapsed(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("ein  Test   hier") == "ein Test hier"

    def test_repeated_punctuation_collapsed(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("Wirklich??") == "Wirklich?"


class TestOrdinals:
    def test_detached_ordinal_dot(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("am 5 . Juli") == "am 5. Juli"

    def test_ordinal_at_end(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("Er wurde 1 .") == "Er wurde 1."


class TestOptInNumberRules:
    def test_decimal_comma_off_by_default(self, normalizer: GermanNormalizer) -> None:
        assert normalizer.normalize_text("3.5 Prozent") == "3.5 Prozent"

    def test_decimal_comma(self) -> None:
        n = GermanNormalizer(decimal_comma=True)
        assert n.normalize_text("3.5 Prozent") == "3,5 Prozent"

    def test_decimal_comma_leaves_versions_alone(self) -> None:
        n = GermanNormalizer(decimal_comma=True)
        assert n.normalize_text("Version 1.2.3") == "Version 1.2.3"

    def test_thousands_grouping(self) -> None:
        n = GermanNormalizer(thousands_grouping=True)
        assert n.normalize_text("Es waren 1000000 Euro") == "Es waren 1.000.000 Euro"

    def test_years_not_grouped(self) -> None:
        n = GermanNormalizer(thousands_grouping=True)
        assert n.normalize_text("Im Jahr 2026") == "Im Jahr 2026"


class TestProcess:
    def test_words_keep_raw_text(self, sample_result: TranscriptResult) -> None:
        sample_result.segments[0].text = "Guten Tag , Frau Müller ."
        out = GermanNormalizer().process(sample_result)
        assert out.segments[0].text == "Guten Tag, Frau Müller."
        # word-level entries stay truthful to recognizer output
        assert out.segments[0].words == sample_result.segments[0].words

    def test_idempotent(self, normalizer: GermanNormalizer) -> None:
        text = "Guten Tag, Frau Müller. Am 5. Juli."
        assert normalizer.normalize_text(text) == text
