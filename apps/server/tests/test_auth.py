from __future__ import annotations

import time

from conftest import TEST_SECRET, login  # type: ignore[import-not-found]
from fastapi.testclient import TestClient

from server_app.auth.passwords import hash_password, verify_password
from server_app.auth.tokens import TokenService


class TestPasswords:
    def test_argon2_hash_and_verify(self) -> None:
        digest = hash_password("korrektes-pferd-batterie-klammer")
        assert digest.startswith("$argon2id$")
        assert verify_password(digest, "korrektes-pferd-batterie-klammer")
        assert not verify_password(digest, "falsches-passwort")

    def test_hashes_are_salted(self) -> None:
        assert hash_password("gleich") != hash_password("gleich")


class TestLogin:
    def test_bootstrap_admin_can_login(self, client: TestClient) -> None:
        headers = login(client, "admin", "admin-passwort-123")
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["username"] == "admin"
        assert me["role"] == "admin"

    def test_wrong_password_is_generic_401(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "falsch"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Anmeldung fehlgeschlagen"

    def test_unknown_user_same_generic_401(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login", json={"username": "gibtsnicht", "password": "x"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Anmeldung fehlgeschlagen"

    def test_inactive_user_cannot_login(self, client: TestClient, make_user) -> None:
        user_id = make_user("inaktiv", "passwort-mit-laenge")
        admin = login(client, "admin", "admin-passwort-123")
        client.patch(
            f"/api/admin/users/{user_id}", headers=admin, json={"is_active": False}
        )
        response = client.post(
            "/api/auth/login",
            json={"username": "inaktiv", "password": "passwort-mit-laenge"},
        )
        assert response.status_code == 401


class TestTokens:
    def test_refresh_rotates_pair(self, client: TestClient) -> None:
        pair = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin-passwort-123"},
        ).json()
        time.sleep(1.1)  # new iat/exp second so rotated tokens differ
        refreshed = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        ).json()
        assert refreshed["access_token"] != pair["access_token"]
        headers = {"Authorization": f"Bearer {refreshed['access_token']}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 200

    def test_refresh_token_rejected_as_access_token(self, client: TestClient) -> None:
        pair = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin-passwort-123"},
        ).json()
        headers = {"Authorization": f"Bearer {pair['refresh_token']}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_access_token_rejected_for_refresh(self, client: TestClient) -> None:
        pair = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin-passwort-123"},
        ).json()
        response = client.post(
            "/api/auth/refresh", json={"refresh_token": pair["access_token"]}
        )
        assert response.status_code == 401

    def test_garbage_token_rejected(self, client: TestClient) -> None:
        headers = {"Authorization": "Bearer nicht.ein.jwt"}
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_token_signed_with_other_key_rejected(self, client: TestClient) -> None:
        forged = TokenService("anderes-geheimnis").issue_pair("someid", "admin")[0]
        headers = {"Authorization": f"Bearer {forged}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_expired_token_rejected(self, client: TestClient) -> None:
        from datetime import timedelta

        expired = TokenService(TEST_SECRET, access_ttl=timedelta(seconds=-1)).issue_pair(
            "someid", "user"
        )[0]
        headers = {"Authorization": f"Bearer {expired}"}
        response = client.get("/api/auth/me", headers=headers)
        assert response.status_code == 401
        assert "abgelaufen" in response.json()["detail"]

    def test_missing_token_is_401(self, client: TestClient) -> None:
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/jobs").status_code == 401
