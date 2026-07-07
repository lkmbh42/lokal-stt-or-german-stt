from __future__ import annotations

import numpy as np
import pytest
from conftest import StubTranscriber, wait_for_status  # type: ignore[import-not-found]
from engine.types import Segment
from fastapi.testclient import TestClient

from desktop_app.config import AppConfig
from desktop_app.jobs import JobManager
from desktop_app.live import SAMPLE_RATE, LiveSession


def pcm_silence(seconds: float) -> bytes:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.int16).tobytes()


def _session(config: AppConfig, stub: StubTranscriber) -> LiveSession:
    manager = JobManager.__new__(JobManager)  # save path unused in these tests
    return LiveSession(config=config, manager=manager, transcriber=stub)


class TestLiveSession:
    def test_short_buffer_is_skipped(self, app_config: AppConfig) -> None:
        stub = StubTranscriber(segments_fn=lambda w: [])
        session = _session(app_config, stub)
        session.add_chunk(pcm_silence(0.5))
        assert session.tick() == ([], "")
        assert stub.calls == []  # under 1 s: no inference at all

    def test_silence_trims_buffer(self, app_config: AppConfig) -> None:
        stub = StubTranscriber(segments_fn=lambda w: [])
        session = _session(app_config, stub)
        session.add_chunk(pcm_silence(10.0))
        committed, partial = session.tick()
        assert (committed, partial) == ([], "")
        assert session.pending_seconds <= 2.01  # silence dropped, short tail kept

    def test_trailing_silence_commits_segments(self, app_config: AppConfig) -> None:
        # 5 s buffer, speech ends at 3.0 s -> 2 s trailing silence >= 0.8 s
        stub = StubTranscriber(
            segments_fn=lambda w: [
                Segment(id=0, start=0.2, end=3.0, text="Guten Tag.")
            ]
        )
        session = _session(app_config, stub)
        session.add_chunk(pcm_silence(5.0))
        committed, partial = session.tick()
        assert [seg.text for seg in committed] == ["Guten Tag."]
        assert partial == ""
        assert session.committed_seconds == 3.0
        assert abs(session.pending_seconds - 2.0) < 0.01

    def test_committed_timestamps_are_offset(self, app_config: AppConfig) -> None:
        stub = StubTranscriber(
            segments_fn=lambda w: [
                Segment(id=0, start=0.0, end=len(w) / SAMPLE_RATE - 1.0, text="Satz.")
            ]
        )
        session = _session(app_config, stub)
        session.add_chunk(pcm_silence(4.0))
        first, _ = session.tick()
        session.add_chunk(pcm_silence(4.0))
        second, _ = session.tick()
        assert first[0].start == 0.0
        # second window starts after 3.0 committed seconds
        assert second[0].start == pytest.approx(3.0)
        assert second[0].end > first[0].end

    def test_speech_without_pause_stays_partial(self, app_config: AppConfig) -> None:
        # segment ends 0.2 s before buffer end -> below the 0.8 s commit gap
        stub = StubTranscriber(
            segments_fn=lambda w: [
                Segment(id=0, start=0.0, end=len(w) / SAMPLE_RATE - 0.2, text="Noch am Reden")
            ]
        )
        session = _session(app_config, stub)
        session.add_chunk(pcm_silence(3.0))
        committed, partial = session.tick()
        assert committed == []
        assert partial == "Noch am Reden"

    def test_live_ticks_use_fast_settings(self, app_config: AppConfig) -> None:
        stub = StubTranscriber(segments_fn=lambda w: [])
        session = _session(app_config, stub)
        session.add_chunk(pcm_silence(3.0))
        session.tick()
        options = stub.calls[0]["options"]
        assert options.word_timestamps is False
        assert options.beam_size == 1

    def test_write_wav_roundtrip(self, app_config: AppConfig, tmp_path) -> None:
        session = _session(app_config, StubTranscriber())
        session.add_chunk(pcm_silence(2.0))
        duration = session.write_wav(tmp_path / "out.wav")
        assert duration == pytest.approx(2.0)
        assert (tmp_path / "out.wav").stat().st_size > 2 * SAMPLE_RATE * 2


class TestLiveWebSocket:
    def test_start_stream_stop_without_save(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/live") as ws:
            ws.send_json({"type": "start", "options": {"initial_prompt": "Test"}})
            assert ws.receive_json() == {"type": "ready"}
            ws.send_bytes(pcm_silence(2.0))
            ws.send_json({"type": "stop", "save": False})
            # finalize commits the pending 2 s -> default stub segments
            messages = [ws.receive_json() for _ in range(3)]
            types = [m["type"] for m in messages]
            assert types == ["final", "final", "stopped"]
            assert messages[0]["segment"]["text"] == "Guten Tag, Frau Müller."
            assert messages[2]["job_id"] is None

    def test_stop_with_save_creates_completed_job(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/live") as ws:
            ws.send_json({"type": "start"})
            assert ws.receive_json() == {"type": "ready"}
            ws.send_bytes(pcm_silence(2.0))
            ws.send_json({"type": "stop", "save": True})
            while True:
                message = ws.receive_json()
                if message["type"] == "stopped":
                    break
            job_id = message["job_id"]
            assert job_id
        done = wait_for_status(client, job_id, "done")
        assert done["source"] == "live"
        assert done["filename"].startswith("aufnahme-")
        # full-quality re-transcription is exportable like any batch job
        export = client.get(f"/api/jobs/{job_id}/export?format=txt")
        assert "Guten Tag" in export.text

    def test_audio_before_start_is_error(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/live") as ws:
            ws.send_bytes(pcm_silence(1.0))
            message = ws.receive_json()
            assert message["type"] == "error"


class TestDualModel:
    def test_live_uses_fast_model_and_save_uses_accurate_model(
        self, app_config: AppConfig
    ) -> None:
        """config.live_engine splits the work: live partials on the fast
        model, the saved recording re-transcribed on the accurate one."""
        from conftest import StubTranscriber, wait_for_status  # type: ignore

        from desktop_app.app import create_app

        batch_stub = StubTranscriber()
        live_stub = StubTranscriber()
        app = create_app(
            app_config, transcriber=batch_stub, live_transcriber=live_stub
        )
        with TestClient(app) as client:
            with client.websocket_connect("/ws/live") as ws:
                ws.send_json({"type": "start"})
                assert ws.receive_json() == {"type": "ready"}
                ws.send_bytes(pcm_silence(2.0))
                ws.send_json({"type": "stop", "save": True})
                while True:
                    message = ws.receive_json()
                    if message["type"] == "stopped":
                        break
            # finalize ran on the live (fast) model...
            assert len(live_stub.calls) == 1
            assert live_stub.calls[0]["options"].beam_size == 1
            # ...and the saved job on the accurate batch model, full quality
            wait_for_status(client, message["job_id"], "done")
            assert len(batch_stub.calls) == 1
            assert batch_stub.calls[0]["options"].word_timestamps is True
