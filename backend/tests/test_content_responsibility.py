import copy
import json

import pytest

from tests.test_activity_engine import engine_lesson
from tutoring import guide, page_script, teaching_script, interactive
from tutoring.content_responsibility import TEACHING_POLICY, REVIEW_POLICY


def _prompt(writer):
    return writer.prompt({'title': 'Family-selected reading', 'sentences': [{'text': 'Original reading.'}]},
        subject='Reading', learner='the reader', grade='N/A', language='en-US',
        skill='Invite disagreement with the author.', learner_context={
            'family_tutoring': {'content': 'Teach warmly.', 'learner_profile': {}}})


@pytest.mark.parametrize('writer', [guide, teaching_script])
def test_legacy_writers_keep_content_review_with_family_even_with_old_subject_guidance(writer):
    prompt = _prompt(writer)
    assert TEACHING_POLICY in prompt
    assert 'original words' in prompt
    assert 'TEACH DURING READING' in prompt and 'there is no target number of pauses' in prompt
    assert 'concrete everyday example' in prompt
    assert TEACHING_POLICY in interactive.SERVER_TUTOR_RULES


def test_page_writer_keeps_content_review_with_family_even_with_old_subject_guidance():
    from tutoring.lesson_prompt import NON_NEGOTIABLES, HOW_TO_TEACH
    prompt = _prompt(page_script)
    assert NON_NEGOTIABLES in prompt and HOW_TO_TEACH in prompt
    assert "author's words" in prompt and "Teach from the book's point of view" in prompt and 'not proof' in prompt
    assert 'no quota' in prompt and 'concrete example or comparison' in prompt
    # The family's older subject wording is kept but outranked.
    assert 'Invite disagreement with the author.' in prompt and 'the non-negotiables win any conflict' in prompt


def test_family_wording_revision_preserves_source_work_position_and_original_recording_identity(harness, monkeypatch):
    h = harness
    engine, state, seeded = engine_lesson(h, monkeypatch)
    playback = h.ctx.store.get('lesson_playback', state['session_id'])
    old_row = h.ctx.store.get('guides', playback['guide_id'])
    old_file = h.ctx.file_bytes(old_row['guide_path'])
    old = json.loads(old_file)
    opening = next(a for a in old['activities'] if a['kind'] == 'introduce')
    before = {t: copy.deepcopy(h.ctx.store.all(t)) for t in ('attempts', 'activity_responses', 'activity_drafts')}
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **k: pytest.fail('A wording correction must not purchase AI generation'))
    path = f"/api/tutor/guides/{old_row['id']}/teacher-wording"
    payload = {'expected_sha256': old_row['guide_sha256'], 'replacements': [[opening['content']['text'], 'Today we will read the assigned chapter.']]}
    assert h.call('POST', path, json=payload, role='tutor').status_code == 403
    result = h.call('POST', path, json=payload, key='family-wording-once')
    assert result.status_code == 200, result.text
    revised = result.json()
    assert revised['current'] and revised['guide_id'] != old_row['id']
    assert revised['passage_sha256'] != old_row['guide_sha256']
    assert revised['updated_sessions'] == [state['session_id']]
    after = h.ctx.store.get('lesson_playback', state['session_id'])
    assert after['guide_id'] == revised['guide_id']
    for field in ('sentence_index', 'action_id', 'resume_index'):
        assert after[field] == playback[field]
    assert h.ctx.store.get('tutor_sessions', state['session_id'])['revision'] > state['revision']
    changed = engine.state(state['session_id'])['active_activity']
    assert changed['content']['text'] == 'Today we will read the assigned chapter.'
    assert changed['interaction']['prompt'] == 'Today we will read the assigned chapter.'
    assert h.ctx.file_bytes(old_row['guide_path']) == old_file
    assert before == {t: h.ctx.store.all(t) for t in before}
    assert [s for s in revised['sentences'] if s['kind'] == 'book'] == [s for s in old['sentences'] if s['kind'] == 'book']
    assert [(a['id'], a['start_sentence'], a['end_sentence']) for a in revised['activities']] == [(a['id'], a['start_sentence'], a['end_sentence']) for a in old['activities']]
    assert h.call('POST', path, json=payload, key='family-wording-once').json() == revised


def test_wording_revision_rejects_source_changes_and_position_changes(harness, monkeypatch):
    h = harness
    _, state, _ = engine_lesson(h, monkeypatch)
    row = h.ctx.store.get('guides', h.ctx.store.get('lesson_playback', state['session_id'])['guide_id'])
    content = json.loads(h.ctx.file_bytes(row['guide_path']))
    opening = next(a for a in content['activities'] if a['kind'] == 'introduce')['content']['text']
    reading = next(a for a in content['activities'] if a['kind'] == 'read_source')['content']['text']
    count = len(h.ctx.store.all('guides'))
    path = f"/api/tutor/guides/{row['id']}/teacher-wording"
    for sha, old, new in [('0' * 64, opening, 'A revised opening.'),
                           (row['guide_sha256'], opening, 'A revised opening. Another sentence.'),
                           (row['guide_sha256'], reading, 'An altered book.')]:
        assert h.call('POST', path, json={'expected_sha256': sha, 'replacements': [[old, new]]}).status_code == 400
    assert len(h.ctx.store.all('guides')) == count


def test_editorial_review_respects_family_material_selection(harness, monkeypatch):
    h = harness
    _, state, _ = engine_lesson(h, monkeypatch)
    from tutoring import script_review
    row = h.ctx.store.get('guides', h.ctx.store.get('lesson_playback', state['session_id'])['guide_id'])
    data = script_review.inputs(h.ctx, row)
    data['rubric']['sha256'] = 'changed-for-review-test'
    monkeypatch.setattr(script_review, 'inputs', lambda *args: data)
    def review(prompt, **kwargs):
        assert REVIEW_POLICY in prompt
        return {'findings': []}
    monkeypatch.setattr(h.ctx.ai, 'generate', review)
    assert script_review.run(h.ctx, row)['status'] == 'approved'
