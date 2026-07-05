"""German-specific text normalization.

Whisper output for German is generally well punctuated, so this stage is
deliberately conservative: it fixes mechanical artifacts (spacing, duplicate
punctuation, ordinal spacing) by default, while opinionated numeric rewrites
(decimal comma, thousands grouping) are opt-in per job. Aggressive rewriting
of recognized text is a WER risk, not a win — Phase 4 tunes this against
real samples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.types import Segment, TranscriptResult

# " 1 . Platz" / "am 3 . Mai" -> "1." / "3." (ordinal digit + detached dot)
_ORDINAL_GAP = re.compile(r"\b(\d+)\s+\.(?=\s|$)")
# space *before* closing punctuation: "Hallo ." -> "Hallo."
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
# missing space *after* sentence punctuation: "Hallo.Welt" -> "Hallo. Welt"
# (digits excluded on both sides so 3.5 / 1.000 / dates stay intact)
_MISSING_SPACE_AFTER = re.compile(r"(?<=[a-zäöüß])([.!?,;:])(?=[A-ZÄÖÜa-zäöüß])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_REPEAT_PUNCT = re.compile(r"([.,!?])\1+")
# standalone decimal "3.5" -> "3,5" (German decimal separator). Requires the
# whole number to be isolated, so version numbers (1.2.3) and German-style
# thousands (1.000) are left alone
_DECIMAL_POINT = re.compile(r"(?<![\d.])(\d+)\.(\d{1,2})(?![\d.])")
# 5+ digit integers -> German thousands grouping (4-digit numbers excluded:
# they are usually years)
_BIG_INT = re.compile(r"(?<![\d.,])(\d{5,})(?![\d.,])")


def _group_thousands(digits: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(reversed(digits)):
        if i and i % 3 == 0:
            out.append(".")
        out.append(ch)
    return "".join(reversed(out))


@dataclass(frozen=True)
class GermanNormalizer:
    """Normalize German transcript text.

    Only segment-level text is rewritten; word-level entries keep the raw
    recognizer output so their timestamps stay truthful to what was spoken.
    """

    fix_spacing: bool = True
    fix_ordinals: bool = True
    decimal_comma: bool = False
    thousands_grouping: bool = False

    def normalize_text(self, text: str) -> str:
        if self.fix_ordinals:
            text = _ORDINAL_GAP.sub(r"\1.", text)
        if self.fix_spacing:
            text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
            text = _MISSING_SPACE_AFTER.sub(r"\1 ", text)
            text = _REPEAT_PUNCT.sub(r"\1", text)
            text = _MULTI_SPACE.sub(" ", text).strip()
        if self.decimal_comma:
            text = _DECIMAL_POINT.sub(r"\1,\2", text)
        if self.thousands_grouping:
            text = _BIG_INT.sub(lambda m: _group_thousands(m.group(1)), text)
        return text

    def process(self, result: TranscriptResult) -> TranscriptResult:
        segments = [
            Segment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=self.normalize_text(seg.text),
                words=seg.words,
                speaker=seg.speaker,
            )
            for seg in result.segments
        ]
        return TranscriptResult(segments=segments, info=result.info)
