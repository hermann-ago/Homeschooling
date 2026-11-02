"""Choosing chapters freely and administrative completion never invent evidence."""
from datetime import datetime, timedelta, timezone
import copy
import pytest

from tests.test_activity_engine import engine_lesson, event
from tests.test_lesson_overview import reach_question
from tests.test_tutoring import seed_history
from tutoring.activity_engine import service


def topic_path(seeded, name='genghis'):
    return f"/api/subjects/{seeded['history']['id']}/topics/{seeded[name]['id']}"


def test_explicit_choice_keeps_each_unfinished_session_and_resumes_after_restart(harness):
    s = seed_history(harness)
    body = {'child_id': s['lucas']['id'], 'subject_id': s['history']['id']}
    old = harness.ctx.store.get('tutor_sessions', '2026-09-24-genghis')
    chosen = harness.call('POST', '/api/tutor/sessions/start', json={**body, 'topic_id': s['conquest']['id']})
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()['topic']['topic_id'] == s['conquest']['id']
    assert harness.ctx.store.get('tutor_sessions', old['id']) == old
    harness.restart()
    for tid, sid in ((s['genghis']['id'], old['id']), (s['conquest']['id'], chosen.json()['session_id'])):
        response = harness.call('POST', '/api/tutor/sessions/start', json={**body, 'topic_id': tid})
        assert response.status_code == 200, response.text
        assert response.json()['session_id'] == sid and response.json()['resumed']
    assert len(harness.ctx.store.all('tutor_sessions')) == 2


def test_new_guided_chapter_does_not_force_another_chapters_pending_question(harness, monkeypatch):
    engine, state, s = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    state = event(engine, state, 'save_draft', {'text': 'A saved draft', 'draft_revision': 0})
    preserved = {table: harness.ctx.store.all(table) for table in ('activity_drafts', 'activity_responses')}
    guide = harness.call('POST', '/api/tutor/reader/guide', json={'learner': s['lucas']['id'], 'topic': s['conquest']['id']})
    assert guide.status_code == 200, guide.text
    started = harness.call('POST', '/api/tutor/interactive/start', json={'learner': s['lucas']['id'], 'topic': s['conquest']['id'], 'guide_id': guide.json()['guide_id']})
    assert started.status_code == 200, started.text
    other = engine.state(started.json()['session_id'])
    assert other['active_activity']['kind'] == 'introduce'
    assert not any(a.get('source_action_id') for a in harness.ctx.store.find('lesson_actions', session_id=other['session_id']))
    assert engine.state(state['session_id'])['active_activity']['draft']['text'] == 'A saved draft'
    assert {table: harness.ctx.store.all(table) for table in preserved} == preserved


@pytest.mark.parametrize('adaptive_warmup', [False, True])
def test_new_chapter_opens_on_its_introduction_instead_of_an_older_due_review(harness, monkeypatch, adaptive_warmup):
    h = harness
    _, _, s = engine_lesson(h, monkeypatch)
    with h.ctx.store.transaction() as tx:
        review = tx.insert('reviews', {'id': 'older-chapter-review', 'child_id': s['lucas']['id'],
            'topic_id': s['genghis']['id'], 'concept': 'An older question to revisit', 'status': 'Open',
            'next_due': datetime.now(timezone.utc).date() - timedelta(days=1),
            'next_prompt': 'Finish the last question from the older chapter.'})
    result = h.call('POST', '/api/tutor/reader/guide', json={
        'learner': s['lucas']['id'], 'topic': s['conquest']['id'], 'prepare_voice': False})
    assert result.status_code == 200, result.text
    if adaptive_warmup:
        from tutoring import lesson_context
        original = lesson_context.preparation
        def context(*args, **kwargs):
            return {**original(*args, **kwargs), 'adaptive_warmup': {
                k: review[k] for k in ('id', 'topic_id', 'next_prompt')}}
        monkeypatch.setattr(lesson_context, 'preparation', context)
    before = copy.deepcopy(h.ctx.store.all('reviews'))
    started = h.call('POST', '/api/tutor/interactive/start', json={
        'learner': s['lucas']['id'], 'topic': s['conquest']['id'], 'guide_id': result.json()['guide_id']})
    assert started.status_code == 200, started.text
    state = service(h.ctx).state(started.json()['session_id'])
    assert state['active_activity']['kind'] == 'introduce'
    assert state['playback']['sentence_index'] == 0
    assert all(a['topic_id'] == s['conquest']['id'] and a.get('review_id') != review['id']
               for a in h.ctx.store.find('lesson_actions', session_id=state['session_id']))
    assert h.ctx.store.all('reviews') == before
    h.restart()
    assert service(h.ctx).state(state['session_id'])['active_activity']['kind'] == 'introduce'


