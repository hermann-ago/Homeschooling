"""A script changed after the app wrote it is saved marked Revised, keeping the original's identity."""
import pytest
from tests.test_library import child, upload, enroll, index
from tutoring import guide, passages, skills


def test_revised_script_keeps_its_original_and_is_marked(harness, monkeypatch):
    h = harness; kid = child(h)
    upload(h); enroll(h, kid['id']); topic = index(h, kid['id'])['topics'][0]
    package = passages.load(h.ctx, topic)
    skill = skills.packet(h.ctx.store, h.ctx.store.get('subjects', topic['subject_id']))
    monkeypatch.setattr(guide, 'write_plan', lambda *a, **k: pytest.fail('No paid writer'))
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **k: pytest.fail('No paid reviewer'))
    def script(say):
        return {'welcome': 'Let us read together.', 'turns': [
            {'type': 'read', 'text': 'Original story.', 'document_id': topic['document_id'],
             'page_start': topic['page_start'], 'page_end': topic['page_start']},
            {'type': 'say', 'text': say}], 'closing': 'We can return to this story.'}
    body = {'learner': kid['id'], 'topic': topic['id'], 'source_sha256': package['passage_sha256'],
            'expected_skill_version': skill['version']}
    first = h.call('POST', '/api/tutor/reader/guide/import', json={**body, 'script': script('First wording.')}).json()
    assert first['origin'] == 'hand' and first['revision_of'] is None
    saved = h.call('GET', f"/api/tutor/guides/{first['guide_id']}/script").json()
    assert saved['script']['turns'][1]['text'] == 'First wording.'
    revised = h.call('POST', '/api/tutor/reader/guide/import', json={**body, 'script': script('Clearer wording.'),
                                                                    'revises_guide_id': first['guide_id']})
    assert revised.status_code == 200, revised.text
    revised = revised.json()
    assert revised['origin'] == 'revised'
    assert revised['revision_of']['guide_id'] == first['guide_id']
    assert revised['revision_of']['original_guide_id'] == first['guide_id'] and revised['revision_of']['original_model'] == 'codex-reviewed'
    again = h.call('POST', '/api/tutor/reader/guide/import', json={**body, 'script': script('Even clearer.'),
                                                                  'revises_guide_id': revised['guide_id']}).json()
    assert again['revision_of']['guide_id'] == revised['guide_id'] and again['revision_of']['original_guide_id'] == first['guide_id']
    other = h.call('POST', '/api/tutor/reader/guide/import', json={**body, 'script': script('x'), 'revises_guide_id': 'missing'})
    assert other.status_code == 400
