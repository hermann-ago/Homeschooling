"""Reviewed source retrieval, learner continuity and immutable running lessons."""
import copy
from datetime import date

from tests.test_map_review import mapped, read, edit
from tests.test_subject_analysis import PRIVATE
from tutoring import guide, interactive, lesson_context, passages


def select(h, mid):
    m = read(h, mid)
    response = h.call('POST', f'/api/subject-maps/{mid}/select', json={
        'expected_revision': m['teaching_selection']['selection_number'], 'expected_review_revision': m['review_revision']})
    assert response.status_code == 200, response.text
    return response.json()


def prepare_sources(mapped):
    h, mid, sent, base, _ = mapped
    subject_id = int(base.split('/')[3]); subject = h.ctx.store.get('subjects', subject_id)
    m = read(h, mid)
    for c in m['concepts']:
        assert edit(h, mid, c, status='approved', changes={}).status_code == 200
    assert edit(h, mid, m['connections'][0], kind='connection', status='approved', changes={}).status_code == 200
    select(h, mid)
    main = m['concepts'][0]; prior = m['concepts'][1]
    with h.ctx.store.transaction() as tx:
        earlier = tx.insert('topics', {'subject_id': subject_id, 'document_id': prior['document_id'], 'title': 'Earlier trade',
            'page_start': 1, 'page_end': 1, 'chapter_order': 1, 'completed': True})
        current = tx.insert('topics', {'subject_id': subject_id, 'document_id': main['document_id'], 'title': 'Mongol Empire',
            'page_start': 1, 'page_end': 1, 'chapter_order': 2})
        future = tx.insert('topics', {'subject_id': subject_id, 'document_id': prior['document_id'], 'title': 'Future trade',
            'page_start': 1, 'page_end': 1, 'chapter_order': 3, 'completed': True})
        tx.insert('tutor_sessions', {'id': 'old-trade', 'child_id': subject['child_id'], 'subject_id': subject_id,
            'topic_id': earlier['id'], 'date': date(2026, 9, 1), 'status': 'completed'})
        tx.insert('attempts', {'id': 'older-difficulty', 'session_id': 'old-trade', 'child_id': subject['child_id'], 'topic_id': earlier['id'],
            'question_ref': 'Trade recall', 'first_answer': 'Not sure', 'first_result': 'Not yet', 'help_given': 'Look at the trade map', 'independence': 'with_help'})
        tx.insert('reviews', {'id': 'trade-review', 'child_id': subject['child_id'], 'topic_id': earlier['id'], 'concept': prior['title'],
            'status': 'Open', 'next_due': date(2026, 9, 3), 'next_prompt': 'What connected China and Europe?'})
    return h, mid, subject, h.ctx.store.get('topics', current['id']), h.ctx.store.get('topics', earlier['id']), future, sent


def test_map_selection_requires_real_parent_review_and_freezes_checked_portions(mapped):
    h, mid, sent, _, _ = mapped
    response = h.call('POST', f'/api/subject-maps/{mid}/select', json={'expected_revision': 0, 'expected_review_revision': 0})
    assert response.status_code == 400 and 'approve' in response.text
    m = read(h, mid); concept = m['concepts'][0]
    assert edit(h, mid, concept, status='approved', changes={}).status_code == 200
    chosen = select(h, mid)['teaching_selection']
    row = h.ctx.store.get('subject_map_selections', chosen['id'])
    assert len(row['data']['concepts']) == 1 and not row['data']['connections']
    assert PRIVATE not in str(row) and 'private_answers' not in row['data']
    assert edit(h, mid, concept).status_code == 200
    assert not read(h, mid)['teaching_selection']['active']
    assert h.ctx.store.get('subject_map_selections', chosen['id']) == row
    second = select(h, mid)['teaching_selection']
    assert second['selection_number'] == 2 and second['active']
    assert len(sent) == 4
    h.restart()
    assert read(h, mid)['teaching_selection'] == second
    assert h.call('POST', f'/api/subject-maps/{mid}/select', role='tutor', json={'expected_revision': 2, 'expected_review_revision': 2}).status_code == 403


def test_retrieval_uses_earlier_source_and_observed_difficulty_but_not_future_assumptions(mapped):
    h, _, subject, topic, earlier, future, sent = prepare_sources(mapped)
    package = passages.load(h.ctx, topic)
    packet = lesson_context.preparation(h.ctx, subject['child_id'], topic, package)
    sources = packet['subject_sources']
    assert len(sources['current_concepts']) == len(sources['earlier_concepts']) == len(sources['connections']) == 1
    assert sources['earlier_concepts'][0]['topic_id'] == earlier['id']
    assert sources['earlier_concepts'][0]['topic_id'] != future['id']
    assert any(o['state'] == 'needs_help' for o in packet['learning_memory']['observations'])
    assert packet['adaptive_warmup']['id'] == 'trade-review'
    assert PRIVATE not in str(packet) and len(sent) == 4
    # If only the future chapter has been seen, the connection cannot imply past learning.
    with h.ctx.store.transaction() as tx:
        tx.update('topics', earlier['id'], {'chapter_order': 4})
    sources = lesson_context.packet(h.ctx, topic, package)
    assert not sources['earlier_concepts'] and not sources['connections']


