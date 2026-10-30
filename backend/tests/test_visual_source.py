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


def test_visual_boundaries_versions_and_private_pages_are_checked(harness):
    h = harness
    seed, topic, package = whole_page(h)
    for bad_topic, bad_package in [
        (topic, {**package, 'pdf_pages': {'start': 1, 'end': 21}}),
        (topic, {**package, 'document_sha256': 'wrong-version'}),
        ({**topic, 'subject_id': -1}, package),
    ]:
        with pytest.raises(GuideError):
            visual_source.prepare(h.ctx, bad_topic, bad_package, VISUAL)
    with h.ctx.store.transaction() as tx:
        tx.insert('chapters', {'id': 'private-chapter', 'subject_id': seed['history']['id'],
            'chapter': 1, 'test_document_id': seed['book']['id'], 'key_pdf_page': 2})
        tx.insert('teacher_keys', {'id': 'private-page', 'subject_id': seed['history']['id'],
            'key_pdf_page': 2, 'chapter': 1,
            'question_start': 1, 'question_end': 1, 'answer': 'private'})
    with pytest.raises(GuideError, match='private'):
        visual_source.prepare(h.ctx, topic, package, VISUAL)


def test_partial_reading_boundaries_are_preserved_and_combined_sources_stay_textual(harness):
    h=harness;seed=seed_history(h);topic=seed['genghis'];package=passages.load(h.ctx,topic)
    pdf,metadata=visual_source.prepare(h.ctx,topic,package,'')
    assert len(PdfReader(io.BytesIO(pdf)).pages)==2
    assert metadata['boundaries']=={'start_at':topic['start_at'],'stop_before':topic['stop_before']}
    assert 'Kublai' not in package['passage']  # complete page visuals do not expand assigned text
    assert visual_source.prepare(h.ctx,topic,{**package,'hide_pdf':True},'')==(None,None)


def test_visual_preview_is_free_and_provider_receives_only_assigned_pdf(harness, monkeypatch):
    h = harness
    seed, topic, _ = whole_page(h)
    # Ordinary teaching skills now receive original pages without a visual opt-in.
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-never-real')
    h.config.update(ai={'provider': 'openai', 'monthly_generation_enabled': True})
    requests = []
    def respond(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 2000})
        if body['text']['format']['name']=='Review':
            return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':2000,'output_tokens':100},
                'output':[{'content':[{'type':'output_text','text':'{"findings":[]}'}]}]})
        if body['text']['format']['name']=='ScanResult':
            scan={'pages':[{'page':2,'text':'','native_reliable':True,'student_safe':True}], 'exercises':[], 'answers':[]}
            return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':2000,'output_tokens':100},
                'output':[{'content':[{'type':'output_text','text':json.dumps(scan)}]}]})
        count = len(passages.load(h.ctx, topic)['sentences'])
        plan = {'welcome': 'Look at your page.', 'turns': [
            {'type': 'read', 'first': 0, 'last': count - 1},
            {'type': 'ask', 'prompt': 'Tell me what you noticed.'}], 'closing': 'We finished this reading.'}
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 2000, 'output_tokens': 100},
            'output': [{'content': [{'type': 'output_text', 'text': json.dumps(plan)}]}]})
    h.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    payload = {'learner': seed['lucas']['id'], 'topic': topic['id']}
    before = copy.deepcopy(h.ctx.store.all('attempts'))
    preview = h.call('POST', '/api/tutor/reader/guide', json={**payload, 'dry_run': True})
    assert preview.status_code == 200, preview.text
    assert preview.json()['source_mode'] == 'visual_pages' and preview.json()['visual_page_count'] == 1
    assert not requests and not h.ctx.store.all('guides')
    ready = h.call('POST', '/api/tutor/reader/guide', json=payload)
    assert ready.status_code == 200, ready.text
    generations=[body for path,body in requests if not path.endswith('/input_tokens')]
    assert [b['text']['format']['name'] for b in generations]==['ScanResult','AssignedTeachingScript','Review']
    generation = generations[-2]
    assert generation['reasoning']['effort'] == 'high'
    files = [item for message in generation['input'] for item in message['content'] if item['type'] == 'input_file']
    assert len(files) == 1
    pdf = base64.b64decode(files[0]['file_data'].split(',', 1)[1])
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1 and 'felt tents' in reader.pages[0].extract_text()
    row = h.ctx.store.all('guides')[0]
    assert row['context_snapshot']['visual_source']['pages'][0]['page'] == 2
    review_files=[item for message in generations[-1]['input'] for item in message['content'] if item['type']=='input_file']
    assert review_files==files
    assert ready.json()['script_review']['status']=='approved'
    assert 'lesson_sources' not in ready.text and 'private-review-sources' not in ready.text
    assert h.ctx.store.all('attempts') == before
    count = len(requests)
    assert h.call('POST', '/api/tutor/reader/guide', json={**payload, 'dry_run': True}).json()['reused']
    assert len(requests) == count


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


def test_image_only_assigned_pages_can_reach_visual_preparation_preview(harness,monkeypatch):
    seed,topic,package=whole_page(harness)
    monkeypatch.setenv('OPENAI_API_KEY','test-key-never-real')
    harness.config.update(ai={'provider':'openai','monthly_generation_enabled':True})
    monkeypatch.setattr(passages,'load',lambda *_a,**_k:{**package,'passage':'','sentences':[]})
    reply=harness.call('POST','/api/tutor/reader/guide',json={
        'learner':seed['lucas']['id'],'topic':topic['id'],'dry_run':True})
    assert reply.status_code==200,reply.text
    assert reply.json()['source_mode']=='visual_pages' and reply.json()['source_inventory_required']
    assert not harness.ctx.store.all('guides') and not harness.ctx.ai.ledger.requests()
