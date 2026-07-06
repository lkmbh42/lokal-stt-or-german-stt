from __future__ import annotations

import io
import json
import zipfile

from conftest import wait_for_status  # type: ignore[import-not-found]
from fastapi.testclient import TestClient
from tests_helpers import upload  # type: ignore[import-not-found]


class TestUpload:
    def test_upload_and_complete(self, client: TestClient) -> None:
        response = upload(client, "besprechung.wav")
        assert response.status_code == 201
        job = response.json()
        assert job["status"] == "queued"
        assert job["filename"] == "besprechung.wav"

        done = wait_for_status(client, job["id"], "done")
        assert done["progress"] == 1.0
        assert done["duration"] == 5.0
        assert "Guten Tag" in done["text_preview"]

    def test_unsupported_extension_rejected(self, client: TestClient) -> None:
        response = upload(client, "malware.exe")
        assert response.status_code == 400
        assert "nicht unterstützt" in response.json()["detail"]

    def test_oversize_rejected(self, client: TestClient) -> None:
        # config caps at 1 MB
        response = upload(client, "big.wav", content=b"0" * (2 * 1024 * 1024))
        assert response.status_code == 413

    def test_empty_file_rejected(self, client: TestClient) -> None:
        response = upload(client, "empty.wav", content=b"")
        assert response.status_code == 400

    def test_path_traversal_filename_sanitized(self, client: TestClient) -> None:
        response = upload(client, "..\\..\\evil.wav")
        assert response.status_code == 201
        assert response.json()["filename"] == "evil.wav"

    def test_options_forwarded_to_engine(
        self, client: TestClient, stub_transcriber
    ) -> None:
        response = upload(
            client,
            "audio.wav",
            data={"initial_prompt": "Anthropic, Kubernetes", "hotwords": "Müller"},
        )
        wait_for_status(client, response.json()["id"], "done")
        options = stub_transcriber.calls[0]["options"]
        assert options.initial_prompt == "Anthropic, Kubernetes"
        assert options.hotwords == "Müller"
        assert options.language == "de"


class TestListingAndDelete:
    def test_list_returns_newest_first(self, client: TestClient) -> None:
        first = upload(client, "a.wav").json()
        second = upload(client, "b.wav").json()
        wait_for_status(client, second["id"], "done")
        ids = [j["id"] for j in client.get("/api/jobs").json()]
        assert set(ids) == {first["id"], second["id"]}

    def test_delete_done_job_removes_files(self, client: TestClient, app_config) -> None:
        job = upload(client, "x.wav").json()
        wait_for_status(client, job["id"], "done")
        assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
        assert client.get(f"/api/jobs/{job['id']}").status_code == 404
        assert list(app_config.transcripts_dir.iterdir()) == []

    def test_unknown_job_404(self, client: TestClient) -> None:
        assert client.get("/api/jobs/doesnotexist").status_code == 404


class TestExport:
    def _done_job(self, client: TestClient) -> str:
        job = upload(client, "meeting.wav").json()
        wait_for_status(client, job["id"], "done")
        return job["id"]

    def test_txt_export(self, client: TestClient) -> None:
        job_id = self._done_job(client)
        response = client.get(f"/api/jobs/{job_id}/export?format=txt")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "attachment" in response.headers["content-disposition"]
        assert "Guten Tag, Frau Müller." in response.text

    def test_docx_export_media_type(self, client: TestClient) -> None:
        job_id = self._done_job(client)
        response = client.get(f"/api/jobs/{job_id}/export?format=docx")
        assert response.status_code == 200
        assert "wordprocessingml" in response.headers["content-type"]
        assert response.content[:2] == b"PK"  # docx is a zip container

    def test_zip_export_contains_all_formats(self, client: TestClient) -> None:
        job_id = self._done_job(client)
        response = client.get(f"/api/jobs/{job_id}/export?format=all")
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        suffixes = {name.rsplit(".", 1)[1] for name in archive.namelist()}
        assert suffixes == {"txt", "srt", "vtt", "json", "docx"}

    def test_json_export_has_word_timestamps(self, client: TestClient) -> None:
        job_id = self._done_job(client)
        response = client.get(f"/api/jobs/{job_id}/export?format=json")
        payload = json.loads(response.content)
        assert payload["segments"][0]["words"]

    def test_export_before_done_is_409(self, client: TestClient, stub_transcriber) -> None:
        import threading

        stub_transcriber.block = threading.Event()
        job = upload(client, "slow.wav").json()
        try:
            response = client.get(f"/api/jobs/{job['id']}/export?format=txt")
            assert response.status_code == 409
        finally:
            stub_transcriber.block.set()

    def test_unknown_format_400(self, client: TestClient) -> None:
        job_id = self._done_job(client)
        assert client.get(f"/api/jobs/{job_id}/export?format=pdf").status_code == 400


class TestHealth:
    def test_health(self, client: TestClient) -> None:
        payload = client.get("/api/health").json()
        assert payload["status"] == "ok"
        assert payload["formats"] == ["txt", "srt", "vtt", "json", "docx"]
