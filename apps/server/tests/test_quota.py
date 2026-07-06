"""Quota enforcement: server-side, not just UI-hidden (project brief)."""

from __future__ import annotations

import pytest
from conftest import login, upload  # type: ignore[import-not-found]
from fastapi.testclient import TestClient


@pytest.fixture
def alice(client: TestClient, make_user) -> dict[str, str]:
    make_user("alice", "alice-passwort-123")
    return login(client, "alice", "alice-passwort-123")


def set_quota(client: TestClient, username: str, **limits: float | None) -> None:
    admin = login(client, "admin", "admin-passwort-123")
    users = client.get("/api/admin/users", headers=admin).json()
    user_id = next(u["id"] for u in users if u["username"] == username)
    response = client.patch(f"/api/admin/users/{user_id}", headers=admin, json=limits)
    assert response.status_code == 200, response.text


class TestDailyQuota:
    def test_upload_rejected_when_daily_cap_reached(
        self, client: TestClient, alice, dispatcher
    ) -> None:
        # each fake upload probes as 5 s; cap at 0.2 min = 12 s → 2 uploads ok
        set_quota(client, "alice", daily_minutes_limit=0.2)
        assert upload(client, alice, "a.wav").status_code == 201
        assert upload(client, alice, "b.wav").status_code == 201
        rejected = upload(client, alice, "c.wav")
        assert rejected.status_code == 429
        assert "Kontingent" in rejected.json()["detail"]

    def test_canceled_jobs_do_not_burn_quota(
        self, client: TestClient, alice, dispatcher
    ) -> None:
        set_quota(client, "alice", daily_minutes_limit=0.2)
        first = upload(client, alice, "a.wav").json()
        client.delete(f"/api/jobs/{first['id']}", headers=alice)  # canceled while queued
        assert upload(client, alice, "b.wav").status_code == 201
        assert upload(client, alice, "c.wav").status_code == 201

    def test_unlimited_by_default(self, client: TestClient, alice) -> None:
        for i in range(5):
            assert upload(client, alice, f"file{i}.wav").status_code == 201

    def test_quota_status_endpoint(self, client: TestClient, alice, dispatcher) -> None:
        set_quota(client, "alice", daily_minutes_limit=10)
        upload(client, alice, "a.wav")
        dispatcher.run_all()
        status = client.get("/api/jobs/quota", headers=alice).json()
        assert status["daily_limit_minutes"] == 10
        assert status["monthly_limit_minutes"] is None
        # real duration (5 s from stub decode) counts once done
        assert status["used_today_minutes"] == pytest.approx(5 / 60, abs=0.01)

    def test_server_default_applies_without_user_override(
        self, settings, dispatcher, stub_transcriber, make_user
    ) -> None:
        from fastapi.testclient import TestClient as TC

        from server_app.app import create_app
        from server_app.db import Base, make_engine

        settings = settings.model_copy(update={"default_daily_minutes": 0.1})
        Base.metadata.create_all(make_engine(settings.database_url))
        app = create_app(settings=settings, dispatch=dispatcher)
        with TC(app) as client:
            make_user("carl", "carls-passwort-123")
            carl = login(client, "carl", "carls-passwort-123")
            assert upload(client, carl, "a.wav").status_code == 201  # 5 s of 6 s cap
            assert upload(client, carl, "b.wav").status_code == 429

    def test_rejection_is_audited(self, client: TestClient, alice) -> None:
        set_quota(client, "alice", daily_minutes_limit=0.05)  # 3 s cap < 5 s upload
        assert upload(client, alice, "zu-gross.wav").status_code == 429
        admin = login(client, "admin", "admin-passwort-123")
        entries = client.get(
            "/api/admin/audit?action=quota.rejected", headers=admin
        ).json()
        assert entries
        assert "zu-gross.wav" in entries[0]["detail"]


class TestMonthlyQuota:
    def test_monthly_cap(self, client: TestClient, alice) -> None:
        set_quota(client, "alice", monthly_minutes_limit=0.1)
        assert upload(client, alice, "a.wav").status_code == 201
        assert upload(client, alice, "b.wav").status_code == 429
