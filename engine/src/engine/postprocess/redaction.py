"""Regex-based PII redaction hook.

Redaction is applied to segment text *and* word-level text: word timestamps
are exported in ``.json``, so leaving raw words in place would leak the very
strings the caller asked to redact.
"""

from __future__ import annotations

import re

from engine.config import RedactionRule
from engine.types import Segment, TranscriptResult, Word


class Redactor:
    def __init__(self, rules: list[RedactionRule]):
        self._compiled: list[tuple[re.Pattern[str], str]] = [
            (re.compile(rule.pattern), rule.replacement) for rule in rules
        ]

    def redact_text(self, text: str) -> str:
        for pattern, replacement in self._compiled:
            text = pattern.sub(replacement, text)
        return text

    def process(self, result: TranscriptResult) -> TranscriptResult:
        if not self._compiled:
            return result
        segments = [
            Segment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=self.redact_text(seg.text),
                words=[
                    Word(
                        start=w.start,
                        end=w.end,
                        text=self.redact_text(w.text),
                        probability=w.probability,
                    )
                    for w in seg.words
                ],
                speaker=seg.speaker,
            )
            for seg in result.segments
        ]
        return TranscriptResult(segments=segments, info=result.info)
