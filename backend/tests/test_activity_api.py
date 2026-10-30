"""Activity API uses the family/tutor boundary and canonical validated schemas."""
from tests.test_activity_engine import engine_lesson


def ensure_router(harness):
    if not any(r.path == "/api/tutor/activity-definitions" for r in harness.app.routes):
        from routers.activities import router
        harness.app.include_router(router, prefix="/api/tutor")


def test_definition_catalog_and_explicit_session_access(harness, monkeypatch):
    _, state, _ = engine_lesson(harness, monkeypatch)
    ensure_router(harness)
    definitions = harness.call("GET", "/api/tutor/activity-definitions").json()
    assert len(definitions["definitions"]) == 23
    path = f"/api/tutor/sessions/{state['session_id']}"
    assert harness.call("GET", path + "/activity-state", role="tutor").status_code == 403
    assert harness.call("POST", path + "/activity-access", role="tutor", json={"enabled": True}).status_code == 403
    assert harness.call("POST", path + "/activity-access", json={"enabled": True}).status_code == 200
    assert harness.call("GET", path + "/activity-state", role="tutor").status_code == 200
    invoke = {"operation_id": "api-invoke-question", "expected_revision": state["revision"], "kind": "ask_question", "content": {"prompt": "Explain one idea"}}
    shown = harness.call("POST", path + "/activities", role="tutor", json=invoke)
    assert shown.status_code == 200, shown.text
    active = shown.json()["active_activity"]
    payload = {"operation_id": "forged-child-answer", "expected_revision": shown.json()["revision"], "activity_id": active["id"],
        "interaction_id": active["interaction"]["id"], "type": "submit_response", "payload": {"response_id": "forged", "text": "Correct"}}
    assert harness.call("POST", path + "/activity-events", role="tutor", json=payload).status_code == 403
    assert not harness.ctx.store.all("activity_responses")


def test_api_rejects_unknown_tools_executable_content_and_stale_revision(harness, monkeypatch):
    _, state, _ = engine_lesson(harness, monkeypatch)
    ensure_router(harness)
    path = f"/api/tutor/sessions/{state['session_id']}/activities"
    body = {"operation_id": "invalid-activity-op", "expected_revision": state["revision"], "kind": "ask_question", "content": {"prompt": "<script>run()</script>"}}
    assert harness.call("POST", path, json=body).status_code == 422
    assert harness.call("POST", path, json={**body, "kind": "arbitrary_html", "content": {}}).status_code == 422
    assert harness.call("POST", path, json={**body, "content": {"prompt": "Explain"}, "expected_revision": 0}).status_code == 409


def test_repeating_in_test_mode_leaves_live_sessions_unchanged(harness, monkeypatch):
    from tests.test_test_mode import enter, call
    from services.test_mode import manager
    _, state, _ = engine_lesson(harness, monkeypatch)
    # A completed synthetic fixture; this test checks storage routing, not grading.
    with harness.ctx.store.transaction() as tx:
        tx.update("tutor_sessions", state["session_id"], {"status": "completed"})
        tx.update("lesson_playback", state["session_id"], {"action_id": None, "reading_finished": True})
        for action in tx.find("lesson_actions", session_id=state["session_id"]):
            tx.update("lesson_actions", action["id"], {"status": "answered"})
    before = harness.ctx.store.all("tutor_sessions")
    token = enter(harness)
    response = call(harness, "POST", f"/api/tutor/sessions/{state['session_id']}/repeat", mode=token,
                    json={"operation_id": "test-mode-repeat-lesson"})
    assert response.status_code == 200, response.text
    repeated = response.json()["session_id"]
    assert repeated != state["session_id"]
    assert manager(harness.ctx).get(token).store.get("tutor_sessions", repeated)
    assert harness.ctx.store.all("tutor_sessions") == before
    assert not harness.ctx.store.get("tutor_sessions", repeated)
