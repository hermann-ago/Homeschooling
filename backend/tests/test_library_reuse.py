"""Book teaching survives its first reader and never shares learner evidence."""
import io
import json

import pytest
from pypdf import PdfReader

from tests.pdf_fixture import make_pdf
from tests.test_library import child, upload, enroll, index, get_book
from tutoring import books, guide, library_materials


@pytest.fixture
def family(harness, monkeypatch):
    h = harness
    first, second = child(h, "First reader private name"), child(h, "Future reader private name")
    pdf = make_pdf([["The first idea", "People exchange things because each expects to benefit from the exchange."]])
    assert upload(h, data=pdf).status_code == 200
    def scan(ctx, data, role, start, end):
        reader = PdfReader(io.BytesIO(data))
        return {"pages": [{"page": n, "text": reader.pages[n-1].extract_text(), "native_reliable": True,
            "student_safe": True, "teacher_material": False, "headings": ["The first idea"]} for n in range(start, end+1)],
            "exercises": [], "answers": []}
    monkeypatch.setattr(books, "scan_unit", scan)
    readings = []
    for kid in (first, second):
        enroll(h, kid["id"])
        reading = index(h, kid["id"])
        assert reading["job"]["status"] == "ready", reading
        readings.append(reading)
    prompts = []
    def write(prompt, *args, **kw):
        prompts.append(prompt)
        return {"mode": "expand", "segments": [
            {"type": "intro", "text": "Let us explore this idea together."}, {"type": "read", "from": 0, "to": 999},
            {"type": "explain", "text": "An exchange is when people trade things."},
            {"type": "activity", "activity_kind": "ask_question", "content": {
                "prompt": "Who expects to benefit?", "choices": [{"id": "both", "label": "Both people"}, {"id": "none", "label": "Neither person"}],
                "response_modes": ["choice"], "answer_format": "single_choice", "require_reasoning": False}},
            {"type": "recap", "text": "Each person expects to benefit."}]}, "synthetic-shared-writer"
    monkeypatch.setattr(guide, "write_plan", write)
    monkeypatch.setattr(h.ctx.ai, "generate", lambda *a, **kw: {"findings": []})
    return h, first, second, readings, prompts


def make_guide(h, kid, reading, **extra):
    response = h.call("POST", "/api/tutor/reader/guide", json={"learner": kid["id"], "topic": reading["topics"][0]["id"], "prepare_voice": False, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_explanations_quiz_and_review_generate_once_for_future_children(family, monkeypatch):
    h, first, second, readings, prompts = family
    with h.ctx.store.transaction() as tx:
        tx.insert('preferences', {'id': 'first-private', 'child_id': first['id'], 'key': 'teaching_style', 'value': 'PRIVATE-FIRST-LEARNER-NOTE'})
    made = make_guide(h, first, readings[0])
    assert made['current'] and made['script_review']['status'] == 'approved'
    assert len(prompts) == 1 and first['name'] not in prompts[0] and 'PRIVATE-FIRST-LEARNER-NOTE' not in prompts[0]
    material = next(r for r in h.ctx.store.all('library_materials') if r['kind'] == 'guided_lesson')
    archived = json.dumps(material['data'])
    assert first['name'] not in archived and 'PRIVATE-FIRST-LEARNER-NOTE' not in archived
    assert not any(key in material['data']['context'] for key in ('preferences', 'resume', 'recent_sessions', 'pending_actions', 'learning_memory', 'workbook_fingerprint'))
    assert material['file_path'].startswith('Family Library/library-02/Lesson Content/')
    assert all(part['content'].get('prompt') for part in made['activities'] if part['kind'] == 'ask_question')
    monkeypatch.setattr(guide, 'write_plan', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Must reuse the saved book lesson')))
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('No repeat paid review')))
    before = len(h.ctx.store.all('guides'))
    estimate = make_guide(h, second, readings[1], dry_run=True)
    assert estimate['reused_book_material'] and estimate['estimated_cost_usd'] == 0
    assert len(h.ctx.store.all('guides')) == before
    reused = make_guide(h, second, readings[1])
    assert reused['reused_book_material'] and reused['current']
    assert reused['guide_id'] != made['guide_id'] and reused['sentences'] == made['sentences']
    assert reused['script_review']['method'] == 'shared_book_review' and reused['script_review']['status'] == 'approved'
    assert not h.ctx.store.all('attempts') and not h.ctx.store.all('tutor_sessions')
    # Binding still starts an ordinary, independent session with the engine's normal checks.
    started = h.call('POST', '/api/tutor/interactive/start', json={'learner': second['id'],
        'topic': readings[1]['topics'][0]['id'], 'guide_id': reused['guide_id']})
    assert started.status_code == 200, started.text
    assert get_book(h, learner=second['id'])['readings'][0]['completed_topics'] == 0


def test_first_shared_lesson_can_be_estimated_without_private_learning_context_or_generation(family):
    h, first, _, readings, prompts = family
    estimate = make_guide(h, first, readings[0], dry_run=True)
    assert not estimate['reused'] and estimate['estimated_cost_usd'] >= 0
    assert estimate['source_context']['observations'] == 0 and estimate['source_context']['warmup'] is None
    assert not prompts and not h.ctx.store.all('guides')


def test_codex_export_bypasses_cached_guide_without_paid_generation_or_student_changes(family, monkeypatch):
    import base64
    h, first, _, readings, prompts = family
    made = make_guide(h, first, readings[0])
    before = {table: h.ctx.store.all(table) for table in ('guides', 'attempts', 'tutor_sessions', 'topics', 'lesson_script_reviews')}
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **kw: pytest.fail('Export cannot call a paid model'))
    exported = h.call('POST', '/api/tutor/reader/guide', json={'learner': first['id'],
        'topic': readings[0]['topics'][0]['id'], 'export_inputs': True, 'dry_run': True, 'prepare_voice': False})
    assert exported.status_code == 200, exported.text
    packet = exported.json()
    assert not packet['paid_generation'] and packet['package']['passage_sha256']
    assert made['guide_id']
    assert base64.b64decode(packet['source_pdf_base64']).startswith(b'%PDF')
    assert 'BOOK READING QUESTION POLICY' in packet['prompt']
    assert packet['context']['book_question_policy'] == 'book-choice-2'
    assert len(prompts) == 1
    assert {table: h.ctx.store.all(table) for table in before} == before
    assert h.call('POST', '/api/tutor/reader/guide', json={'learner': first['id'],
        'topic': readings[0]['topics'][0]['id'], 'export_inputs': True}).status_code == 422


