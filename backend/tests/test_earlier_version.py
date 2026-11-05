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


def test_repeating_a_finished_lesson_uses_the_newest_approved_script(harness, monkeypatch):
    import copy, datetime
    from tests.test_activity_integration import http_event
    from tests.test_activity_engine import engine_lesson
    from tutoring import interactive
    engine, state, _ = engine_lesson(harness, monkeypatch)
    monkeypatch.setattr(interactive, 'gemini_turn', lambda *args: {'feedback': 'Yes.', 'result': 'Correct', 'ready_to_continue': True})
    for _ in range(12):
        active = state['active_activity']
        if active is None:
            break
        kind = active['kind']
        command = 'finish' if kind == 'close_lesson' else 'reading_done' if kind == 'read_source' and active['status'] == 'pending' else 'submit_response' if kind == 'ask_question' and active['status'] == 'pending' else 'continue'
        state = http_event(harness, state, command, {'response_id': 'r1', 'text': 'He united the tribes.', 'assess_after_save': True} if command == 'submit_response' else {})
    assert state['status'] == 'completed'
    old = harness.ctx.store.get('guides', state['playback']['guide_id'])
    with harness.ctx.store.transaction() as tx:
        row = {k: v for k, v in copy.deepcopy(old).items() if k not in ('id', 'revision', 'updated_at', 'created_at')}
        newer = tx.insert('guides', {**row, 'id': old['id'] + '-newer', 'created_at': old['created_at'] + datetime.timedelta(hours=1)})
        tx.insert('lesson_script_reviews', {'id': 'review-newer', 'guide_id': newer['id'], 'input_sha256': 'x', 'policy_version': 1,
                                            'status': 'approved', 'method': 'ai', 'data': {'findings': []}})
    repeated = harness.call('POST', f"/api/tutor/sessions/{state['session_id']}/repeat", json={'operation_id': 'repeat-newest'}).json()
    assert repeated['playback']['guide_id'] == newer['id']
