"""Finishing a lesson starts preparing the subject's next lesson in the background."""
from tests.test_interactive import prepare, start, pause, change, correct
from tutoring import curriculum_preparation, interactive


def finish(harness, seeded, guide, monkeypatch):
    state = pause(harness, start(harness, seeded, guide), guide)
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    response = harness.call("POST", f"/api/tutor/sessions/{state['session_id']}/answer", key="answer-next",
                            json={"expected_revision": state["revision"], "action_id": "action-1", "message_id": "answer-1", "text": "He united them."})
    state = change(harness, response.json(), "continue")
    state = change(harness, state, "playback", sentence_index=len(guide["sentences"]), reading_finished=True)
    return change(harness, state, "interactive-finish")


def test_finishing_a_lesson_queues_the_next_lesson_once(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    harness.config.update(preparation={'auto_next': True})
    launched = []
    monkeypatch.setattr(curriculum_preparation, 'launch', lambda ctx, job_id: launched.append(job_id))
    assert finish(harness, seeded, guide, monkeypatch)["status"] == "completed"
    jobs = harness.ctx.store.all('lesson_preparation_jobs')
    ordered = harness.ctx.tutor._topics(seeded['history']['id'])
    position = next(i for i, t in enumerate(ordered) if t['id'] == seeded['genghis']['id'])
    upcoming = next(t for t in ordered[position + 1:] if not t.get('completed'))
    assert [(j['topic_id'], j['target'], j['status']) for j in jobs] == [(upcoming['id'], 'both', 'queued')]
    assert launched == [jobs[0]['id']]
    # Another finish while that job is active does not queue a second one.
    assert curriculum_preparation.prepare_next(harness.ctx, seeded['lucas']['id'], seeded['history']['id'], seeded['genghis']['id'])['id'] == jobs[0]['id']
    assert len(launched) == 1


def test_turned_off_or_in_rehearsal_nothing_is_queued(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    monkeypatch.setattr(curriculum_preparation, 'launch', lambda ctx, job_id: (_ for _ in ()).throw(AssertionError('no launch')))
    assert finish(harness, seeded, guide, monkeypatch)["status"] == "completed"
    assert not harness.ctx.store.all('lesson_preparation_jobs')
