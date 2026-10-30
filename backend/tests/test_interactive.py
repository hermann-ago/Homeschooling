"""Real HTTP/storage flows with deterministic AI responses and isolated curriculum files."""
import base64
from datetime import date

from tests.test_tutoring import seed_history, FakeTTS
from tutoring import guide as guide_mod, audio, interactive, skills


def prepare(harness, monkeypatch, resume=False):
    original_generate=harness.ctx.ai.generate
    def synthetic_review(*args,**kwargs):
        from tutoring.script_review import Review
        if isinstance(kwargs.get('schema'), type) and issubclass(kwargs['schema'], Review):return {'findings':[]}
        return original_generate(*args,**kwargs)
    monkeypatch.setattr(harness.ctx.ai,'generate',synthetic_review)
    seeded = seed_history(harness)
    if not resume:
        with harness.ctx.store.transaction() as tx:
            tx.delete("checkpoints", "2026-09-24-genghis-cp")
            tx.update("tutor_sessions", "2026-09-24-genghis", {"status": "completed"})
    monkeypatch.setattr(guide_mod, "write_plan", lambda text, models, **kwargs: ({"mode": "expand", "segments": [
        {"type": "intro", "text": "Let us read about Genghis Khan."},
        {"type": "read", "from": 0, "to": 99},
        {"type": "action", "text": "What did Genghis Khan do with the tribes?", "action_kind": "answer"},
        {"type": "recap", "text": "The tribes were united."}]}, "test-model"))
    response = harness.call("POST", "/api/tutor/reader/guide", json={"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"]})
    assert response.status_code == 200, response.text
    return seeded, response.json()


def start(harness, seeded, guide, slot_id=None):
    response = harness.call("POST", "/api/tutor/interactive/start", json={"learner": seeded["lucas"]["id"],
        "topic": seeded["genghis"]["id"], "guide_id": guide["guide_id"], "slot_id": slot_id})
    assert response.status_code == 200, response.text
    return response.json()


def change(harness, state, route, **payload):
    response = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/{route}",
                            json={"expected_revision": state["revision"], **payload})
    assert response.status_code == 200, response.text
    return response.json()


def correct(text, images, models):
    return {"feedback": "Yes, he brought the tribes together.", "result": "Correct", "ready_to_continue": True}


def pause(harness, state, guide):
    action = guide["actions"][0]
    return change(harness, state, "playback", sentence_index=action["resume_index"], action_id=action["id"])


def test_skills_are_versioned_isolated_exported_and_survive_grade_move(harness):
    seeded = seed_history(harness)
    subject_id = seeded["history"]["id"]
    url = f"/api/subjects/{subject_id}/teaching-skill"
    starter = harness.call("GET", url).json()
    assert "Story of the World" in starter["content"] and "spelling" in starter["content"].lower()
    saved = harness.call("PUT", url, json={"content": starter["content"] + "\nUse maps often.", "expected_version": 0}).json()
    assert saved["version"] == 1 and (harness.drive / saved["file_path"]).exists()
    other = harness.call("POST", "/api/subjects", json={"child_id": seeded["lucas"]["id"], "name": "Math"}).json()
    assert "Use maps often" not in harness.call("GET", f"/api/subjects/{other['id']}/teaching-skill").json()["content"]
    assert harness.call("PUT", url, json={"content": "Old edit", "expected_version": 0}).status_code == 409
    assert harness.call("PUT", f"/api/subjects/{subject_id}", json={"grade": "5th"}).status_code == 200
    again = harness.call("PUT", url, json={"content": starter["content"], "expected_version": 1}).json()
    assert again["version"] == 2 and "5th Grade" in again["file_path"]
    assert len(harness.call("GET", url + "/history").json()) == 2
    harness.restart()
    assert harness.call("GET", url).json()["content"] == starter["content"].strip()