def test_source_boundary_or_changed_edition_excludes_unusable_context(mapped):
    h, _, subject, topic, _, _, _ = prepare_sources(mapped)
    clipped = {'sentences': [{'text': 'Kublai Khan became emperor.'}]}
    assert not lesson_context.packet(h.ctx, topic, clipped)['current_concepts']
    with h.ctx.store.transaction() as tx:
        tx.update('documents', topic['document_id'], {'sha256': 'changed-original'})
    assert not lesson_context.status(h.ctx, subject['id'])['active']
    assert not lesson_context.packet(h.ctx, topic, clipped)['current_concepts']


def test_new_guide_and_running_tutor_pin_source_context_and_refresh_only_saved_recall(mapped, monkeypatch):
    h, mid, subject, topic, _, _, sent = prepare_sources(mapped)
    from tutoring import books, passages
    original_generate=h.ctx.ai.generate
    def source_inventory(*args,**kwargs):
        from tutoring.script_review import Review
        if isinstance(kwargs.get('schema'), type) and issubclass(kwargs['schema'], Review):return {'findings':[]}
        if kwargs.get('schema') is books.ScanResult:
            first,last=passages.pdf_range(topic)
            return {'pages':[{'page':p,'text':'','native_reliable':True,'student_safe':True}
                             for p in range(first,last+1)],'exercises':[],'answers':[]}
        return original_generate(*args,**kwargs)
    monkeypatch.setattr(h.ctx.ai,'generate',source_inventory)
    prompts = []
    def write(text, models, **kwargs):
        prompts.append(text)
        c = read(h, mid)['concepts'][0]['id']
        return {'mode': 'expand', 'segments': [{'type': 'intro', 'text': 'Let us connect our earlier reading.'},
            {'type': 'read', 'from': 0, 'to': 99}, {'type': 'action', 'text': 'Explain one connection.', 'action_kind': 'answer', 'concept_ids': [c, 'invented']}]}, 'test-model'
    monkeypatch.setattr(guide, 'write_plan', write)
    payload = {'learner': subject['child_id'], 'topic': topic['id']}
    response = h.call('POST', '/api/tutor/reader/guide', json=payload)
    assert response.status_code == 200, response.text
    saved = response.json(); source_id = read(h, mid)['concepts'][0]['id']
    assert saved['actions'][0]['concept_ids'] == [source_id]
    assert 'older-difficulty' in prompts[0] and 'Earlier trade' in prompts[0] and PRIVATE not in prompts[0]
    assert saved['adaptive_context']['fresh']
    original_guide = copy.deepcopy(h.ctx.store.get('guides', saved['guide_id']))
    with h.ctx.store.transaction() as tx:
        tx.update('reviews', 'trade-review', {'next_prompt': 'Recall the earlier trade routes.'})
    refreshed = h.call('POST', '/api/tutor/reader/guide', json=payload).json()
    assert refreshed['guide_id'] == saved['guide_id'] and not refreshed['adaptive_context']['fresh']
    assert refreshed['adaptive_context']['warmup']['next_prompt'] == 'Recall the earlier trade routes.'
    assert len(prompts) == 1 and h.ctx.store.get('guides', saved['guide_id']) == original_guide
    started = h.call('POST', '/api/tutor/interactive/start', json={**payload, 'guide_id': saved['guide_id']})
    assert started.status_code == 200, started.text
    state = started.json(); playback = h.ctx.store.get('lesson_playback', state['session_id'])
    assert len([a for a in state['actions'] if a.get('review_id')]) == 1
    assert state['playback']['action_id'] == 'warmup-trade-review'
    assert playback['context_snapshot']['started_with']['adaptive_warmup']['next_prompt'] == 'Recall the earlier trade routes.'
    assert edit(h, mid, read(h, mid)['concepts'][0]).status_code == 200
    select(h, mid)
    resumed = h.call('POST', '/api/tutor/interactive/start', json={**payload, 'guide_id': saved['guide_id']}).json()
    assert resumed['playback']['context_snapshot'] == playback['context_snapshot']
    assert resumed['playback']['action_id'] == 'warmup-trade-review'
    assert h.ctx.store.get('guides', saved['guide_id']) == original_guide and len(sent) == 4
    turns = []
    def assess(prompt, images, models):
        turns.append(prompt)
        return {'feedback': 'You explained the earlier connection.', 'result': 'Correct', 'transcription': 'Trade routes.',
            'help': None, 'assistance_used': False, 'follow_up': None, 'ready_to_continue': True, 'concept': 'Trade routes'}
    monkeypatch.setattr(interactive, 'gemini_turn', assess)
    answered = h.call('POST', f"/api/tutor/sessions/{state['session_id']}/answer", json={
        'expected_revision': resumed['revision'], 'action_id': 'warmup-trade-review', 'message_id': 'recall-answer', 'text': 'Trade routes.'})
    assert answered.status_code == 200, answered.text
    assert 'pinned_subject_sources' in turns[0] and 'current observed evidence' in turns[0] and PRIVATE not in turns[0]
    assert h.ctx.store.get('lesson_playback', state['session_id'])['context_snapshot'] == playback['context_snapshot']
    h.restart()
    assert h.call('GET', f"/api/tutor/sessions/{state['session_id']}/conversation").json()['playback']['context_snapshot'] == playback['context_snapshot']
