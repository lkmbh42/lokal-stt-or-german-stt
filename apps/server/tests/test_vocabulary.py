from __future__ import annotations

from conftest import login, upload  # type: ignore[import-not-found]
from fastapi.testclient import TestClient


def _login_alice(client: TestClient, make_user) -> dict[str, str]:
    make_user("alice", "alice-passwort-123")
    return login(client, "alice", "alice-passwort-123")


class TestVocabularyCrud:
    def test_add_list_delete(self, client: TestClient, make_user) -> None:
        alice = _login_alice(client, make_user)
        created = client.post(
            "/api/vocabulary",
            headers=alice,
            json={"term": "Cappel", "variants": "Kabel, Kappel"},
        )
        assert created.status_code == 201
        entry = created.json()
        assert entry["term"] == "Cappel"

        listed = client.get("/api/vocabulary", headers=alice).json()
        assert [e["term"] for e in listed] == ["Cappel"]

        assert client.delete(f"/api/vocabulary/{entry['id']}", headers=alice).status_code == 204
        assert client.get("/api/vocabulary", headers=alice).json() == []

    def test_duplicate_term_updates_variants(self, client: TestClient, make_user) -> None:
        alice = _login_alice(client, make_user)
        client.post("/api/vocabulary", headers=alice, json={"term": "Cappel", "variants": "Kabel"})
        client.post(
            "/api/vocabulary", headers=alice, json={"term": "Cappel", "variants": "Kabel, Kappel"}
        )
        entries = client.get("/api/vocabulary", headers=alice).json()
        assert len(entries) == 1
        assert entries[0]["variants"] == "Kabel, Kappel"

    def test_empty_term_rejected(self, client: TestClient, make_user) -> None:
        alice = _login_alice(client, make_user)
        assert (
            client.post("/api/vocabulary", headers=alice, json={"term": "  "}).status_code == 422
        )


class TestVocabularyIsolation:
    def test_users_only_see_their_own(self, client: TestClient, make_user) -> None:
        make_user("alice", "alice-passwort-123")
        make_user("bob", "bob-passwort-1234")
        alice = login(client, "alice", "alice-passwort-123")
        bob = login(client, "bob", "bob-passwort-1234")
        alice_entry = client.post(
            "/api/vocabulary", headers=alice, json={"term": "Cappel"}
        ).json()
        assert client.get("/api/vocabulary", headers=bob).json() == []
        # bob cannot delete alice's entry
        assert (
            client.delete(f"/api/vocabulary/{alice_entry['id']}", headers=bob).status_code == 404
        )


class TestVocabularyAppliedToJobs:
    def test_terms_boost_and_variants_correct(
        self, client: TestClient, make_user, dispatcher, stub_transcriber
    ) -> None:
        alice = _login_alice(client, make_user)
        client.post(
            "/api/vocabulary",
            headers=alice,
            json={"term": "Cappel", "variants": "Kabel"},
        )
        # make the engine emit the mishear so the correction has something to fix
        from engine.types import Segment

        stub_transcriber.segments_fn = lambda w: [
            Segment(id=0, start=0.0, end=2.0, text="Heimweg nach Kabel")
        ]
        job = upload(client, alice, "weg.wav").json()
        dispatcher.run_all()

        options = stub_transcriber.calls[0]
        assert "Cappel" in (options.hotwords or "")  # boosted
        done = client.get(f"/api/jobs/{job['id']}", headers=alice).json()
        assert "Cappel" in done["text_preview"]  # corrected
        assert "Kabel" not in done["text_preview"]

    def test_user_hotwords_and_vocabulary_combine(
        self, client: TestClient, make_user, dispatcher, stub_transcriber
    ) -> None:
        alice = _login_alice(client, make_user)
        client.post("/api/vocabulary", headers=alice, json={"term": "Cappel"})
        upload(client, alice, "x.wav", data={"hotwords": "Marburg"})
        dispatcher.run_all()
        hotwords = stub_transcriber.calls[0].hotwords or ""
        assert "Marburg" in hotwords and "Cappel" in hotwords

    def test_no_vocabulary_leaves_options_clean(
        self, client: TestClient, make_user, dispatcher, stub_transcriber
    ) -> None:
        alice = _login_alice(client, make_user)
        upload(client, alice, "x.wav")
        dispatcher.run_all()
        assert stub_transcriber.calls[0].corrections == []
