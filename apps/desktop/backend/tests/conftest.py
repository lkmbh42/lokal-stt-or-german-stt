from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import engine.audio
import numpy as np
import pytest
from engine.config import TranscribeOptions
from engine.types import Segment, TranscriptInfo, TranscriptResult, Word
from fastapi.testclient import TestClient

from desktop_app.app import create_app
from desktop_app.config import AppConfig


def make_result(segments: list[Segment], duration: float) -> TranscriptResult:
    return TranscriptResult(
        segments=segments,
        info=TranscriptInfo(
            language="de",
            duration=duration,
            model="stub",
            device="cpu",
            compute_type="int8",
        ),
    )


DEFAULT_SEGMENTS = [
    Segment(
        id=0,
        start=0.0,
        end=2.0,
        text="Guten Tag, Frau Müller.",
        words=[Word(start=0.0, end=2.0, text="Guten", probability=0.9)],
    ),
    Segment(id=1, start=2.5, end=5.0, text="Die Prüfung findet am fünften Juli statt."),
]


class StubTranscriber:
    """Deterministic engine stand-in.

    ``segments_fn`` maps a waveform to segments — live-session tests script
    commit behavior with it. ``block`` (an Event) simulates a slow job so
    cancellation paths can be exercised.
    """

    def __init__(
        self,
        segments_fn: Callable[[np.ndarray], list[Segment]] | None = None,
        block: threading.Event | None = None,
    ):
        self.segments_fn = segments_fn or (lambda w: list(DEFAULT_SEGMENTS))
        self.block = block
        self.calls: list[dict[str, Any]] = []

    def transcribe(
        self,
        audio: Any,
        options: TranscribeOptions | None = None,
        on_segment: Callable[[Segment], None] | None = None,
    ) -> TranscriptResult:
        waveform = audio if isinstance(audio, np.ndarray) else np.zeros(16000 * 5)
        self.calls.append({"samples": len(waveform), "options": options})
        if self.block is not None:
            deadline = time.monotonic() + 10
            while not self.block.is_set():
                if time.monotonic() > deadline:  # pragma: no cover
                    raise TimeoutError("stub never unblocked")
                if on_segment is not None:
                    # give the manager a chance to observe cancellation
                    on_segment(DEFAULT_SEGMENTS[0])
                time.sleep(0.02)
        segments = self.segments_fn(waveform)
        if on_segment is not None:
            for seg in segments:
                on_segment(seg)
        return make_result(segments, duration=len(waveform) / 16000.0)


@pytest.fixture
def stub_transcriber() -> StubTranscriber:
    return StubTranscriber()


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        data_dir=tmp_path / "data",
        max_upload_mb=1,
        frontend_dist=tmp_path / "no-dist",
        live={"tick_seconds": 10.0},  # type: ignore[arg-type]  # ticker quiet in tests
    )


@pytest.fixture(autouse=True)
def fake_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uploads in tests are not real audio — decode to 5 s of silence."""
    monkeypatch.setattr(
        engine.audio, "decode_audio", lambda p, sampling_rate=16000: np.zeros(80000, np.float32)
    )


@pytest.fixture
def client(app_config: AppConfig, stub_transcriber: StubTranscriber) -> Iterator[TestClient]:
    app = create_app(app_config, transcriber=stub_transcriber)
    with TestClient(app) as test_client:
        yield test_client


def wait_for_status(client: TestClient, job_id: str, status: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload["status"] == status:
            return payload
        if payload["status"] == "error" and status != "error":
            raise AssertionError(f"job failed: {payload['error']}")
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {status}")