def test_canonical_reviewed_import_cannot_bypass_book_question_policy(family):
    from tutoring import passages, skills
    h, first, _, readings, _ = family
    topic = h.ctx.store.get('topics', readings[0]['topics'][0]['id'])
    source = passages.load(h.ctx, topic)
    subject = h.ctx.store.get('subjects', topic['subject_id'])
    result = h.call('POST', '/api/tutor/reader/guide/import', json={'learner': first['id'], 'topic': topic['id'],
        'source_sha256': source['passage_sha256'], 'expected_skill_version': skills.packet(h.ctx.store, subject)['version'],
        'plan': {'mode': 'expand', 'segments': [{'type': 'intro', 'text': 'Let us read.'},
            {'type': 'read', 'from': 0, 'to': 999}, {'type': 'action', 'text': 'Write an explanation.', 'action_kind': 'answer'}]}})
    assert result.status_code == 502 and 'single-choice' in result.text
    assert not h.ctx.store.all('guides')


def test_voice_guard_rejects_legacy_book_writing_before_any_provider_call(family, monkeypatch):
    import copy
    from tutoring import elevenlabs_audio, narration
    h, first, _, readings, _ = family
    made = make_guide(h, first, readings[0])
    old = copy.deepcopy(made)
    question = next(a for a in old['activities'] if a['kind'] == 'ask_question')
    question['kind'] = 'request_book_work'
    question['content'].update(answer_format='text', response_modes=['text'])
    monkeypatch.setattr(elevenlabs_audio, 'generate', lambda *a, **kw: pytest.fail('Do not purchase voice for an invalid book lesson'))
    topic = h.ctx.store.get('topics', readings[0]['topics'][0]['id'])
    with pytest.raises(ValueError, match='single-choice'):
        narration.generate(h.ctx, topic, old, provider='elevenlabs')


def test_materials_survive_restart_and_deleting_the_first_child(family, monkeypatch):
    h, first, second, readings, prompts = family
    made = make_guide(h, first, readings[0])
    with h.ctx.store.transaction() as tx:
        tx.delete('children', first['id'])
    assert not h.ctx.store.get('guides', made['guide_id'])
    h.restart()
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Archived source teaching must survive its first child')))
    monkeypatch.setattr(guide, 'write_plan', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('No new generation')))
    reused = make_guide(h, second, readings[1])
    assert reused['reused_book_material'] and reused['sentences'] == made['sentences']
    assert reused['script_review']['status'] == 'approved'
    assert get_book(h)['shared_preparation']['guided_lesson'] == 1


@pytest.mark.parametrize('kind,result', [('quiz', [{'question': 'Why trade?', 'choices': ['A. Benefit', 'B. Nothing'], 'answer': 'A'}]),
    ('audio', 'Both expect a benefit.'), ('terms', [{'term': 'exchange', 'definition': 'A trade.'}]), ('explain', 'People trade things.')])