def test_prepared_lesson_can_open_with_a_selected_collection_reference(harness, monkeypatch):
    from tests.pdf_fixture import make_pdf
    from tests.test_collections import source, payload
    from tutoring import passages, skills
    h = harness
    _, _, s = engine_lesson(h, monkeypatch)
    subject = s['history']['id']
    url = f'/api/subjects/{subject}/book-collection'
    view = h.call('GET', url).json()
    path = h.add_file(make_pdf([['The owl flew over the quiet field.']]), 'Books/Extra story.pdf')
    body = payload(view)
    body['books'].append(source('extra-story', path, role='reference', position=len(body['books'])))
    response = h.call('PUT', url, json=body)
    assert response.status_code == 200, response.text
    doc = next(b['document_id'] for b in response.json()['books'] if b['path'] == path)
    # A new reference book is set up for page selection but never becomes lessons of its own.
    assert not h.ctx.store.find('topics', subject_id=subject, document_id=doc)
    topic = s['conquest']
    selected = h.call('PUT', f"/api/topics/{topic['id']}/source-pages", json={
        'expected_revision': 0, 'sources': [{'document_id': doc, 'page_start': 1, 'page_end': 1}]})
    assert selected.status_code == 200, selected.text
    package = passages.load(h.ctx, topic)
    script = {'welcome': 'We will read both assigned sources.', 'turns': [
        {'type': 'read', 'first': 0, 'last': len(package['sentences']) - 1},
        {'type': 'read', 'document_id': doc, 'page_start': 1, 'page_end': 1,
         'text': 'The owl flew over the quiet field.'},
        {'type': 'ask', 'purpose': 'discussion', 'prompt': 'Where did the owl fly?', 'response': {'format': 'text'}}],
        'closing': 'We have reached the end of the reading.'}
    imported = h.call('POST', '/api/tutor/reader/guide/import', json={'learner': s['lucas']['id'],
        'topic': topic['id'], 'source_sha256': package['passage_sha256'],
        'expected_skill_version': skills.current(h.ctx.store, subject)['version'],
        'script': script})
    assert imported.status_code == 200, imported.text
    started = h.call('POST', '/api/tutor/interactive/start', json={
        'learner': s['lucas']['id'], 'topic': topic['id'], 'guide_id': imported.json()['guide_id']})
    assert started.status_code == 200, started.text
    state = service(h.ctx).state(started.json()['session_id'])
    assert state['active_activity']['kind'] == 'introduce'
    assert any(a['activity_kind'] == 'read_source' and any(r.get('document_id') == doc for r in a['source_refs'])
               for a in h.ctx.store.find('lesson_actions', session_id=state['session_id']))
    # Collection-only references are usable; the same file classified as a key
    # still cannot enter learner-facing activity content.
    latest = h.call('GET', url).json()
    key_edit = payload(latest)
    target = next(b for b in key_edit['books'] if b['document_id'] == doc)
    key_edit['books'].append({'key': 'main-original', 'document_id': topic['document_id'],
        'role': 'combined', 'edition': '', 'position': len(key_edit['books']), 'is_main': True,
        'companion_key': None, 'answer_for_key': None})
    target.update(role='answer_key', answer_for_key='main-original')
    changed = h.call('PUT', url, json=key_edit)
    assert changed.status_code == 200, changed.text
    from tutoring.service import TutorError
    with pytest.raises(TutorError):
        service(h.ctx)._validate_sources(h.ctx.store.get('tutor_sessions', state['session_id']),
            {'source_refs': [{'document_id': doc, 'page': 1}]})


