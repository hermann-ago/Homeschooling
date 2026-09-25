import json

from security.network import allowed_host, is_private
from storage import SAVED


def test_pairing_requires_host_approval_and_issues_role_token(harness):
    client = harness.client
    request = client.post("/api/pairing/request", json={"device_name": "Kitchen tablet", "role": "learner"}).json()
    assert client.post("/api/pairing/poll", json={"request_id": request["request_id"],
                                                  "poll_secret": request["poll_secret"]}).json()["status"] == "waiting"
    waiting = client.get("/api/pairing/waiting").json()
    assert waiting[0]["code"] == request["code"]
    wrong = client.post("/api/pairing/approve", json={"request_id": request["request_id"], "code": "000000"})
    assert wrong.status_code == 403 or request["code"] == "000000"
    client.post("/api/pairing/approve", json={"request_id": request["request_id"], "code": request["code"]})
    result = client.post("/api/pairing/poll", json={"request_id": request["request_id"],
                                                    "poll_secret": request["poll_secret"]}).json()
    assert result["status"] == "approved" and result["role"] == "learner"
    session = client.get("/api/session", headers={"Authorization": f"Bearer {result['token']}"}).json()
    assert session["device"]["role"] == "learner"
    # The token is released exactly once.
    assert client.post("/api/pairing/poll", json={"request_id": request["request_id"],
                                                  "poll_secret": request["poll_secret"]}).json()["status"] == "expired"


def test_unpaired_and_learner_devices_are_limited(harness):
    assert harness.client.get("/api/children").status_code == 401
    assert harness.call("POST", "/api/children", role="learner", json={"name": "X"}).status_code == 403
    assert harness.call("POST", "/api/storage/backup", role="learner").status_code == 403
    assert harness.call("GET", "/api/tutor/learners", role="learner").status_code == 403
    assert harness.call("GET", "/api/tutor/learners", role="tutor").status_code == 200
    assert harness.call("POST", "/api/storage/backup", role="tutor").status_code == 403
    assert harness.call("POST", "/api/storage/drive-folder", role="learner", json={"path": "/tmp"}).status_code == 403


def test_no_google_credentials_are_needed_or_exposed(harness):
    from security.secrets import write_secret
    write_secret(harness.config.secrets_dir / "tutor-agent.bin", b"agent-secret")
    for path in ("/api/storage/status", "/api/session", "/api/devices"):
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
    assert (harness.drive / "Backups" / backup["name"]).exists()
    export = harness.call("POST", "/api/storage/export").json()
    assert (harness.drive / export["path"]).exists()
    status = harness.call("GET", "/api/storage/status").json()
    assert status["last_backup"] == backup["name"] and status["drive_folder_available"] is True
