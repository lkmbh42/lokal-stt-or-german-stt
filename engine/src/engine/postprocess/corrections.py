"""Custom-vocabulary corrections.

Deterministic whole-word replacement of known mishears with the correct term
(e.g. ``Kabel`` → ``Cappel``). Complements hotword *boosting*: boosting biases
the model toward a term before transcription; this fixes the cases where it
still comes out wrong afterwards.

* Matching is case-insensitive and word-boundary aware, so ``Kabel`` does not
  match inside ``Kabelbaum``.
* Sentence-initial capitalization is preserved: a capitalized match yields a
  capitalized replacement.
* Applied to segment text *and* word-level text (word timestamps are exported
  in ``.json``, so leaving the raw mishears there would be inconsistent).
"""

from __future__ import annotations

import re

from engine.config import CorrectionRule
from engine.types import Segment, TranscriptResult, Word


class VocabularyCorrections:
    def __init__(self, rules: list[CorrectionRule]):
        self._compiled: list[tuple[re.Pattern[str], str]] = [
            (re.compile(rf"\b{re.escape(rule.wrong)}\b", re.IGNORECASE), rule.right)
            for rule in rules
            if rule.wrong.strip() and rule.right.strip()
        ]

    def correct_text(self, text: str) -> str:
        for pattern, right in self._compiled:

            def repl(match: re.Match[str], r: str = right) -> str:
                return _match_case(match.group(0), r)

            text = pattern.sub(repl, text)
        return text

    def process(self, result: TranscriptResult) -> TranscriptResult:
        if not self._compiled:
            return result
        segments = [
            Segment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=self.correct_text(seg.text),
                words=[
                    Word(
                        start=w.start,
                        end=w.end,
                        text=self.correct_text(w.text),
                        probability=w.probability,
                    )
                    for w in seg.words
                ],
                speaker=seg.speaker,
            )
            for seg in result.segments
        ]
        return TranscriptResult(segments=segments, info=result.info)


def _match_case(matched: str, replacement: str) -> str:
    """Carry the matched token's leading capitalization onto the replacement."""
    if matched[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement
