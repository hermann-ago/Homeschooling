"""Rehearsal works with real AI/caches without contaminating learner evidence."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json

import httpx
import pytest

from app_context import AppContext
from dependencies import select_context
from services.test_mode import compatible_topic, manager, publish_audio
from storage.schema import TABLES
from tests.test_tutoring import seed_history
from tests.test_ai_costs import enable_voice, audio_response, SmallResponse
from tutoring import guide, passages, skills
from tutoring.expressive_audio import generate


@pytest.fixture
def ready(harness):
    s = seed_history(harness)
    harness.ctx._assign_subject_folders()
    harness.ctx.books.backfill()
    skills.ensure(harness.ctx)
    yield harness, s
    harness.ctx.shutdown()


def call(h, method, path, mode="live", **kw):
    return h.client.request(method, path, headers={"X-Homeschooling-Mode": mode}, **kw)


def enter(h):
    response = call(h, "POST", "/api/test-mode", json={"enabled": True})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_bookmarked_rehearsal_resumes_existing_records_and_rejects_ended_sessions(ready):
    h, s = ready; token = enter(h)
    ctx = manager(h.ctx).get(token)
    with ctx.store.transaction() as tx:
        tx.update('topics', s['genghis']['id'], {'completed': True})
    resumed = call(h, 'POST', '/api/test-mode', json={'enabled': True, 'token': token})
    assert resumed.status_code == 200 and resumed.json()['token'] == token
    assert manager(h.ctx).get(token).store.get('topics', s['genghis']['id'])['completed']
    assert not h.ctx.store.get('topics', s['genghis']['id'])['completed']
    manager(h.ctx).end(token)
    assert call(h, 'POST', '/api/test-mode', json={'enabled': True, 'token': token}).status_code == 409


def rows(ctx):
    return {name: copy.deepcopy(ctx.store.all(name)) for name in TABLES}


def test_rehearsal_records_files_and_completion_never_change_real_state(ready):
    h, s = ready
    before = rows(h.ctx)
    token = enter(h)
    ctx = manager(h.ctx).get(token)
    assert call(h, "GET", "/api/session", token).json()["test_mode"]
    assert not call(h, "GET", "/api/session").json()["test_mode"]
    assert call(h, "POST", "/api/children", token, json={"name": "Pretend learner"}).status_code == 201
    with ctx.store.transaction() as tx:
        tx.update("topics", s["genghis"]["id"], {"completed": True})
        tx.insert("attempts", {"id": "pretend-answer", "session_id": "2026-09-24-genghis",
                               "child_id": s["lucas"]["id"], "topic_id": s["genghis"]["id"],
                               "question_ref": "test-q", "first_result": "Not yet", "first_answer": "Pretend mistake"})
    started = call(h, "POST", "/api/tutor/sessions/start", token,
                   json={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    response = call(h, "POST", f"/api/tutor/sessions/{started['session_id']}/checkpoint", token,
                    json={"expected_revision": started["revision"], "phase": "discussion", "next_prompt": "Pretend next question",
                          "observations": ctx.store.get("checkpoints", "2026-09-24-genghis-cp")["observations"]})
    assert response.status_code == 200, response.text
    original = h.ctx.file_bytes(s["book"]["file_path"])
    ctx.files.resolve(s["book"]["file_path"]).write_bytes(b"pretend book edit")
    assert h.ctx.file_bytes(s["book"]["file_path"]) == original
    assert rows(h.ctx) == before
    assert call(h, "POST", "/api/test-mode", token, json={"enabled": False}).status_code == 200
    assert rows(h.ctx) == before
    # Old tabs remain a refusal, never an unnoticed real write after exit.
    assert call(h, "POST", "/api/children", token, json={"name": "Stale tab"}).status_code == 409
    next_token = enter(h)
    next_ctx = manager(h.ctx).get(next_token)
    assert next_token != token
    assert not next_ctx.store.get("attempts", "pretend-answer")
    assert not next_ctx.store.get("topics", s["genghis"]["id"])["completed"]


def test_simultaneous_real_and_test_requests_use_their_own_contexts(ready):
    h, _ = ready
    token = enter(h)
    def write(i):
        return call(h, "POST", "/api/children", token if i % 2 else "live", json={"name": f"Learner {i}"}).status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert set(pool.map(write, range(8))) == {201}
    assert {r["name"] for r in h.ctx.store.all("children") if r["name"].startswith("Learner")} == {f"Learner {i}" for i in (0, 2, 4, 6)}
    assert {r["name"] for r in manager(h.ctx).get(token).store.all("children") if r["name"].startswith("Learner")} == {f"Learner {i}" for i in (1, 3, 5, 7)}


def test_invalid_modes_raw_downloads_and_idempotency_do_not_fall_back_to_live(ready):
    h, _ = ready
    assert call(h, "POST", "/api/children", "../real", json={"name": "Bad"}).status_code == 409
    token = enter(h)
    body = {"name": "Only in rehearsal"}
    headers = {"X-Homeschooling-Mode": token, "Idempotency-Key": "same-id"}
    first = h.client.post("/api/children", headers=headers, json=body)
    repeated = h.client.post("/api/children", headers=headers, json=body)
    assert repeated.json() == first.json()
    assert repeated.headers["x-idempotent-replay"] == "true"
    live = h.client.post("/api/children", headers={"X-Homeschooling-Mode": "live", "Idempotency-Key": "same-id"}, json={"name": "Real separate action"})
    assert live.status_code == 201
    test_download = h.client.get(f"/api/records/export?app_mode={token}")
    assert test_download.status_code == 200
    assert "Cookie" in test_download.headers["vary"]
    assert h.client.get("/api/session?app_mode=live").json()["environment"] == "live"


def test_reusable_guide_is_prepared_from_real_learning_then_available_normally(ready, monkeypatch):
    h, s = ready
    token = enter(h)
    ctx = manager(h.ctx).get(token)
    with ctx.store.transaction() as tx:
        tx.update("checkpoints", "2026-09-24-genghis-cp", {"next_prompt": "PRETEND DIFFICULTY DO NOT LEARN FROM THIS"})
    prompts = []
    def writer(text, models, **kwargs):
        prompts.append(text)
        return {"mode": "expand", "segments": [{"type": "intro", "text": "Let us read."}, {"type": "read", "from": 0, "to": 1}]}, "gpt-6-luna"
    monkeypatch.setattr(guide, "write_plan", writer)
    payload = {"learner": s["lucas"]["id"], "topic": s["genghis"]["id"]}
    before = {table: h.ctx.store.all(table) for table in ("topics", "attempts", "reviews", "tutor_sessions", "checkpoints")}
    prepared = call(h, "POST", "/api/tutor/reader/guide", token, json=payload)
    assert prepared.status_code == 200, prepared.text
    assert len(prompts) == 1 and "PRETEND DIFFICULTY" not in prompts[0]
    assert prepared.json()["guide_id"] in {r["id"] for r in h.ctx.store.all("guides")}
    reused = call(h, "POST", "/api/tutor/reader/guide", json=payload)
    assert reused.status_code == 200, reused.text
    assert reused.json()["guide_id"] == prepared.json()["guide_id"]
    assert len(prompts) == 1
    assert {table: h.ctx.store.all(table) for table in before} == before


def test_ai_is_shared_paid_and_identical_inputs_reuse_across_mode_and_restart(ready, monkeypatch):
    h, _ = ready
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-no-real-provider")
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        return httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [{"content": [{"type": "output_text", "text": '{"answer":"saved","note":null}'}]}]})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    token = enter(h)
    test = manager(h.ctx).get(token)
    assert test.ai is h.ctx.ai
    assert test.ai.generate("Exact preparation", schema=SmallResponse)["answer"] == "saved"
    assert h.ctx.ai.generate("Exact preparation", schema=SmallResponse)["answer"] == "saved"
    assert len(calls) == 2
    charge = h.ctx.ai.ledger.summary(h.ctx.ai.limits)["categories"]["teaching"]["used_usd"]
    assert charge > 0
    restarted = AppContext(h.config, start_worker=False)
    restarted.ai.http = httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("Cached result must not send a provider request")))
    assert restarted.ai.generate("Exact preparation", schema=SmallResponse)["answer"] == "saved"
    resumed = manager(restarted).get(token)
    assert resumed.ai is restarted.ai
    assert resumed.ai.ledger.summary(resumed.ai.limits)["categories"]["teaching"]["used_usd"] == charge
    restarted.shutdown()


def test_spending_and_credentials_cannot_be_changed_from_test_mode(ready):
    h, _ = ready
    token = enter(h)
    for path, payload in (("/api/ai/settings", {"pilot_passed": True}), ("/api/ai/key", {"provider": "openai", "key": "test-long-key-only"})):
        assert call(h, "PUT", path, token, json=payload).status_code == 400
    assert call(h, "POST", "/api/storage/drive-folder", token, json={"path": str(h.drive)}).status_code == 400
    assert call(h, "POST", "/api/host/shutdown", token, json={"instance_token": "any"}).status_code == 400
    ctx = manager(h.ctx).get(token)
    assert ctx.ai.limits == h.ctx.ai.limits
    with pytest.raises(ValueError):
        ctx.config.update(ai={"limits": {"teaching": 100}})


def test_generated_test_voice_survives_exit_and_is_reused_without_charge(ready):
    h, s = ready
    sent = []
    enable_voice(h, lambda req: (sent.append(req), audio_response())[1])
    token = enter(h)
    ctx = manager(h.ctx).get(token)
    topic = ctx.store.get("topics", s["genghis"]["id"])
    text = "A patient narration for the same passage."
    package = {"passage_sha256": passages.passage_sha256(text), "sentences": passages.split_sentences(text)}
    with select_context(ctx):
        made = generate(ctx, topic, package)
        publish_audio(ctx)
    assert len(sent) == 1
    assert h.ctx.store.get("audio_tracks", made["track_id"])
    charge = h.ctx.ai.ledger.summary(h.ctx.ai.limits)["categories"]["voice"]["used_usd"]
    manager(h.ctx).end(token)
    again = generate(h.ctx, h.ctx.store.get("topics", topic["id"]), package)
    assert again["reused"] and len(sent) == 1
    assert h.ctx.ai.ledger.summary(h.ctx.ai.limits)["categories"]["voice"]["used_usd"] == charge


def test_edited_test_sources_do_not_publish_a_guide_over_real_material(ready):
    h, s = ready
    token = enter(h)
    ctx = manager(h.ctx).get(token)
    assert compatible_topic(ctx, s["genghis"]["id"])
    with ctx.store.transaction() as tx:
        tx.update("topics", s["genghis"]["id"], {"start_at": "Test-only heading"})
    assert not compatible_topic(ctx, s["genghis"]["id"])
    assert h.ctx.store.get("topics", s["genghis"]["id"])["start_at"] == "Genghis Khan, Emperor of All Men"


@pytest.mark.parametrize('aligned', [False, True])
def test_automatic_recording_arrives_in_test_mode_without_live_learner_writes(ready, monkeypatch, aligned):
    h, seeded = ready
    enable_voice(h, lambda request: audio_response())
    original=h.ctx.ai.generate
    def review_only(*args,**kwargs):
        from tutoring.script_review import Review
        return {'findings':[]} if isinstance(kwargs.get('schema'), type) and issubclass(kwargs['schema'], Review) else original(*args,**kwargs)
    monkeypatch.setattr(h.ctx.ai,'generate',review_only)
    if aligned:
        from tutoring import narration_alignment
        h.config.update(tts={**h.config.get('tts'), 'aligned_blocks': True})
        monkeypatch.setattr(narration_alignment, 'available', lambda *_: True)
        monkeypatch.setattr(narration_alignment, 'validate_script', lambda *_: None)
        monkeypatch.setattr(narration_alignment, 'align', lambda _ctx, _data, rows, _lang: {
            'sentenceStarts': [i/len(rows) for i in range(len(rows))], 'duration': 1.,
            'alignment': {'version': narration_alignment.VERSION}})
    monkeypatch.setattr(guide, 'write_plan', lambda *args, **kwargs: ({'mode': 'expand', 'segments': [
        {'type': 'intro', 'text': 'Welcome to practice.'}, {'type': 'read', 'from': 0, 'to': 99},
        {'type': 'action', 'text': 'What changed?', 'action_kind': 'answer'}]}, 'mocked-teacher'))
    before = {name: h.ctx.store.all(name) for name in ('attempts', 'reviews', 'tutor_sessions', 'checkpoints', 'lesson_dialogue')}
    token = enter(h)
    prepared = call(h, 'POST', '/api/tutor/reader/guide', token, json={'learner': seeded['lucas']['id'], 'topic': seeded['genghis']['id']})
    assert prepared.status_code == 200, prepared.text
    # Voice preparation runs independently of the guide response.
    from tests.test_automatic_voice import wait_voice
    wait_voice(manager(h.ctx).get(token), prepared.json()['guide_id'])
    reader = call(h, 'GET', f"/api/tutor/reader?learner={seeded['lucas']['id']}&topic={seeded['genghis']['id']}", token)
    assert reader.status_code == 200, reader.text
    assert reader.json()['guide']['audio']
    assert reader.json()['guide']['voice_preparation']['status'] == 'ready'
    assert {name: h.ctx.store.all(name) for name in before} == before


def test_real_ai_answer_and_lesson_finish_record_only_practice_evidence(ready, monkeypatch):
    h, s = ready
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-only-no-real-provider")
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        result = {"feedback": "Yes, he united the tribes.", "result": "Correct", "ready_to_continue": True}
        if json.loads(request.content).get('instructions')=='Return only the structured editorial review.':
            result={'findings':[]}
        return httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 50},
            "output": [{"content": [{"type": "output_text", "text": json.dumps(result)}]}]})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(guide, "write_plan", lambda text, models, **kwargs: ({"mode": "expand", "segments": [
        {"type": "read", "from": 0, "to": 99},
        {"type": "action", "text": "What did he do with the tribes?", "action_kind": "answer"}]}, "gpt-6-luna"))
    token = enter(h)
    ctx = manager(h.ctx).get(token)
    with ctx.store.transaction() as tx:
        tx.delete("checkpoints", "2026-09-24-genghis-cp")
        tx.update("tutor_sessions", "2026-09-24-genghis", {"status": "completed"})
    before = {t: h.ctx.store.all(t) for t in ("topics", "attempts", "reviews", "tutor_sessions", "checkpoints", "lesson_dialogue")}
    prepared = call(h, "POST", "/api/tutor/reader/guide", token, json={"learner": s["lucas"]["id"], "topic": s["genghis"]["id"]}).json()
    response = call(h, "POST", "/api/tutor/interactive/start", token, json={"learner": s["lucas"]["id"], "topic": s["genghis"]["id"], "guide_id": prepared["guide_id"]})
    assert response.status_code == 200, response.text
    state = response.json()
    def change(route, **values):
        nonlocal state
        response = call(h, "POST", f"/api/tutor/sessions/{state['session_id']}/{route}", token,
                        json={"expected_revision": state["revision"], **values})
        assert response.status_code == 200, response.text
        state = response.json()
    action = prepared["actions"][0]
    change("playback", sentence_index=action["resume_index"], action_id=action["id"])
    change("answer", action_id=action["id"], message_id="practice-answer", text="He united them.")
    assert len(calls) == 4  # Review and feedback, each with token count and mocked generation.
    assert prepared['script_review']['status']=='approved'
    assert ctx.store.find("attempts", session_id=state["session_id"])
    change("continue")
    change("playback", sentence_index=len(prepared["sentences"]), reading_finished=True)
    change("interactive-finish")
    assert state["status"] == "completed"
    assert ctx.store.get("topics", s["genghis"]["id"])["completed"]
    assert {t: h.ctx.store.all(t) for t in before} == before


def test_paid_invalid_response_is_cached_instead_of_purchased_again(ready, monkeypatch):
    from services.ai_provider import StructuredResponseError
    h, _ = ready
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-only-no-real-provider")
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        return httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 20},
            "output": [{"content": [{"type": "output_text", "text": '{"wrong":"structure"}'}]}]})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    for _ in range(2):
        with pytest.raises(StructuredResponseError):
            h.ctx.ai.generate("Invalid but paid response", schema=SmallResponse)
    assert len(calls) == 2
