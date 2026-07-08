from __future__ import annotations

import io
import zipfile

from conftest import login, upload  # type: ignore[import-not-found]
from fastapi.testclient import TestClient


class TestJobLifecycle:
    def test_upload_process_export_roundtrip(
        self, client: TestClient, make_user, dispatcher
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")

        created = upload(client, alice, "besprechung.wav")
        assert created.status_code == 201
        job = created.json()
        assert job["status"] == "queued"
        assert job["queue_position"] == 1

        dispatcher.run_all()

        done = client.get(f"/api/jobs/{job['id']}", headers=alice).json()
        assert done["status"] == "done"
        assert done["progress"] == 1.0
        assert done["duration"] == 5.0
        assert "Guten Tag" in done["text_preview"]

        export = client.get(f"/api/jobs/{job['id']}/export?format=all", headers=alice)
        archive = zipfile.ZipFile(io.BytesIO(export.content))
        suffixes = {name.rsplit(".", 1)[1] for name in archive.namelist()}
        assert suffixes == {"txt", "srt", "vtt", "json", "docx"}

    def test_queue_positions_are_global_across_users(
        self, client: TestClient, make_user, dispatcher
    ) -> None:
        make_user("alice", "alice-passwort-123")
        make_user("bob", "bob-passwort-1234")
        alice = login(client, "alice", "alice-passwort-123")
        bob = login(client, "bob", "bob-passwort-1234")
        first = upload(client, alice, "a.wav").json()
        second = upload(client, bob, "b.wav").json()
        assert first["queue_position"] == 1
        # one shared GPU: bob queues behind alice even though it's his first job
        assert second["queue_position"] == 2

    def test_options_reach_the_engine(
        self, client: TestClient, make_user, dispatcher, stub_transcriber
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        upload(
            client,
            alice,
            "meeting.wav",
            data={"initial_prompt": "Anthropic, Kubernetes", "hotwords": "Müller"},
        )
        dispatcher.run_all()
        options = stub_transcriber.calls[0]
        assert options is not None
        assert options.initial_prompt == "Anthropic, Kubernetes"
        assert options.hotwords == "Müller"
        assert options.language == "de"

    def test_dictation_flag_forwarded_to_engine(
        self, client: TestClient, make_user, dispatcher, stub_transcriber
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        upload(client, alice, "diktat.wav", data={"dictation": "true"})
        dispatcher.run_all()
        assert stub_transcriber.calls[0].dictation_mode is True

    def test_dictation_defaults_off(
        self, client: TestClient, make_user, dispatcher, stub_transcriber
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        upload(client, alice, "normal.wav")
        dispatcher.run_all()
        assert stub_transcriber.calls[0].dictation_mode is False

    def test_cancel_queued_job(self, client: TestClient, make_user, dispatcher) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        job = upload(client, alice, "warten.wav").json()
        assert client.delete(f"/api/jobs/{job['id']}", headers=alice).status_code == 204
        # worker picks it up later and skips it
        dispatcher.run_all()
        status = client.get(f"/api/jobs/{job['id']}", headers=alice).json()
        assert status["status"] == "canceled"

    def test_cancel_mid_processing_via_flag(
        self, client: TestClient, make_user, dispatcher, stub_transcriber, settings
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        job = upload(client, alice, "lang.wav").json()

        def cancel_during_processing(waveform):
            # simulate the user hitting cancel while the engine is running:
            # the DB flag flips, then the next on_segment callback aborts
            from server_app.db import make_session_factory, session_scope
            from server_app.models import Job

            factory = make_session_factory(settings.database_url)
            with session_scope(factory) as session:
                row = session.get(Job, job["id"])
                assert row is not None
                row.cancel_requested = True
            from conftest import DEFAULT_SEGMENTS  # type: ignore[import-not-found]

            return list(DEFAULT_SEGMENTS)

        stub_transcriber.segments_fn = cancel_during_processing
        dispatcher.run_all()
        status = client.get(f"/api/jobs/{job['id']}", headers=alice).json()
        assert status["status"] == "canceled"

    def test_engine_failure_marks_error(
        self, client: TestClient, make_user, dispatcher, stub_transcriber
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")

        def boom(waveform):
            raise RuntimeError("GPU out of memory")

        stub_transcriber.segments_fn = boom
        job = upload(client, alice, "kaputt.wav").json()
        dispatcher.run_all()
        status = client.get(f"/api/jobs/{job['id']}", headers=alice).json()
        assert status["status"] == "error"
        assert "GPU out of memory" in status["error"]


class TestUploadValidation:
    def test_bad_extension(self, client: TestClient, make_user) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        assert upload(client, alice, "virus.exe").status_code == 400

    def test_oversize(self, client: TestClient, make_user) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        response = upload(client, alice, "gross.wav", content=b"0" * (2 * 1024 * 1024))
        assert response.status_code == 413

    def test_export_before_done_is_409(self, client: TestClient, make_user) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        job = upload(client, alice, "neu.wav").json()
        response = client.get(f"/api/jobs/{job['id']}/export?format=txt", headers=alice)
        assert response.status_code == 409


class TestAdminUserManagement:
    def test_admin_creates_user_who_can_login(self, client: TestClient) -> None:
        admin = login(client, "admin", "admin-passwort-123")
        created = client.post(
            "/api/admin/users",
            headers=admin,
            json={"username": "neu.benutzer", "password": "zehn-zeichen-mind"},
        )
        assert created.status_code == 201
        assert created.json()["role"] == "user"
        assert login(client, "neu.benutzer", "zehn-zeichen-mind")

    def test_duplicate_username_is_409(self, client: TestClient) -> None:
        admin = login(client, "admin", "admin-passwort-123")
        body = {"username": "doppelt", "password": "zehn-zeichen-mind"}
        assert client.post("/api/admin/users", headers=admin, json=body).status_code == 201
        assert client.post("/api/admin/users", headers=admin, json=body).status_code == 409

    def test_weak_password_rejected(self, client: TestClient) -> None:
        admin = login(client, "admin", "admin-passwort-123")
        response = client.post(
            "/api/admin/users",
            headers=admin,
            json={"username": "schwach", "password": "kurz"},
        )
        assert response.status_code == 422