def test_manual_check_closes_session_keeps_capture_and_is_durable(harness, monkeypatch):
    engine, state, s = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    state = event(engine, state, 'save_draft', {'text': 'Still writing', 'draft_revision': 0})
    state = event(engine, state, 'submit_response', {'response_id': 'unconfirmed-answer', 'text': 'They joined', 'method': 'dictation'})
    preserved = {table: harness.ctx.store.all(table) for table in ('activity_drafts', 'activity_responses', 'attempts', 'reviews', 'lesson_actions')}
    checked = harness.call('POST', topic_path(s) + '/toggle-complete', key='manual-check')
    assert checked.status_code == 200, checked.text
    assert checked.json()['completed'] and checked.json()['completion_source'] == 'manual'
    session = harness.ctx.store.get('tutor_sessions', state['session_id'])
    assert session['status'] == 'completed' and session['completion_source'] == 'manual'
    assert session['completion_summary']['understanding'] == 'Not assessed'
    assert session['completion_summary']['pending_work']
    assert engine.state(state['session_id'])['active_activity'] is None
    assert harness.ctx.tutor.reader_state(state['session_id']) == 'closed'
    assert all(c['status'] != 'open' for c in harness.ctx.store.find('checkpoints', session_id=state['session_id']))
    assert {table: harness.ctx.store.all(table) for table in preserved} == preserved
    assert len(harness.ctx.store.all('topic_completion_events')) == 1
    assert harness.call('POST', topic_path(s) + '/toggle-complete', key='manual-check').json() == checked.json()
    harness.restart()
    assert harness.ctx.store.get('tutor_sessions', state['session_id'])['completion_source'] == 'manual'
    assert len(harness.ctx.store.all('topic_completion_events')) == 1
    assert service(harness.ctx).state(state['session_id'])['learning_summary']['answers']['checked'] == 0
    unchecked = harness.call('POST', topic_path(s) + '/toggle-complete')
    assert not unchecked.json()['completed'] and unchecked.json()['completion_source'] is None
    assert harness.ctx.store.get('tutor_sessions', state['session_id'])['status'] == 'completed'
    assert {table: harness.ctx.store.all(table) for table in preserved} == preserved


def test_manual_completion_without_session_is_visible_in_records_and_repeat_stays_open(harness):
    s = seed_history(harness)
    completed = harness.call('PUT', topic_path(s, 'conquest'), json={'completed': True})
    assert completed.status_code == 200, completed.text
    rows = harness.call('GET', '/api/records', params={'view': 'lessons'}).json()['rows']
    row = next(r for r in rows if r['topic'] == s['conquest']['title'])
    assert row['status'] == 'Completed by user' and row['details']['Completion source'] == 'manual'
    assert not harness.ctx.store.find('tutor_sessions', topic_id=s['conquest']['id'])
    assert not harness.ctx.store.all('attempts')
    body = {'child_id': s['lucas']['id'], 'subject_id': s['history']['id'], 'topic_id': s['conquest']['id']}
    repeated = harness.call('POST', '/api/tutor/sessions/start', json=body).json()['session_id']
    assert harness.ctx.store.get('tutor_sessions', repeated)['session_type'] == 'repeat'
    assert harness.call('PUT', topic_path(s, 'conquest'), json={'title': 'Edited chapter'}).status_code == 200
    harness.restart()
    assert harness.ctx.store.get('tutor_sessions', repeated)['status'] == 'active'


def test_legacy_reconciliation_closes_only_pre_completion_sessions(harness):
    s = seed_history(harness)
    when = datetime.now(timezone.utc)
    with harness.ctx.store.transaction() as tx:
        tx.update('topics', s['genghis']['id'], {'completed': True, 'completed_at': when})
        for sid, typ, started in [('intentional-repeat', 'repeat', when - timedelta(days=1)), ('newer-session', 'lesson', when + timedelta(seconds=1))]:
            tx.insert('tutor_sessions', {'id': sid, 'child_id': s['lucas']['id'], 'subject_id': s['history']['id'], 'topic_id': s['genghis']['id'],
                'status': 'active', 'session_type': typ, 'started_at': started})
    harness.restart()
    old = harness.ctx.store.get('tutor_sessions', '2026-09-24-genghis')
    assert old['status'] == 'completed' and old['completion_source'] == 'topic_completion'
    assert harness.ctx.store.get('topics', s['genghis']['id'])['completion_source'] is None
    for sid in ('intentional-repeat', 'newer-session'):
        assert harness.ctx.store.get('tutor_sessions', sid)['status'] == 'active'
    harness.restart()
    assert harness.ctx.store.get('tutor_sessions', old['id']) == old


