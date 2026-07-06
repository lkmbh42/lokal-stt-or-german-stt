from __future__ import annotations

from conftest import login, upload  # type: ignore[import-not-found]
from fastapi.testclient import TestClient


def actions(client: TestClient, admin: dict[str, str], **params: str) -> list[str]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return [e["action"] for e in client.get(f"/api/admin/audit?{query}", headers=admin).json()]


class TestAuditTrail:
    def test_full_job_lifecycle_is_audited(
        self, client: TestClient, make_user, dispatcher
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        job = upload(client, alice, "protokoll.wav").json()
        dispatcher.run_all()
        client.delete(f"/api/jobs/{job['id']}", headers=alice)

        admin = login(client, "admin", "admin-passwort-123")
        all_actions = actions(client, admin)
        for expected in ("auth.login", "job.submitted", "job.completed", "job.deleted"):
            assert expected in all_actions, f"{expected} not in {all_actions}"

    def test_failed_login_is_audited_with_username(self, client: TestClient) -> None:
        client.post("/api/auth/login", json={"username": "angreifer", "password": "x"})
        admin = login(client, "admin", "admin-passwort-123")
        entries = client.get(
            "/api/admin/audit?action=auth.login_failed", headers=admin
        ).json()
        assert entries[0]["username"] == "angreifer"

    def test_audit_requires_admin(self, client: TestClient, make_user) -> None:
        make_user("normal", "normales-passwort-1")
        headers = login(client, "normal", "normales-passwort-1")
        assert client.get("/api/admin/audit", headers=headers).status_code == 403
        assert client.get("/api/admin/audit/export", headers=headers).status_code == 403

    def test_csv_export(self, client: TestClient, make_user, dispatcher) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        upload(client, alice, "export-test.wav")
        admin = login(client, "admin", "admin-passwort-123")
        response = client.get("/api/admin/audit/export", headers=admin)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        body = response.content.decode("utf-8-sig")
        assert body.splitlines()[0] == "created_at,username,action,detail,ip"
        assert "job.submitted" in body

    def test_no_mutation_routes_exist(self, client: TestClient) -> None:
        admin = login(client, "admin", "admin-passwort-123")
        entries = client.get("/api/admin/audit", headers=admin).json()
        entry_id = entries[0]["id"]
        # append-only: no DELETE/PUT/PATCH surface for audit entries exists
        # (404 = no such route, 405 = method not allowed — both prove it)
        delete = client.delete(f"/api/admin/audit/{entry_id}", headers=admin)
        patch = client.patch(f"/api/admin/audit/{entry_id}", headers=admin)
        assert delete.status_code in (404, 405)
        assert patch.status_code in (404, 405)


class TestEtaAndStats:
    def test_eta_appears_once_speed_history_exists(
        self, client: TestClient, make_user, dispatcher
    ) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        # first job builds speed history
        upload(client, alice, "erster.wav")
        dispatcher.run_all()
        # second + third stay queued
        second = upload(client, alice, "zweiter.wav").json()
        third = upload(client, alice, "dritter.wav").json()
        assert second["queue_position"] == 1
        assert third["queue_position"] == 2
        listed = {j["filename"]: j for j in client.get("/api/jobs", headers=alice).json()}
        assert listed["dritter.wav"]["eta_seconds"] is not None
        assert listed["dritter.wav"]["eta_seconds"] >= listed["zweiter.wav"]["eta_seconds"]

    def test_eta_is_null_without_history(self, client: TestClient, make_user) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        job = upload(client, alice, "erster.wav").json()
        assert job["eta_seconds"] is None  # honest: no data yet, no fake number

    def test_admin_stats(self, client: TestClient, make_user, dispatcher) -> None:
        make_user("alice", "alice-passwort-123")
        alice = login(client, "alice", "alice-passwort-123")
        upload(client, alice, "a.wav")
        dispatcher.run_all()
        upload(client, alice, "b.wav")

        admin = login(client, "admin", "admin-passwort-123")
        stats = client.get("/api/admin/stats", headers=admin).json()
        assert stats["queue_depth"] == 1
        assert stats["max_concurrent_jobs"] == 1
        alice_row = next(u for u in stats["users"] if u["username"] == "alice")
        assert alice_row["job_count"] == 2
        assert alice_row["storage_bytes"] > 0
