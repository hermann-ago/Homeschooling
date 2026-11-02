"""Original pages are the default, with an explicit text-only compatibility path."""
import base64
import copy
import io
import json

import httpx
import pytest
from pypdf import PdfReader

from tests.test_tutoring import seed_history
from tutoring import passages, visual_source
from tutoring.guide import GuideError

VISUAL = '---\nname: workbook\nlesson_source: visual_pages\n---\nUse actual pictures.'


def whole_page(h):
    seed = seed_history(h)
    with h.ctx.store.transaction() as tx:
        topic = tx.update('topics', seed['genghis']['id'], {
            'start_at': None, 'stop_before': None, 'page_start': 2, 'page_end': 2})
    return seed, topic, passages.load(h.ctx, topic)


def test_explicit_text_mode_does_not_read_pdf():
    assert visual_source.prepare(None, None, None, '---\nlesson_source: text\n---\nKeep original text.') == (None, None)


@pytest.mark.parametrize('skill', ['', 'lesson_source: text', '---\nname: ordinary\n---\nlesson_source: text'])
def test_pdf_is_default_and_metadata_must_be_explicit(skill):
    assert visual_source.requested(skill)


def test_visual_pdf_contains_only_assigned_pages_and_stable_provenance(harness):
    h = harness
    seed, topic, package = whole_page(h)
    data, metadata = visual_source.prepare(h.ctx, topic, package, VISUAL)
    reader = PdfReader(io.BytesIO(data))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert 'felt tents' in text and 'rabbi ate' not in text and 'united the tribes' not in text
    assert metadata['pages'] == [{'attachment_page': 1, 'document_id': seed['book']['id'],
                                  'page': 2, 'printed_page': 2}]
    assert visual_source.prepare(h.ctx, topic, package, VISUAL) == (data, metadata)


def test_partial_reading_boundaries_are_preserved_and_combined_sources_stay_textual(harness):
    h=harness;seed=seed_history(h);topic=seed['genghis'];package=passages.load(h.ctx,topic)
    pdf,metadata=visual_source.prepare(h.ctx,topic,package,'')
    assert len(PdfReader(io.BytesIO(pdf)).pages)==2
    assert metadata['boundaries']=={'start_at':topic['start_at'],'stop_before':topic['stop_before']}
    assert 'Kublai' not in package['passage']  # complete page visuals do not expand assigned text
    assert visual_source.prepare(h.ctx,topic,{**package,'hide_pdf':True},'')==(None,None)


def test_registered_question_does_not_gain_a_redundant_legacy_question(harness, monkeypatch):
    from tutoring import guide
    h = harness
    seed = seed_history(h)
    monkeypatch.setattr(guide, 'write_plan', lambda text, models, **kwargs: ({'mode': 'expand', 'segments': [
        {'type': 'intro', 'text': 'Let us read.'},
        {'type': 'read', 'from': 0, 'to': 99},
        {'type': 'activity', 'activity_kind': 'ask_question', 'content': {'prompt': 'What changed?'}}
    ]}, models[0]))
    response = h.call('POST', '/api/tutor/reader/guide', json={'learner': seed['lucas']['id'], 'topic': seed['genghis']['id']})
    assert response.status_code == 200, response.text
    questions = [a for a in response.json()['activities'] if a['kind'] == 'ask_question']
    assert [a['content']['prompt'] for a in questions] == ['What changed?']


