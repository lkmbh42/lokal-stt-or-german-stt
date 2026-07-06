from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import engine.audio
import numpy as np
import pytest
from engine.config import TranscribeOptions
from engine.types import Segment, TranscriptInfo, TranscriptResult, Word
from fastapi.testclient import TestClient

from server_app.app import create_app
from server_app.auth.passwords import hash_password
from server_app.config import ServerSettings
from server_app.db import Base, make_engine, make_session_factory
from server_app.models import User
from server_app.tasks import run_transcription_job

TEST_SECRET = "test-secret-key-not-for-production-0000"

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
    def __init__(self, segments_fn: Callable[[np.ndarray], list[Segment]] | None = None):
        self.segments_fn = segments_fn or (lambda w: list(DEFAULT_SEGMENTS))
        self.calls: list[TranscribeOptions | None] = []

    def transcribe(
        self,
        audio: Any,
        options: TranscribeOptions | None = None,
        on_segment: Callable[[Segment], None] | None = None,
    ) -> TranscriptResult:
        self.calls.append(options)
        waveform = audio if isinstance(audio, np.ndarray) else np.zeros(80000)
        segments = self.segments_fn(waveform)
        if on_segment is not None:
            for seg in segments:
                on_segment(seg)
        return TranscriptResult(
            segments=segments,
            info=TranscriptInfo(
                language="de",
                duration=len(waveform) / 16000.0,
                model="stub",
                device="cpu",
                compute_type="int8",
            ),
        )


class ManualDispatcher:
    """Collects dispatched job ids; tests run them explicitly.

    This keeps the 'queued' state observable and exercises the same
    ``run_transcription_job`` code path the Celery worker uses.
    """

    def __init__(self, settings: ServerSettings, transcriber: StubTranscriber):
        self.settings = settings
        self.transcriber = transcriber
        self.pending: list[str] = []

    def __call__(self, job_id: str) -> None:
        self.pending.append(job_id)

    def run_next(self) -> None:
        job_id = self.pending.pop(0)
        run_transcription_job(job_id, self.settings, self.transcriber)

    def run_all(self) -> None:
        while self.pending:
            self.run_next()


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        secret_key=TEST_SECRET,
        data_dir=tmp_path / "data",
        max_upload_mb=1,
        bootstrap_admin_username="admin",
        bootstrap_admin_password="admin-passwort-123",
    )


@pytest.fixture
def stub_transcriber() -> StubTranscriber:
    return StubTranscriber()


@pytest.fixture
def dispatcher(settings: ServerSettings, stub_transcriber: StubTranscriber) -> ManualDispatcher:
    return ManualDispatcher(settings, stub_transcriber)


@pytest.fixture(autouse=True)
def fake_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        engine.audio,
        "decode_audio",
        lambda p, sampling_rate=16000: np.zeros(80000, np.float32),
    )


@pytest.fixture
def client(settings: ServerSettings, dispatcher: ManualDispatcher) -> Iterator[TestClient]:
    Base.metadata.create_all(make_engine(settings.database_url))
    app = create_app(settings=settings, dispatch=dispatcher)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def make_user(settings: ServerSettings) -> Callable[[str, str, str], str]:
    """Create a user directly in the DB; returns the user id."""

    def _make(username: str, password: str, role: str = "user") -> str:
        factory = make_session_factory(settings.database_url)
        session = factory()
        try:
            user = User(
                username=username, password_hash=hash_password(password), role=role
            )
            session.add(user)
            session.commit()
            return user.id
        finally:
            session.close()

    return _make


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(
    client: TestClient,
    headers: dict[str, str],
    filename: str = "audio.wav",
    content: bytes = b"RIFF" + b"0" * 400,
    data: dict[str, str] | None = None,
):
    return client.post(
        "/api/jobs",
        headers=headers,
        files={"file": (filename, content, "audio/wav")},
        data=data or {},
    )