def test_checklist_completion_and_test_mode_use_the_same_manual_completion(harness):
    from datetime import date
    from tests.test_test_mode import call, enter
    from services.test_mode import manager
    s = seed_history(harness)
    with harness.ctx.store.transaction() as tx:
        slot = tx.insert('scheduled_slots', {'child_id': s['lucas']['id'], 'subject_id': s['history']['id'],
            'topic_id': s['genghis']['id'], 'date': date.today(), 'time_start': '09:00', 'time_end': '09:30'})
    before = {name: harness.ctx.store.all(name) for name in ('topics', 'tutor_sessions', 'topic_completion_events', 'checkpoints')}
    token = enter(harness)
    checked = call(harness, 'POST', topic_path(s) + '/toggle-complete', mode=token)
    assert checked.status_code == 200, checked.text
    test_db = manager(harness.ctx).get(token).store
    assert test_db.get('tutor_sessions', '2026-09-24-genghis')['completion_source'] == 'manual'
    assert test_db.all('topic_completion_events')
    assert {name: harness.ctx.store.all(name) for name in before} == before
    response = call(harness, 'POST', f"/api/checklist/complete/{slot['id']}", mode='live')
    assert response.status_code == 201, response.text
    assert harness.ctx.store.get('tutor_sessions', '2026-09-24-genghis')['status'] == 'completed'
    assert harness.ctx.store.get('topics', s['genghis']['id'])['completion_source'] == 'manual'
    assert not harness.ctx.store.all('attempts')


def test_bulk_completion_closes_only_sessions_in_the_selected_book(harness):
    from tests.test_curriculum_book_identity import seed
    subject, docs, topics = seed(harness)
    with harness.ctx.store.transaction() as tx:
        for topic in topics:
            tx.insert('tutor_sessions', {'id': f"session-{topic['id']}", 'topic_id': topic['id'],
                'child_id': subject['child_id'], 'subject_id': subject['id'], 'status': 'unfinished'})
    response = harness.call('POST', f"/api/subjects/{subject['id']}/topics/{topics[-1]['id']}/complete-previous")
    assert response.status_code == 200, response.text
    assert [harness.ctx.store.get('tutor_sessions', f"session-{t['id']}")['status'] for t in topics] == ['unfinished', 'unfinished', 'completed', 'completed']
    assert len(harness.ctx.store.all('topic_completion_events')) == 2


def test_manual_completion_preserves_assessed_answers_and_repeat_can_start_beside_another_lesson(harness, monkeypatch):
    from tests.test_interactive import correct
    from tutoring import interactive
    engine, state, s = engine_lesson(harness, monkeypatch)
    state = reach_question(engine, state)
    monkeypatch.setattr(interactive, 'gemini_turn', correct)
    state = event(engine, state, 'submit_response', {'response_id': 'assessed-answer', 'text': 'He united them.', 'assess_after_save': True})
    before = {table: harness.ctx.store.all(table) for table in ('attempts', 'activity_responses', 'lesson_dialogue')}
    assert before['attempts']
    assert harness.call('PUT', topic_path(s), json={'completed': True}).status_code == 200
    assert {table: harness.ctx.store.all(table) for table in before} == before
    other = harness.call('POST', '/api/tutor/sessions/start', json={'child_id': s['lucas']['id'],
        'subject_id': s['history']['id'], 'topic_id': s['conquest']['id']}).json()['session_id']
    other_session = harness.ctx.store.get('tutor_sessions', other)
    repeated = engine.repeat(state['session_id'], 'repeat-after-manual-completion', from_beginning=True)
    assert repeated['active_activity']['kind'] == 'introduce'
    assert repeated['session_id'] not in (state['session_id'], other)
    assert harness.ctx.store.get('tutor_sessions', other) == other_session
    assert {table: harness.ctx.store.all(table) for table in before} == before
    harness.restart()
    assert harness.ctx.store.get('tutor_sessions', repeated['session_id'])['status'] == 'active'
