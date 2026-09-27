import json

from security.network import allowed_host, is_private
from storage import SAVED


def test_every_home_device_has_full_access_without_pairing(harness):
    home = harness.client  # no credential, like any browser on the home network
    assert home.get("/api/session").json()["device"]["role"] == "family"
    assert home.post("/api/children", json={"name": "Ana"}).status_code in (200, 201)
    assert home.post("/api/storage/backup").status_code == 200
    assert home.get("/api/tutor/learners").status_code == 200
    stale = {"Authorization": "Bearer hs_from-an-old-pairing"}  # browsers paired before keep working
    assert home.get("/api/session", headers=stale).json()["device"]["role"] == "family"
    assert home.post("/api/pairing/request", json={"device_name": "Tablet", "role": "learner"}).status_code in (404, 405)


def test_the_tutor_is_identified_by_its_credential(harness):
    assert harness.call("GET", "/api/session", role="tutor").json()["device"]["role"] == "tutor"
    assert harness.call("GET", "/api/tutor/learners", role="tutor").status_code == 200
    assert harness.call("POST", "/api/storage/backup", role="tutor").status_code == 403


def test_old_learner_and_parent_pairings_are_forgotten(tmp_path):
    import hashlib
    from security.devices import DeviceRegistry
    digest = lambda token: hashlib.sha256(token.encode()).hexdigest()
    (tmp_path / "devices.json").write_text(json.dumps({"devices": {
        "a": {"id": "a", "name": "Office Computer", "role": "learner", "token_hash": digest("old"),
              "created_at": 1, "last_seen": None},
        "t": {"id": "t", "name": "Claude Desktop", "role": "tutor", "token_hash": digest("agent"),
              "created_at": 1, "last_seen": None}}}))
    registry = DeviceRegistry(tmp_path)
    assert registry.authenticate("old") is None and registry.authenticate("agent").role == "tutor"
    assert list(json.loads((tmp_path / "devices.json").read_text())["devices"]) == ["t"]


def test_changes_from_other_websites_are_refused(harness):
    evil = harness.client.post("/api/children", json={"name": "X"}, headers={"Origin": "http://evil.example"})
    assert evil.status_code == 403 and "Homeschooling app" in evil.json()["detail"]
    sandboxed = harness.client.post("/api/children", json={"name": "X"}, headers={"Origin": "null"})
    assert sandboxed.status_code == 403
    app_page = harness.client.post("/api/children", json={"name": "Ana"}, headers={"Origin": "http://testserver"})
    assert app_page.status_code in (200, 201)
    assert harness.client.get("/api/health", headers={"Origin": "http://evil.example"}).status_code == 200


def test_no_google_credentials_are_needed_or_exposed(harness):
    from security.secrets import write_secret
    write_secret(harness.config.secrets_dir / "tutor-agent.bin", b"agent-secret")
    for path in ("/api/storage/status", "/api/session"):
        body = harness.call("GET", path).text
        assert "agent-secret" not in body and "client_secret" not in body
    assert not list(harness.config.dir.rglob("google-token*"))


def test_private_network_rules():
    assert is_private("192.168.1.20") and is_private("10.0.0.5") and is_private("127.0.0.1")
    assert is_private("fe80::1") and is_private("::ffff:192.168.0.3")
    assert not is_private("8.8.8.8") and not is_private("2001:4860::1")
    assert allowed_host("192.168.1.20:8000") and allowed_host("localhost:8000")
    assert not allowed_host("evil.example.com") and not allowed_host("8.8.8.8:8000")


def test_public_clients_and_foreign_hosts_are_refused(harness):
    from fastapi.testclient import TestClient
    public = TestClient(harness.app, client=("203.0.113.9", 5000))
    assert public.get("/api/health").status_code == 403
    rebinding = harness.client.get("/api/health", headers={"Host": "attacker.example"})
    assert rebinding.status_code == 403
    home = TestClient(harness.app, client=("192.168.1.30", 5000), base_url="http://192.168.1.2:8000")
    assert home.get("/api/health").status_code == 200


def test_retried_request_returns_original_response_without_duplicates(harness):
    first = harness.call("POST", "/api/children", key="add-lucas", json={"name": "Lucas"})
    again = harness.call("POST", "/api/children", key="add-lucas", json={"name": "Lucas"})
    assert again.headers.get("x-idempotent-replay") == "true"
    assert again.json() == first.json()
    assert len(harness.ctx.store.all("children")) == 1
    reused = harness.call("POST", "/api/children", key="add-lucas", json={"name": "Mila"})
    assert reused.status_code == 409


def test_saved_work_survives_restart_and_replays_once(harness):
    r = harness.call("POST", "/api/children", key="restart-1", json={"name": "Lucas"})
    assert r.status_code == 201 and r.headers["x-sync-state"] == SAVED
    harness.restart()
    assert harness.call("GET", "/api/children").json()[0]["name"] == "Lucas"
    assert harness.call("GET", "/api/sync/operations/restart-1").json()["state"] == SAVED
    replay = harness.call("POST", "/api/children", key="restart-1", json={"name": "Lucas"})
    assert replay.headers["x-sync-state"] == SAVED and len(harness.ctx.store.all("children")) == 1


def test_parent_can_back_up_and_export_from_settings(harness):
    harness.call("POST", "/api/children", json={"name": "Lucas"})
    backup = harness.call("POST", "/api/storage/backup").json()
    assert backup["counts"]["children"] == 1
    assert (harness.drive / "_App Backups" / backup["name"]).exists()
    export = harness.call("POST", "/api/storage/export").json()
    assert (harness.drive / export["path"]).exists()
    status = harness.call("GET", "/api/storage/status").json()
    assert status["last_backup"] == backup["name"] and status["drive_folder_available"] is True