def test_all_practice_material_is_shared_by_edition_range_language_and_input(family, monkeypatch, kind, result):
    from services import ai_enrichment
    h, first, second, readings, _ = family
    calls = []
    monkeypatch.setattr(ai_enrichment, 'generate_content', lambda *a, **kw: calls.append(a) or result)
    def request(reading, language='en', source='People exchange things because each expects to benefit.'):
        response = h.call('POST', '/api/canvas/ai-content/generate', json={'topic_id': reading['topics'][0]['id'],
            'page_start': 1, 'page_end': 1, 'content_type': kind, 'source_text': source, 'language': language})
        assert response.status_code == 200, response.text
        return response.json()
    original = request(readings[0]); reused = request(readings[1])
    assert not original['from_cache'] and reused['from_cache'] and len(calls) == 1
    assert reused['content'] == original['content'] and reused['topic_id'] != original['topic_id']
    paths = {r['content_path'] for r in h.ctx.store.all('enrichment')}
    assert len(paths) == 1 and next(iter(paths)).startswith('Family Library/library-02/')
    assert not request(readings[1], language='pt')['from_cache'] and len(calls) == 2
    assert not request(readings[1], source='A different source passage.')['from_cache'] and len(calls) == 3
    assert not h.ctx.store.all('attempts')


def test_book_instructions_are_shared_versioned_and_invalidate_future_scripts(family):
    h, first, second, readings, prompts = family
    made = make_guide(h, first, readings[0])
    path = '/api/library/books/library-02/teaching-skill'
    packet = h.call('GET', path).json()
    saved = h.call('PUT', path, json={'content': packet['content']+'\nUse a trade in fruit as an example.', 'expected_version': packet['version']})
    assert saved.status_code == 200, saved.text
    assert saved.json()['file_path'].startswith('Family Library/library-02/Teaching Skill/')
    assert h.call('PUT', path, json={'content': 'Stale edit', 'expected_version': packet['version']}).status_code == 409
    for reading in readings:
        skill = h.call('GET', f"/api/subjects/{reading['subject_id']}/teaching-skill").json()
        assert skill['content'] == saved.json()['content']
    newer = make_guide(h, second, readings[1])
    assert not newer.get('reused_book_material') and len(prompts) == 2
    assert len([r for r in h.ctx.store.all('library_materials') if r['kind'] == 'guided_lesson']) == 2
    assert h.ctx.store.get('guides', made['guide_id'])  # Older materials and pinned threads are preserved.


def test_parent_topic_boundaries_are_reused_without_copying_completion(family):
    h, first, second, readings, _ = family
    topic = readings[0]['topics'][0]
    changed = h.call('PUT', f"/api/subjects/{readings[0]['subject_id']}/topics/{topic['id']}", json={'title': 'Parent-reviewed section', 'start_at': None, 'stop_before': None})
    assert changed.status_code == 200, changed.text
    future = child(h, 'A later child')
    enroll(h, future['id']); reading = index(h, future['id'])
    assert reading['topics'][0]['title'] == 'Parent-reviewed section'
    assert not reading['topics'][0]['completed']
    assert h.ctx.store.all('book_navigation')[0]['data']['chapters'][0]['title'] == 'Parent-reviewed section'


def test_narration_is_visible_to_other_children_and_survives_the_original_reader(family):
    from tests.test_ai_costs import enable_voice, audio_response
    from tutoring.narration import generate
    h, first, second, readings, _ = family
    made = make_guide(h, first, readings[0]); reused = make_guide(h, second, readings[1])
    requests = []
    enable_voice(h, lambda request: requests.append(request) or audio_response())
    first_topic = h.ctx.store.get('topics', readings[0]['topics'][0]['id'])
    second_topic = h.ctx.store.get('topics', readings[1]['topics'][0]['id'])
    recorded = generate(h.ctx, first_topic, made)
    count = len(requests)
    assert count > 0
    assert generate(h.ctx, second_topic, reused)['reused'] and len(requests) == count
    manifest = h.call('GET', f"/api/tutor/audio/{recorded['track_id']}/manifest")
    assert manifest.status_code == 200, manifest.text
    archive = next(r for r in h.ctx.store.all('library_materials') if r['kind'] == 'narration')
    assert archive['data']['track']['manifest_path'].startswith('Family Library/library-02/Audio/')
    assert 'topic_id' not in archive['data']['track']
    visible = h.ctx.tutor.audio_tracks(second_topic, reused)
    assert any(t['track_id'] == recorded['track_id'] and t['synchronized'] for t in visible)
    with h.ctx.store.transaction() as tx:
        tx.delete('children', first['id'])
    assert h.ctx.store.get('audio_tracks', recorded['track_id']) is None
    # No provider request or regeneration is needed for the future reader's controls.
    visible = h.ctx.tutor.audio_tracks(second_topic, reused)
    assert any(t['track_id'] == recorded['track_id'] and t['synchronized'] for t in visible)
    assert h.call('GET', f"/api/tutor/audio/{recorded['track_id']}/manifest").status_code == 200
    assert h.call('GET', f"/api/tutor/audio/{recorded['track_id']}/parts/0").status_code == 200
    assert len(requests) == count


