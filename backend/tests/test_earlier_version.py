"""An unfinished lesson keeps its script; a newer version is a choice, never a silent swap."""
from tests.test_interactive import prepare, start
from tutoring import guide as guide_mod


def test_newer_script_is_offered_instead_of_silently_resuming_the_old_one(harness, monkeypatch):
    seeded, first = prepare(harness, monkeypatch)
    lucas, topic = seeded['lucas']['id'], seeded['genghis']['id']
    state = start(harness, seeded, first)
    monkeypatch.setattr(guide_mod, 'write_plan', lambda text, models, **kwargs: ({'mode': 'expand', 'segments': [
        {'type': 'intro', 'text': 'A newer welcome.'}, {'type': 'read', 'from': 0, 'to': 99},
        {'type': 'action', 'text': 'What did Genghis Khan do with the tribes?', 'action_kind': 'answer'},
        {'type': 'recap', 'text': 'The tribes were united.'}]}, 'test-model'))
    newer = harness.call('POST', '/api/tutor/reader/guide', json={'learner': lucas, 'topic': topic, 'rewrite': True}).json()
    assert newer['guide_id'] != first['guide_id']

    reader = harness.call('GET', '/api/tutor/reader', params={'learner': lucas, 'topic': topic}).json()
    resume = reader['resume_current_lesson']
    assert resume['earlier_version'] and resume['updated_guide_id'] == newer['guide_id']
    assert resume['session_id'] == state['session_id']

    blocked = harness.call('POST', '/api/tutor/interactive/start', json={'learner': lucas, 'topic': topic, 'guide_id': newer['guide_id']})
    assert blocked.status_code == 409 and blocked.json()['detail']['code'] == 'earlier_version_open'
    # Continuing the earlier version still works with its own script.
    assert harness.call('POST', '/api/tutor/interactive/start', json={'learner': lucas, 'topic': topic,
                                                                        'guide_id': first['guide_id']}).status_code == 200

    opened = harness.call('POST', f"/api/tutor/sessions/{resume['session_id']}/replace-script",
                          json={'operation_id': 'open-updated-1', 'expected_revision': resume['revision'], 'guide_id': newer['guide_id']})
    assert opened.status_code == 200, opened.text
    new_session = opened.json()['session_id']
    assert new_session != state['session_id']
    assert harness.ctx.store.get('lesson_playback', new_session)['guide_id'] == newer['guide_id']
    assert harness.ctx.store.get('tutor_sessions', state['session_id'])['status'] == 'superseded'
    after = harness.call('GET', '/api/tutor/reader', params={'learner': lucas, 'topic': topic}).json()
    assert not after['resume_current_lesson']['earlier_version']