def test_skill_edit_marks_guide_stale_but_session_pins_guide_and_skill(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = start(harness, seeded, guide)
    subject_id = seeded["history"]["id"]
    skill = skills.current(harness.ctx.store, subject_id)
    assert harness.call("PUT", f"/api/subjects/{subject_id}/teaching-skill", json={"content": skill["content"] + "\nMore maps.", "expected_version": skill["version"]}).status_code == 200
    params = {"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"]}
    assert not harness.call("GET", "/api/tutor/reader", params=params).json()["guide"]["current"]
    pinned = harness.call("GET", "/api/tutor/reader", params={**params, "session": state["session_id"]}).json()["guide"]
    assert pinned["guide_id"] == guide["guide_id"] and pinned["skill_id"] == guide["skill_id"] and pinned["current"]


def test_book_only_link_offers_exact_saved_tutoring_session_without_starting_another(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = start(harness, seeded, guide)
    sessions = harness.ctx.store.all('tutor_sessions')
    params = {'learner': seeded['lucas']['id'], 'topic': seeded['genghis']['id']}
    reader = harness.call('GET', '/api/tutor/reader', params=params).json()
    assert reader['resume_current_lesson']['path'].endswith('session=' + state['session_id'])
    assert reader['session_id'] is None  # Opening the source is still a read-only operation.
    pinned = harness.call('GET', '/api/tutor/reader', params={**params, 'session': state['session_id']}).json()
    assert pinned['resume_current_lesson'] is None
    assert harness.ctx.store.all('tutor_sessions') == sessions


def test_active_lesson_keeps_its_source_when_book_boundaries_change(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = start(harness, seeded, guide)
    params = {"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"]}
    original = harness.call("GET", "/api/tutor/reader", params=params).json()["passage"]
    with harness.ctx.store.transaction() as tx:
        tx.update("topics", seeded["genghis"]["id"], {"stop_before": None})
    changed = harness.call("GET", "/api/tutor/reader", params=params).json()
    assert "Kublai Khan" in changed["passage"]["passage"] and not changed["guide"]["current"]
    pinned = harness.call("GET", "/api/tutor/reader", params={**params, "session": state["session_id"]}).json()
    assert pinned["passage"] == original
    seen = []
    def assess(prompt, images, models):
        seen.append(prompt)
        return correct(prompt, images, models)
    monkeypatch.setattr(interactive, "gemini_turn", assess)
    state = pause(harness, state, guide)
    change(harness, state, "answer", action_id="action-1", message_id="original-source", text="He united the tribes.")
    assert "Kublai Khan" not in seen[0]


def test_resume_exact_imported_prompt_before_reading(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch, resume=True)
    state = start(harness, seeded, guide)
    assert state["playback"]["action_id"] == "resume"
    assert next(a for a in state["actions"] if a["action_id"] == "resume")["prompt"] == "What did the man who spoke up do next?"
    assert state["playback"]["reading_finished"] and not state["can_finish"]
    harness.restart()
    resumed = harness.call("GET", f"/api/tutor/sessions/{state['session_id']}/conversation").json()
    assert resumed["playback"] == state["playback"]


def test_pause_answer_continue_finish_saves_topic_and_slot_without_playback_mastery(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    with harness.ctx.store.transaction() as tx:
        slot = tx.insert("scheduled_slots", {"child_id": seeded["lucas"]["id"], "subject_id": seeded["history"]["id"],
            "topic_id": seeded["genghis"]["id"], "date": date.today(), "time_start": "09:00", "time_end": "09:20"})
    state = start(harness, seeded, guide, slot["id"])
    assert not harness.ctx.store.get("topics", seeded["genghis"]["id"])["completed"]
    assert harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/interactive-finish", json={"expected_revision": state["revision"]}).status_code == 400
    state = pause(harness, state, guide)
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    payload = {"expected_revision": state["revision"], "action_id": "action-1", "message_id": "answer-1", "text": "He united them."}
    response = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/answer", key="answer-operation", json=payload)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["playback"]["action_id"] == "action-1"  # no automatic playback
    assert len(harness.ctx.store.find("attempts", session_id=state["session_id"])) == 1
    assert "assessment" not in state["messages"][0] and "SECRET-KEY" not in response.text
    retry = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/answer", key="answer-operation", json=payload)
    assert retry.json() == state and len(harness.ctx.store.find("lesson_dialogue", session_id=state["session_id"])) == 2
    state = change(harness, state, "continue")
    assert not state["playback"]["action_id"]
    state = change(harness, state, "playback", sentence_index=len(guide["sentences"]), reading_finished=True)
    state = change(harness, state, "interactive-finish")
    assert state["status"] == "completed"
    assert harness.ctx.store.get("topics", seeded["genghis"]["id"])["understanding"] == "Independent"
    assert harness.ctx.store.find("completions", slot_id=slot["id"])


def test_skip_persists_for_next_session_and_final_topic_can_finish(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = pause(harness, start(harness, seeded, guide), guide)
    state = change(harness, state, "skip")
    assert state["playback"]["action_id"] == "action-1" and state["actions"][0]["status"] == "skipped"
    state = change(harness, state, "continue")
    state = change(harness, state, "playback", sentence_index=len(guide["sentences"]), reading_finished=True)
    change(harness, state, "interactive-finish")
    # Choosing another chapter leaves the skipped question in its original thread.
    next_seed = {**seeded, "genghis": seeded["conquest"]}
    response = harness.call("POST", "/api/tutor/reader/guide", json={"learner": seeded["lucas"]["id"], "topic": seeded["conquest"]["id"]})
    assert response.status_code == 200, response.text
    guide = response.json()
    state = start(harness, next_seed, guide)
    assert state["playback"]["action_id"] is None
    assert not any(a['source_action_id'] for a in state['actions'])
    assert any(a['status']=='skipped' for a in harness.ctx.store.find('lesson_actions',topic_id=seeded['genghis']['id']))
    state = pause(harness, state, guide)
    state = change(harness, state, 'skip')
    state = change(harness, state, 'continue')
    state = change(harness, state, "playback", sentence_index=len(guide["sentences"]), reading_finished=True)
    assert state["playback"]["action_id"] is None
    assert change(harness, state, "interactive-finish")["status"] == "completed"


def test_ai_failure_preserves_answer_retry_and_stale_or_foreign_writes_are_rejected(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = pause(harness, start(harness, seeded, guide), guide)
    def fail(*args):
        raise ValueError("Temporary quota issue")
    monkeypatch.setattr(interactive, "gemini_turn", fail)
    next_state = change(harness, state, "answer", action_id="action-1", message_id="saved-work", text="He united the tribes.")
    assert next_state["error"] and next_state["messages"][0]["text"] == "He united the tribes."
    assert not harness.ctx.store.find("attempts", session_id=state["session_id"])
    stale = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/skip", json={"expected_revision": state["revision"]})
    assert stale.status_code == 409
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    assessed = change(harness, next_state, "answer", action_id="action-1", message_id="saved-work", retry=True)
    assert len(assessed["messages"]) == 2 and assessed["messages"][0]["status"] == "assessed"
    with harness.ctx.store.transaction() as tx:
        child = tx.insert("children", {"name": "Other learner"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "Science"})
        topic = tx.insert("topics", {"subject_id": subject["id"], "title": "Plants", "page_start": 1, "page_end": 1})
    foreign = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/attempts", json={"expected_revision": assessed["revision"],
        "attempts": [{"question_ref": "alien", "first_result": "Correct", "topic_id": topic["id"]}]})
    assert foreign.status_code == 400


def test_photo_clarification_is_amendment_and_help_never_becomes_independent(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = pause(harness, start(harness, seeded, guide), guide)
    photo = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+X8AAAAASUVORK5CYII=")
    upload = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/evidence", data={"expected_revision": state["revision"]},
                          files={"file": ("answer.png", photo, "image/png")}).json()
    state = harness.call("GET", f"/api/tutor/sessions/{state['session_id']}/conversation").json()
    seen = []
    def unreadable(text, images, models):
        seen.extend(images)
        return {"feedback": "Could you type what the handwriting says?", "result": "Unreadable", "ready_to_continue": False}
    monkeypatch.setattr(interactive, "gemini_turn", unreadable)
    state = change(harness, state, "answer", action_id="action-1", message_id="photo-work", evidence_ids=[upload["evidence_id"]])
    assert seen[0][0] == photo
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    state = change(harness, state, "answer", action_id="action-1", message_id="clarification", text="He united the tribes.")
    attempts = harness.ctx.store.find("attempts", session_id=state["session_id"])
    assert attempts[0]["first_result"] == "Unreadable"
    assert attempts[1]["amends_attempt_id"] == attempts[0]["id"] and attempts[1]["independence"] == "independent"
    state = change(harness, state, "continue")
    state = change(harness, state, "playback", sentence_index=0, ask_question=True)
    # Free questions are conversation, not scored knowledge.
    state = change(harness, state, "answer", action_id=state["playback"]["action_id"], message_id="learner-question", text="What is a tribe?")
    assert len(harness.ctx.store.find("attempts", session_id=state["session_id"])) == 2


def test_narration_chunks_stop_at_every_action(harness, monkeypatch, tmp_path):
    harness.config.update(tts={**harness.config.get("tts"), "provider": "google-neural2"})
    seeded, guide = prepare(harness, monkeypatch)
    monkeypatch.setattr("config.home_tutor_dir", lambda: tmp_path / "ledger")
    monkeypatch.setattr(audio, "GoogleTTS", lambda project: FakeTTS())
    made = harness.call("POST", "/api/tutor/reader/narration", json={"learner": seeded["lucas"]["id"], "topic": seeded["genghis"]["id"], "guide": True, "dry_run": False})
    assert made.status_code == 200, made.text
    manifest = harness.call("GET", f"/api/tutor/audio/{made.json()['track_id']}/manifest").json()
    ends = [p["startSentence"] + len(p["sentenceStarts"]) - 1 for p in manifest["tracks"]]
    assert all(a["end_sentence"] in ends for a in guide["actions"])


def test_unsent_photo_survives_refresh_and_keeps_transcription_separate_from_typed_note(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = pause(harness, start(harness, seeded, guide), guide)
    photo = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+X8AAAAASUVORK5CYII=")
    response = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/evidence",
        data={"expected_revision": state["revision"], "action_id": "action-1"}, files={"file": ("answer.png", photo, "image/png")})
    assert response.status_code == 200
    evidence_id = response.json()["evidence_id"]
    harness.restart()
    state = harness.call("GET", f"/api/tutor/sessions/{state['session_id']}/conversation").json()
    assert state["draft_evidence"] == [{"id": evidence_id, "filename": "answer.png", "size_bytes": len(photo)}]
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: {
        "feedback": "Yes, he united them.", "result": "Correct", "transcription": "He united the tribes.", "ready_to_continue": True})
    state = change(harness, state, "answer", action_id="action-1", message_id="photo-with-note", text="Here is my work.", evidence_ids=[evidence_id])
    assert not state["draft_evidence"]
    attempt = harness.ctx.store.find("attempts", session_id=state["session_id"])[0]
    assert attempt["first_answer"] == "He united the tribes." and "Here is my work." in attempt["source_note"]
    assert state["messages"][0]["text"] == "Here is my work."


def test_hint_revision_and_later_independent_review(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = pause(harness, start(harness, seeded, guide), guide)
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: {
        "feedback": "Look at what happened to the tribes.", "result": "Not yet",
        "help": "Pointed to the tribes paragraph.", "follow_up": "What changed for the tribes?"})
    state = change(harness, state, "answer", action_id="action-1", message_id="first-wrong", text="They fought him.")
    assert state["playback"]["action_id"] == "action-1"
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    state = change(harness, state, "answer", action_id="action-1", message_id="after-hint", text="He united the tribes.")
    attempts = harness.ctx.store.find("attempts", session_id=state["session_id"])
    assert attempts[0]["first_answer"] == "They fought him."
    assert attempts[1]["first_answer"] == "They fought him." and attempts[1]["revised_answer"] == "He united the tribes."
    assert attempts[1]["help_given"] and attempts[1]["independence"] == "with_help"
    review = harness.ctx.store.find("reviews", child_id=seeded["lucas"]["id"])[0]
    assert review["status"] == "Open"
    state = change(harness, state, "continue")
    state = change(harness, state, "playback", sentence_index=len(guide["sentences"]), reading_finished=True)
    change(harness, state, "interactive-finish")
    assert harness.ctx.store.get("topics", seeded["genghis"]["id"])["understanding"] == "With help"
    with harness.ctx.store.transaction() as tx:
        topic = seeded["conquest"]
        passage = interactive.passages.load(harness.ctx, topic)
        plan = guide_mod.build(passage["sentences"], {"segments": [
            {"type": "read", "from": 0, "to": 99}, {"type": "action", "text": review["next_prompt"]}]})
        row = guide_mod.save(tx, topic, passage, plan, model="test", language="en-US",
                             skill=skills.current(tx, seeded["history"]["id"]))
    next_guide = guide_mod.package(harness.ctx, row, True)
    next_seed = {**seeded, "genghis": topic}
    state = pause(harness, start(harness, next_seed, next_guide), next_guide)
    change(harness, state, "answer", action_id="action-1", message_id="later-independent", text="He united the tribes.")
    assert harness.ctx.store.get("reviews", review["id"])["status"] == "Closed"


def test_clarifying_a_disputed_source_does_not_create_false_help(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = pause(harness, start(harness, seeded, guide), guide)
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: {
        "feedback": "Which part of the passage do you mean?", "result": "Source disputed", "ready_to_continue": True})
    state = change(harness, state, "answer", action_id="action-1", message_id="source-question", text="That is not what my book says.")
    assert state["actions"][0]["status"] == "pending"
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    state = change(harness, state, "answer", action_id="action-1", message_id="source-clarified", text="I see it now. He united the tribes.")
    attempts = harness.ctx.store.find("attempts", session_id=state["session_id"])
    assert attempts[1]["independence"] == "independent" and attempts[1]["amends_attempt_id"] == attempts[0]["id"]


def test_a_parent_supplied_first_answer_cannot_establish_independence(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    state = pause(harness, start(harness, seeded, guide), guide)
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: {
        "feedback": "That answer is correct. We will try a fresh check later.", "result": "Correct",
        "ready_to_continue": True, "assistance_used": True})
    state = change(harness, state, "answer", action_id="action-1", message_id="parent-help", text="My parent told me he united the tribes.")
    attempt = harness.ctx.store.find("attempts", session_id=state["session_id"])[0]
    assert attempt["first_answer"] == "My parent told me he united the tribes."
    assert attempt["independence"] == "with_help" and attempt["help_given"]
    assert harness.ctx.store.find("reviews", child_id=seeded["lucas"]["id"])[0]["status"] == "Open"
    state = change(harness, state, "continue")
    state = change(harness, state, "playback", sentence_index=len(guide["sentences"]), reading_finished=True)
    change(harness, state, "interactive-finish")
    assert harness.ctx.store.get("topics", seeded["genghis"]["id"])["understanding"] == "With help"


def test_missing_handwritten_question_source_cannot_be_graded_from_key(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    with harness.ctx.store.transaction() as tx:
        tx.insert("assignments", {"id": "old-test", "session_id": "2026-09-24-genghis", "child_id": seeded["lucas"]["id"],
            "topic_id": seeded["genghis"]["id"], "questions": [1], "status": "assigned"})
    state = start(harness, seeded, guide)
    assert state["playback"]["action_id"] == "assignment-old-test"
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: (_ for _ in ()).throw(AssertionError("Do not grade a key without questions")))
    state = change(harness, state, "answer", action_id="assignment-old-test", message_id="missing-source", text="He united them.")
    assert "error" not in state
    attempt = harness.ctx.store.find("attempts", session_id=state["session_id"])[0]
    assert attempt["first_result"] == "Source disputed" and attempt["independence"] == "not_assessed"
    assert "SECRET-KEY-ANSWER" not in str(state)
