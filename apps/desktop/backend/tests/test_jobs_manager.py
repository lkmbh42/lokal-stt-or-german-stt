from __future__ import annotations

import threading

from conftest import wait_for_status  # type: ignore[import-not-found]
from fastapi.testclient import TestClient
from tests_helpers import upload  # type: ignore[import-not-found]


class TestCancellation:
    def test_cancel_processing_job(self, client: TestClient, stub_transcriber) -> None:
        stub_transcriber.block = threading.Event()
        job = upload(client, "long.wav").json()
        try:
            wait_for_status(client, job["id"], "processing")
            assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
            canceled = wait_for_status(client, job["id"], "canceled")
            assert canceled["status"] == "canceled"
        finally:
            stub_transcriber.block.set()

    def test_cancel_queued_job(self, client: TestClient, stub_transcriber) -> None:
        stub_transcriber.block = threading.Event()
        running = upload(client, "running.wav").json()
        queued = upload(client, "queued.wav").json()
        try:
            wait_for_status(client, running["id"], "processing")
            assert client.delete(f"/api/jobs/{queued['id']}").status_code == 204
            assert client.get(f"/api/jobs/{queued['id']}").json()["status"] == "canceled"
        finally:
            stub_transcriber.block.set()
        # the running job still completes normally
        wait_for_status(client, running["id"], "done")


class TestProgress:
    def test_progress_reaches_one(self, client: TestClient) -> None:
        job = upload(client, "p.wav").json()
        done = wait_for_status(client, job["id"], "done")
        assert done["progress"] == 1.0

    def test_transcript_persisted_as_json(self, client: TestClient, app_config) -> None:
        job = upload(client, "t.wav").json()
        wait_for_status(client, job["id"], "done")
        files = list(app_config.transcripts_dir.glob("*.json"))
        assert len(files) == 1
        assert "Guten Tag" in files[0].read_text(encoding="utf-8")

    def test_engine_error_marks_job_failed(self, client: TestClient, stub_transcriber) -> None:
        def boom(w: object) -> list:
            raise RuntimeError("Modell konnte nicht geladen werden")

        stub_transcriber.segments_fn = boom
        job = upload(client, "broken.wav").json()
        failed = wait_for_status(client, job["id"], "error")
        assert "Modell" in failed["error"]
