from __future__ import annotations

from engine.formats.timecode import srt_time, vtt_time


def test_zero() -> None:
    assert srt_time(0.0) == "00:00:00,000"
    assert vtt_time(0.0) == "00:00:00.000"


def test_millisecond_rounding() -> None:
    assert srt_time(1.2345) == "00:00:01,234"  # banker's-free round of 234.5 -> 234
    assert srt_time(0.9996) == "00:00:01,000"


def test_hours_minutes() -> None:
    assert srt_time(3661.5) == "01:01:01,500"
    assert vtt_time(3661.5) == "01:01:01.500"


def test_negative_clamped_to_zero() -> None:
    assert srt_time(-0.5) == "00:00:00,000"
