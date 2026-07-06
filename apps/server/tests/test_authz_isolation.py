"""Authorization tests — the most likely vulnerability class in this app
(project brief: "authorization bypass on job IDs is the most likely vuln").

Invariants under test:
* User B gets **404** (not 403, no oracle) for any operation on user A's job.
* Admin role is required for every /api/admin route.
* Deactivated users lose access immediately (not just at next login).
"""

from __future__ import annotations

from conftest import login, upload  # type: ignore[import-not-found]
from fastapi.testclient import TestClient


class TestJobIsolation:
    def _two_users_one_job(self, client: TestClient, make_user, dispatcher):
        make_user("alice", "alice-passwort-123")
        make_user("bob", "bob-passwort-1234")
        alice = login(client, "alice", "alice-passwort-123")
        bob = login(client, "bob", "bob-passwort-1234")
        job = upload(client, alice, "geheim.wav").json()
        dispatcher.run_all()
        return alice, bob, job["id"]

    def test_get_foreign_job_is_404(self, client, make_user, dispatcher) -> None:
        _, bob, job_id = self._two_users_one_job(client, make_user, dispatcher)
        assert client.get(f"/api/jobs/{job_id}", headers=bob).status_code == 404

    def test_export_foreign_job_is_404(self, client, make_user, dispatcher) -> None:
        _, bob, job_id = self._two_users_one_job(client, make_user, dispatcher)
        response = client.get(f"/api/jobs/{job_id}/export?format=txt", headers=bob)
        assert response.status_code == 404

    def test_delete_foreign_job_is_404_and_noop(
        self, client, make_user, dispatcher
    ) -> None:
        alice, bob, job_id = self._two_users_one_job(client, make_user, dispatcher)
        assert client.delete(f"/api/jobs/{job_id}", headers=bob).status_code == 404
        # Alice's job is untouched
        assert client.get(f"/api/jobs/{job_id}", headers=alice).status_code == 200

    def test_listing_never_shows_foreign_jobs(
        self, client, make_user, dispatcher
    ) -> None:
        _, bob, _ = self._two_users_one_job(client, make_user, dispatcher)
        upload(client, bob, "bobs-datei.wav")
        listed = client.get("/api/jobs", headers=bob).json()
        assert [j["filename"] for j in listed] == ["bobs-datei.wav"]

    def test_foreign_and_missing_job_are_indistinguishable(
        self, client, make_user, dispatcher
    ) -> None:
        _, bob, job_id = self._two_users_one_job(client, make_user, dispatcher)
        foreign = client.get(f"/api/jobs/{job_id}", headers=bob)
        missing = client.get(f"/api/jobs/{'0' * 32}", headers=bob)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()


class TestRbac:
    def test_user_cannot_access_admin_routes(self, client, make_user) -> None:
        make_user("normal", "normales-passwort-1")
        headers = login(client, "normal", "normales-passwort-1")
        assert client.get("/api/admin/users", headers=headers).status_code == 403
        assert client.get("/api/admin/jobs", headers=headers).status_code == 403
        response = client.post(
            "/api/admin/users",
            headers=headers,
            json={"username": "hacker", "password": "hacker-passwort-1", "role": "admin"},
        )
        assert response.status_code == 403

    def test_admin_sees_all_jobs_with_owner(
        self, client, make_user, dispatcher
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        upload(client, alice, "meeting.wav")
        admin = login(client, "admin", "admin-passwort-123")
        jobs = client.get("/api/admin/jobs", headers=admin).json()
        assert jobs[0]["filename"] == "meeting.wav"
        assert jobs[0]["username"] == "alice"

    def test_deactivation_locks_out_existing_token(self, client, make_user) -> None:
        user_id = make_user("kurzlebig", "kurzlebig-passwort")
        headers = login(client, "kurzlebig", "kurzlebig-passwort")
        assert client.get("/api/jobs", headers=headers).status_code == 200
        admin = login(client, "admin", "admin-passwort-123")
        client.patch(
            f"/api/admin/users/{user_id}", headers=admin, json={"is_active": False}
        )
        # same still-valid JWT — but the live is_active check rejects it
        assert client.get("/api/jobs", headers=headers).status_code == 401

    def test_admin_cannot_demote_self(self, client) -> None:
        admin = login(client, "admin", "admin-passwort-123")
        me = client.get("/api/auth/me", headers=admin).json()
        response = client.patch(
            f"/api/admin/users/{me['id']}", headers=admin, json={"is_active": False}
        )
        assert response.status_code == 400


class TestStorageIsolation:
    def test_uploads_land_in_per_user_directories(
        self, client, make_user, settings, dispatcher
    ) -> None:
        alice_id = make_user("alice", "alice-passwort-123")
        bob_id = make_user("bob", "bob-passwort-1234")
        alice = login(client, "alice", "alice-passwort-123")
        bob = login(client, "bob", "bob-passwort-1234")
        upload(client, alice, "a.wav")
        upload(client, bob, "b.wav")
        alice_files = list(settings.uploads_dir(alice_id).iterdir())
        bob_files = list(settings.uploads_dir(bob_id).iterdir())
        assert len(alice_files) == 1
        assert len(bob_files) == 1
        assert alice_files[0].parent != bob_files[0].parent
