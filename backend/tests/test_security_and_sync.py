import json

from security.network import allowed_host, is_private
from storage import PENDING, SAVED


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
    assert harness.call("POST", "/api/maintenance/begin", role="learner").status_code == 403
    assert harness.call("GET", "/api/tutor/learners", role="learner").status_code == 403
    assert harness.call("GET", "/api/tutor/learners", role="tutor").status_code == 200
    assert harness.call("POST", "/api/maintenance/begin", role="tutor").status_code == 403


def test_browsers_never_receive_google_credentials(harness, tmp_path):
    secrets_dir = harness.config.secrets_dir
    harness.ctx.auth.save_client({"installed": {"client_id": "abc.apps.googleusercontent.com",
                                                "client_secret": "desktop-secret"}})
    from security.secrets import write_secret
    write_secret(secrets_dir / "google-token.bin", json.dumps({"refresh_token": "refresh-secret"}).encode())
    for path in ("/api/google/status", "/api/sync/status", "/api/session", "/api/devices"):
        body = harness.call("GET", path).text
        assert "refresh-secret" not in body and "desktop-secret" not in body
    assert harness.call("GET", "/api/google/status").json()["connected"] is True


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


def test_outage_keeps_work_pending_and_saves_once_after_restart(harness):
    harness.sheets.fail_next("offline")
    r = harness.call("POST", "/api/children", key="offline-1", json={"name": "Lucas"})
    assert r.status_code == 201 and r.headers["x-sync-state"] == PENDING
    status = harness.call("GET", "/api/sync/status").json()
    assert status["state"] == PENDING and status["online"] is False
    harness.sheets.fail_next("offline")
    harness.restart()
    assert harness.call("GET", "/api/children").json()[0]["name"] == "Lucas"
    harness.call("POST", "/api/sync/now")
    assert harness.call("GET", "/api/sync/operations/offline-1").json()["state"] == SAVED
    assert len(harness.sheets.rows("Children")) == 2  # header + exactly one child
    replay = harness.call("POST", "/api/children", key="offline-1", json={"name": "Lucas"})
    assert replay.headers["x-sync-state"] == SAVED and len(harness.ctx.store.all("children")) == 1


def test_google_authorization_failure_asks_for_reconnect_and_keeps_work(harness):
    harness.sheets.fail_next("auth")
    r = harness.call("POST", "/api/children", key="auth-1", json={"name": "Lucas"})
    assert r.status_code == 201 and r.headers["x-sync-state"] == PENDING
    status = harness.call("GET", "/api/sync/status").json()
    assert status["auth_required"] is True and status["pending"] == 1
    assert harness.call("GET", "/api/google/status").json()["authorization_required"] is True
    harness.call("POST", "/api/sync/now")  # parent reconnected; the same operation is saved once
    assert harness.call("GET", "/api/sync/operations/auth-1").json()["state"] == SAVED
    assert harness.call("GET", "/api/sync/status").json()["auth_required"] is False


def test_concurrent_edit_is_a_recoverable_conflict(harness):
    child = harness.call("POST", "/api/children", json={"name": "Lucas"}).json()
    harness.ctx.store.flush()
    harness.sheets.edit_cell("Children", 1, 1, "5")  # edited in Sheets outside maintenance mode
    r = harness.call("PUT", f"/api/children/{child['id']}", key="edit-1", json={"nickname": "Luke"})
    assert r.headers["x-sync-state"] == "needs_reconciliation"
    unsettled = harness.call("GET", "/api/sync/unsettled").json()
    assert unsettled[0]["id"] == "edit-1" and "edited in Google Sheets" in unsettled[0]["last_error"]
    retry = harness.call("POST", "/api/sync/reconcile/edit-1/retry").json()
    assert retry["needs_reconciliation"] == 1  # still conflicting: nothing is overwritten silently
    harness.call("POST", "/api/sync/reconcile/edit-1/discard")
    assert harness.call("GET", "/api/sync/status").json()["state"] == SAVED
