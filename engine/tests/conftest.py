from __future__ import annotations

from pathlib import Path

import pytest

from engine.types import Segment, TranscriptInfo, TranscriptResult, Word

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def sample_result() -> TranscriptResult:
    """A hand-built two-segment German transcript with word timestamps."""
    return TranscriptResult(
        segments=[
            Segment(
                id=0,
                start=0.0,
                end=2.5,
                text="Guten Tag, Frau Müller.",
                words=[
                    Word(start=0.0, end=0.4, text="Guten", probability=0.99),
                    Word(start=0.4, end=0.8, text="Tag,", probability=0.98),
                    Word(start=0.9, end=1.3, text="Frau", probability=0.97),
                    Word(start=1.3, end=2.5, text="Müller.", probability=0.95),
                ],
            ),
            Segment(
                id=1,
                start=3.0,
                end=6.0,
                text="Die Prüfung findet am fünften Juli statt.",
                words=[
                    Word(start=3.0, end=3.3, text="Die", probability=0.99),
                    Word(start=3.3, end=3.9, text="Prüfung", probability=0.98),
                    Word(start=3.9, end=4.4, text="findet", probability=0.99),
                    Word(start=4.4, end=4.7, text="am", probability=0.99),
                    Word(start=4.7, end=5.3, text="fünften", probability=0.97),
                    Word(start=5.3, end=5.7, text="Juli", probability=0.98),
                    Word(start=5.7, end=6.0, text="statt.", probability=0.99),
                ],
            ),
        ],
        info=TranscriptInfo(
            language="de",
            language_probability=1.0,
            duration=6.0,
            duration_after_vad=5.5,
            model="test-model",
            device="cpu",
            compute_type="int8",
            engine_version="0.1.0",
        ),
    )
