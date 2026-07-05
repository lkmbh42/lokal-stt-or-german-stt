from __future__ import annotations

from engine.config import RedactionRule
from engine.postprocess.redaction import Redactor
from engine.types import TranscriptResult


def test_segment_and_word_text_redacted(sample_result: TranscriptResult) -> None:
    redactor = Redactor([RedactionRule(pattern=r"Müller", replacement="[NAME]")])
    out = redactor.process(sample_result)
    assert out.segments[0].text == "Guten Tag, Frau [NAME]."
    assert out.segments[0].words[3].text == "[NAME]."
    # timestamps preserved
    assert out.segments[0].words[3].start == 1.3


def test_default_replacement_marker(sample_result: TranscriptResult) -> None:
    out = Redactor([RedactionRule(pattern=r"\bJuli\b")]).process(sample_result)
    assert "[REDIGIERT]" in out.segments[1].text


def test_multiple_rules_apply_in_order(sample_result: TranscriptResult) -> None:
    out = Redactor(
        [
            RedactionRule(pattern=r"Müller", replacement="X"),
            RedactionRule(pattern=r"Frau X", replacement="[PERSON]"),
        ]
    ).process(sample_result)
    assert out.segments[0].text == "Guten Tag, [PERSON]."


def test_no_rules_is_identity(sample_result: TranscriptResult) -> None:
    assert Redactor([]).process(sample_result) is sample_result