def test_failed_book_review_is_preserved_and_a_later_approval_is_shared(family, monkeypatch):
    from tutoring import script_review
    h, first, second, readings, _ = family
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **kw: (_ for _ in ()).throw(ValueError('Synthetic review interruption')))
    made = make_guide(h, first, readings[0])
    assert made['script_review']['status'] == 'failed'
    reused = make_guide(h, second, readings[1])
    assert reused['reused_book_material'] and reused['script_review']['status'] == 'failed'
    second_row = h.ctx.store.get('guides', reused['guide_id'])
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **kw: {'findings': []})
    script_review.run(h.ctx, second_row, retry=True)
    latest = library_materials.latest(h.ctx.store, second_row['context_snapshot']['library_material_key'])
    assert latest['data']['review']['status'] == 'approved'
    future = child(h, 'Next year reader'); enroll(h, future['id']); future_reading = index(h, future['id'])
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('No repeated review')))
    future_guide = make_guide(h, future, future_reading)
    assert future_guide['reused_book_material'] and future_guide['script_review']['status'] == 'approved'


def test_personal_feedback_audio_is_not_archived_as_shared_book_content(family):
    from tests.test_ai_costs import enable_voice, audio_response
    from tutoring import passages
    from tutoring.narration import generate
    h, first, _, readings, _ = family
    enable_voice(h, lambda request: audio_response())
    topic = h.ctx.store.get('topics', readings[0]['topics'][0]['id'])
    feedback = 'Your private first answer and follow-up are saved for you.'
    audio = generate(h.ctx, topic, {'passage_sha256': passages.passage_sha256(feedback),
        'sentences': passages.split_sentences(feedback)}, purpose='feedback')
    assert not h.ctx.store.find('library_materials', kind='narration')
    track = h.ctx.store.get('audio_tracks', audio['track_id'])
    assert '/Extra Reading/' in track['manifest_path'] and not track['manifest_path'].startswith('Family Library/')


def test_checked_reading_text_is_shared_without_the_reviewers_private_note(family):
    from tutoring import passages
    h, first, second, readings, _ = family
    original = h.ctx.store.get('topics', readings[0]['topics'][0]['id'])
    other = h.ctx.store.get('topics', readings[1]['topics'][0]['id'])
    text = passages.load(h.ctx, original)['passage']
    response = h.call('POST', f"/api/tutor/passages/{original['id']}/review", json={
        'reviewed_pdf_pages': [1], 'passage': text, 'notes': 'PRIVATE-REVIEWER-NOTE about the first reader'})
    assert response.status_code == 200, response.text
    shared = passages.load(h.ctx, other)
    assert shared['status'] == 'verified' and shared['passage'] == text
    archive = next(r for r in h.ctx.store.all('library_materials') if r['kind'] == 'source_passage')
    assert 'PRIVATE-REVIEWER-NOTE' not in json.dumps(archive['data'])
    assert 'topic_id' not in archive['data']
    with h.ctx.store.transaction() as tx:
        tx.delete('children', first['id'])
    assert passages.load(h.ctx, other)['status'] == 'verified'


def test_two_children_preparing_at_once_do_not_duplicate_book_generation(family):
    from concurrent.futures import ThreadPoolExecutor
    h, first, second, readings, prompts = family
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: make_guide(h, *pair), [(first, readings[0]), (second, readings[1])]))
    assert len(prompts) == 1
    assert results[0]['sentences'] == results[1]['sentences']
    assert sum(bool(r.get('reused_book_material')) for r in results) == 1


def test_unavailable_shared_archive_does_not_trigger_another_paid_generation(family):
    h, first, second, readings, prompts = family
    make_guide(h, first, readings[0])
    material = next(r for r in h.ctx.store.all('library_materials') if r['kind'] == 'guided_lesson')
    (h.drive / material['file_path']).unlink()
    response = h.call('POST', '/api/tutor/reader/guide', json={'learner': second['id'], 'topic': readings[1]['topics'][0]['id'], 'prepare_voice': False})
    assert response.status_code in (404, 503), response.text
    assert len(prompts) == 1


def test_retired_full_book_scanner_cannot_be_called(harness):
    with pytest.raises(ValueError, match='retired'):
        books.scan_unit(harness.ctx, b'', 'textbook', 1, 8)
