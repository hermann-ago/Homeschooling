"""Learning memory uses durable evidence, keeps amendments, and isolates rehearsal."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from tests.test_tutoring import seed_history
from services.test_mode import manager
from tutoring.learning_memory import evidence_state, summarize


def path(s):
    return f"/api/records/learning/{s['lucas']['id']}/{s['history']['id']}"


def add_attempt(h, s, aid='first', **extra):
    with h.ctx.store.transaction() as tx:
        tx.insert('attempts', {'id': aid, 'session_id': '2026-09-24-genghis', 'child_id': s['lucas']['id'],
            'topic_id': s['genghis']['id'], 'question_ref': 'Q1', 'first_answer': 'Uncertain handwriting',
            'first_result': 'Unreadable', 'reading_certainty': 'unclear', 'independence': 'not_assessed', **extra})
    return h.ctx.store.get('attempts', aid)


@pytest.mark.parametrize('result,certainty,help,state', [
    ('Unreadable', 'unclear', None, 'clarification'), ('Source disputed', 'clear', None, 'clarification'),
    ('Unanswered', 'clear', None, 'not_checked'), ('Correct', 'clear', 'Hint', 'needs_help'),
    ('Correct', 'clear', None, 'independent'), ('Not yet', 'clear', None, 'needs_help')])
def test_unassessed_and_helped_work_cannot_establish_independence(result, certainty, help, state):
    assert evidence_state({'first_result': result, 'reading_certainty': certainty, 'help_given': help,
                           'independence': 'independent'}) == state


def test_repeated_help_requires_multiple_lessons_and_retention_requires_later_day():
    def item(aid, when='2026-09-24', session='same', state='needs_help'):
        return {'id': aid, 'date': when, 'created_at': when, 'session_id': session, 'state': state}
    assert not summarize([item('1'), item('2')], [])['repeated_difficulty']
    assert summarize([item('1'), item('2', session='other')], [])['repeated_difficulty']
    assert summarize([item('1', state='independent'), item('2', state='independent')], [])['state'] == 'independent'
    assert summarize([item('1', state='independent'), item('2', when='2026-09-28', state='independent')], [])['state'] == 'retained'
    closed = [{'id': 'review', 'status': 'Closed', 'last_outcome': 'Independent'}]
    assert summarize([item('1', state='independent')], closed)['state'] == 'independent'
    assert summarize([item('1', state='independent'), item('2', state='independent')], closed)['state'] == 'independent'
    assert summarize([], closed)['state'] == 'not_checked'


def test_older_reviews_survive_recent_lessons_and_snapshots_are_reconstructable(harness):
    h = harness; s = seed_history(h); add_attempt(h, s, first_result='Not yet', reading_certainty='clear')
    with h.ctx.store.transaction() as tx:
        tx.insert('reviews', {'id': 'old-review', 'child_id': s['lucas']['id'], 'topic_id': s['genghis']['id'],
            'concept': 'Explain Mongolia', 'status': 'Open', 'next_due': date(2026, 9, 25), 'next_prompt': 'Locate Mongolia.'})
        for n in range(5):
            tx.insert('tutor_sessions', {'id': f'later-{n}', 'child_id': s['lucas']['id'], 'subject_id': s['history']['id'],
                'topic_id': s['conquest']['id'], 'status': 'completed', 'date': date(2026, 10, n+1)})
    before = copy.deepcopy(h.ctx.store.all('attempts'))
    data = h.call('GET', path(s)).json()
    assert data['topics'][0]['state'] == 'needs_help' and data['unmapped_evidence'] == ['first']
    packet = h.ctx.learning_memory.packet(s['lucas']['id'], s['history']['id'], s['conquest']['id'])
    assert packet['older_reviews'][0]['id'] == 'old-review'
    assert h.call('GET', path(s)).json()['snapshot_id'] == data['snapshot_id']
    assert len(h.ctx.store.all('learning_snapshots')) == 1
    h.restart()
    assert h.call('GET', path(s)).json()['fingerprint'] == data['fingerprint']
    with h.ctx.store.transaction() as tx:
        tx.update('tutor_sessions', '2026-09-24-genghis', {'date': date(2026, 9, 23)})
    next_data = h.call('GET', path(s)).json()
    assert next_data['summary_version'] == 2 and next_data['evidence'][0]['date'] == '2026-09-23'
    assert h.ctx.store.all('attempts') == before


def test_changed_summary_rules_create_a_new_snapshot_without_rewriting_evidence(harness, monkeypatch):
    from tutoring import learning_memory
    h = harness; s = seed_history(h)
    add_attempt(h, s, first_result='Correct', reading_certainty='clear', independence='independent')
    original = copy.deepcopy(h.ctx.store.all('attempts'))
    current = learning_memory.VERSION
    with monkeypatch.context() as old_rules:
        old_rules.setattr(learning_memory, 'VERSION', 'older-summary-rules')
        first = h.call('GET', path(s)).json()
    assert learning_memory.VERSION == current
    second = h.call('GET', path(s)).json()
    assert second['summary_version'] == first['summary_version'] + 1
    assert second['snapshot_id'] != first['snapshot_id']
    assert h.ctx.store.get('learning_snapshots', first['snapshot_id'])['data']['fingerprint'] == first['fingerprint']
    assert h.ctx.store.all('attempts') == original
    assert h.call('GET', path(s)).json()['snapshot_id'] == second['snapshot_id']


def test_parent_clarification_is_append_only_and_default_remains_unassessed(harness):
    h = harness; s = seed_history(h); original = add_attempt(h, s)
    endpoint = path(s) + '/attempts/first/clarify'
    payload = {'expected_revision': original['revision'], 'transcription': 'The Mongols', 'note': 'Read the photograph with Lucas.'}
    assert h.call('POST', endpoint, json={**payload, 'transcription': ' '}).status_code == 400
    response = h.call('POST', endpoint, key='clarify-once', json=payload)
    assert response.status_code == 200, response.text
    row = response.json()['evidence'][0]
    assert row['first_result'] == 'Unanswered' and row['state'] == 'not_checked'
    assert row['lineage'] == [row['id'], 'first'] and len(response.json()['amendment_history']) == 1
    assert h.ctx.store.get('attempts', 'first') == original
    assert len(h.ctx.store.all('learning_snapshots')) == 1  # Staged/committed metadata cannot create duplicate versions.
    assert h.call('POST', endpoint, key='clarify-once', json=payload).json() == response.json()
    assert h.call('POST', endpoint, json=payload).status_code == 409
    response = h.call('POST', path(s) + f"/attempts/{row['id']}/clarify", json={**payload, 'expected_revision': row['revision'], 'result': 'Correct'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['topics'][0]['state'] == 'independent' and data['topics'][0]['independent_checks'] == 1
    assert data['evidence'][0]['date'] == '2026-09-24' and len(data['amendment_history']) == 2


def test_parent_correction_preserves_assistance_and_concurrent_amendment_has_one_winner(harness):
    h = harness; s = seed_history(h); original = add_attempt(h, s, independence='with_help')
    payload = {'expected_revision': original['revision'], 'transcription': 'The Mongols', 'note': 'Checked the submitted work.', 'result': 'Correct'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: h.call('POST', path(s) + '/attempts/first/clarify', json=payload).status_code, range(2)))
    assert sorted(results) == [200, 409]
    data = h.call('GET', path(s)).json()
    assert data['topics'][0]['state'] == 'needs_help' and data['topics'][0]['independent_checks'] == 0


def test_ownership_bridge_and_test_mode_cannot_mutate_real_memory(harness):
    h = harness; s = seed_history(h); original = add_attempt(h, s)
    h.call('GET', path(s))
    tables = ('attempts', 'reviews', 'learning_snapshots', 'learner_concept_links', 'topics')
    before = {t: copy.deepcopy(h.ctx.store.all(t)) for t in tables}
    token = h.call('POST', '/api/test-mode', json={'enabled': True}).json()['token']
    payload = {'expected_revision': original['revision'], 'transcription': 'Test-only answer', 'note': 'Testing parent clarification.'}
    response = h.client.post(path(s) + '/attempts/first/clarify', headers={'X-Homeschooling-Mode': token}, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['evidence'][0]['first_answer'] == 'Test-only answer'
    assert before == {t: h.ctx.store.all(t) for t in tables}
    assert len(manager(h.ctx).get(token).store.all('learning_snapshots')) == 2
    assert h.call('GET', path(s), role='tutor').status_code == 403
    assert h.call('POST', path(s) + '/attempts/first/clarify', role='tutor', json=payload).status_code == 403
    assert h.call('POST', path(s) + '/link', role='tutor', json={}).status_code == 403
    assert h.call('GET', f"/api/records/learning/999/{s['history']['id']}").status_code == 400
