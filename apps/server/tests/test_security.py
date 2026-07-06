"""Phase 4 security pass: refresh rotation/revocation and rate limiting."""

from __future__ import annotations

import time

import pytest
from conftest import login  # type: ignore[import-not-found]
from fastapi.testclient import TestClient

from server_app.app import create_app
from server_app.db import Base, make_engine
from server_app.ratelimit import RateLimiter


def login_pair(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


class TestRefreshRotation:
    def test_rotated_refresh_token_cannot_be_replayed(self, client: TestClient) -> None:
        pair = login_pair(client, "admin", "admin-passwort-123")
        first = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert first.status_code == 200
        # replaying the ALREADY-USED refresh token must fail
        replay = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert replay.status_code == 401
        assert "nicht mehr gültig" in replay.json()["detail"]

    def test_replay_attempt_is_audited(self, client: TestClient) -> None:
        pair = login_pair(client, "admin", "admin-passwort-123")
        client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        client.post("/api/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        admin = login(client, "admin", "admin-passwort-123")
        entries = client.get(
            "/api/admin/audit?action=auth.token_replayed", headers=admin
        ).json()
        assert entries

    def test_logout_revokes_refresh_token(self, client: TestClient) -> None:
        pair = login_pair(client, "admin", "admin-passwort-123")
        headers = {"Authorization": f"Bearer {pair['access_token']}"}
        response = client.post(
            "/api/auth/logout", headers=headers,
            json={"refresh_token": pair["refresh_token"]},
        )
        assert response.status_code == 204
        refresh = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert refresh.status_code == 401

    def test_rotated_chain_keeps_working(self, client: TestClient) -> None:
        pair = login_pair(client, "admin", "admin-passwort-123")
        for _ in range(3):
            time.sleep(1.05)  # distinct iat per rotation
            response = client.post(
                "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
            )
            assert response.status_code == 200
            pair = response.json()
        headers = {"Authorization": f"Bearer {pair['access_token']}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 200

    def test_deactivation_revokes_all_refresh_tokens(
        self, client: TestClient, make_user
    ) -> None:
        user_id = make_user("opfer", "opfer-passwort-123")
        pair = login_pair(client, "opfer", "opfer-passwort-123")
        admin = login(client, "admin", "admin-passwort-123")
        client.patch(f"/api/admin/users/{user_id}", headers=admin, json={"is_active": False})
        client.patch(f"/api/admin/users/{user_id}", headers=admin, json={"is_active": True})
        # even though the account is active again, old sessions stay dead
        refresh = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert refresh.status_code == 401


class TestRateLimiting:
    def test_login_gets_429_after_burst(self, settings, dispatcher) -> None:
        limited = settings.model_copy(
            update={"auth_rate_limit_attempts": 3, "auth_rate_limit_window_seconds": 60.0}
        )
        Base.metadata.create_all(make_engine(limited.database_url))
        app = create_app(settings=limited, dispatch=dispatcher)
        with TestClient(app) as client:
            for _ in range(3):
                client.post(
                    "/api/auth/login", json={"username": "x", "password": "falsch"}
                )
            response = client.post(
                "/api/auth/login", json={"username": "x", "password": "falsch"}
            )
            assert response.status_code == 429
            assert int(response.headers["Retry-After"]) >= 1
            # refresh endpoint shares the limiter
            refresh = client.post("/api/auth/refresh", json={"refresh_token": "x"})
            assert refresh.status_code == 429

    def test_limiter_window_slides(self) -> None:
        limiter = RateLimiter(max_attempts=2, window_seconds=0.2)
        assert limiter.check("ip") is None
        assert limiter.check("ip") is None
        assert limiter.check("ip") is not None  # third within window blocked
        time.sleep(0.25)
        assert limiter.check("ip") is None  # window slid, allowed again

    def test_limiter_isolates_keys(self) -> None:
        limiter = RateLimiter(max_attempts=1, window_seconds=60)
        assert limiter.check("a") is None
        assert limiter.check("b") is None  # other IP unaffected
        assert limiter.check("a") is not None


class TestSecretsHygiene:
    def test_secret_key_is_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError

        from server_app.config import ServerSettings

        monkeypatch.delenv("STT_SECRET_KEY", raising=False)
        with pytest.raises(ValidationError):
            ServerSettings(database_url="sqlite://")  # type: ignore[call-arg]
