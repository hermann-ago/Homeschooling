"""New preparation uses chapter maps and original pages, without whole-book scans."""
import io
import pytest
from pypdf import PdfReader, PdfWriter
from tests.pdf_fixture import make_pdf
from tests.test_library import child, upload, enroll, index
from tutoring import navigation, page_script, books, guide


def test_codex_structured_import_uses_original_pages_without_paid_calls(harness, monkeypatch):
    from tutoring import passages, skills
    h=harness; kid=child(h)
    upload(h); enroll(h,kid['id']); topic=index(h,kid['id'])['topics'][0]
    package=passages.load(h.ctx,topic)
    skill=skills.packet(h.ctx.store,h.ctx.store.get('subjects',topic['subject_id']))
    monkeypatch.setattr(guide,'write_plan',lambda *a,**k:pytest.fail('No paid writer'))
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**k:pytest.fail('No paid reviewer'))
    script={'welcome':'Let us read together.','turns':[
        {'type':'read','text':'Original story.','document_id':topic['document_id'],
         'page_start':topic['page_start'],'page_end':topic['page_start']},
        {'type':'book_work','document_id':topic['document_id'],'page':topic['page_start'],
         'prompt':'Point to the title on this page.','response':{'format':'observe'}},
        {'type':'ask','prompt':'Choose a title.','response':{'format':'single_choice','choices':['Story','Map']}}],
        'closing':'We can return to this story.'}
    payload={'learner':kid['id'],'topic':topic['id'],'source_sha256':package['passage_sha256'],
        'expected_skill_version':skill['version'],'script':script}
    path='/api/tutor/reader/guide/import'
    assert h.call('POST',path,json={**payload,'plan':{'mode':'expand','segments':[{'type':'intro','text':'Hi'}]}}).status_code==422
    assert h.call('POST',path,json={**payload,'source_sha256':'0'*64}).status_code==409
    import copy
    foreign=copy.deepcopy(payload)
    foreign['script']['turns'][0]['document_id']=999999
    assert h.call('POST',path,json=foreign).status_code==502
    assert not h.ctx.store.all('guides')
    result=h.call('POST',path,json=payload)
    assert result.status_code==200,result.text
    row=h.ctx.store.get('guides',result.json()['guide_id'])
    assert row['model']=='codex-reviewed'
    assert row['context_snapshot']['teaching_script']['script']['welcome']==script['welcome']
    assert result.json()['script_review']['status']=='approved'
    assert not h.ctx.ai.ledger.requests()
    assert not h.ctx.store.all('tutor_sessions') and not h.ctx.store.all('attempts')


def test_structurally_blank_pages_are_explicit_in_both_source_maps(harness):
    from tutoring import visual_source, passages
    from pypdf.generic import NameObject, DecodedStreamObject, ArrayObject, DictionaryObject
    h = harness; kid = child(h)
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(make_pdf([['A source story with actual visible reading.']]))))
    empty = writer.add_blank_page(width=612, height=792)
    assert visual_source.blank_page(empty)
    visual = writer.add_blank_page(width=612, height=792)
    stream = DecodedStreamObject(); stream.set_data(b'0 0 100 100 re f')
    visual[NameObject('/Contents')] = stream
    assert not visual.extract_text() and not visual_source.blank_page(visual)
    annotated = writer.add_blank_page(width=612, height=792)
    annotated[NameObject('/Annots')] = ArrayObject([DictionaryObject()])
    assert not visual_source.blank_page(annotated)
    output = io.BytesIO(); writer.write(output)
    assert upload(h, data=output.getvalue()).status_code == 200
    reading = enroll(h, kid['id'])
    # Keep this source test independent of chapter-map heuristics.
    with h.ctx.store.transaction() as tx:
        topic = tx.insert('topics', {'subject_id': reading['subject_id'], 'title': 'Test story',
            'document_id': tx.get('library_books', 'library-02')['document_id'],
            'page_start': 1, 'page_end': 4, 'pdf_page_offset': 0})
    package = passages.load(h.ctx, topic)
    pdf, metadata = visual_source.prepare(h.ctx, topic, package, '')
    assert [p.get('blank', False) for p in metadata['pages']] == [False, True, False, False]
    _, public, (_, private) = navigation.attach(h.ctx, topic, pdf, metadata)
    assert public['pages'][1]['blank'] and private['pages'][1]['blank']
    assert 'blank=true' in page_script.prompt({**package, 'title': 'Test story'},
        subject='Reading', learner='the reader', grade=None, language='en-US')


def test_chapter_map_is_local_shared_and_does_not_scan(harness, monkeypatch):
    h = harness
    one, two = child(h), child(h, 'Future reader')
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(make_pdf([['First chapter.'], ['Second chapter.']]))))
    writer.add_outline_item('First chapter', 0)
    writer.add_outline_item('Second chapter', 1)
    output = io.BytesIO(); writer.write(output)
    upload(h, data=output.getvalue())
    monkeypatch.setattr(h.ctx.ai, 'generate', lambda *a, **k: pytest.fail('No AI scan for navigation'))
    monkeypatch.setattr(books, 'scan_unit', lambda *a, **k: pytest.fail('Retired scanner'))
    readings = []
    for kid in (one, two):
        enroll(h, kid['id']); readings.append(index(h, kid['id']))
    assert [t['title'] for t in readings[0]['topics']] == ['First chapter', 'Second chapter']
    assert len(h.ctx.store.all('book_navigation')) == 1
    assert not h.ctx.store.all('book_units')
    assert not h.ctx.store.all('attempts')
    h.restart()
    assert len(h.ctx.store.all('book_navigation')) == 1


def test_direct_writer_needs_no_task_inventory_and_preserves_controls():
    passage = {'sentences': [{'text': 'Original story.'}, {'text': 'More story.'}]}
    context = {'visual_source': {'pages': [{'document_id': 2, 'page': 7, 'role': 'workbook', 'book_name': 'Workbook'}]}}
    value = {'welcome': 'Let us explore.', 'turns': [
        {'type': 'read', 'first': 0, 'last': 1},
        {'type': 'book_work', 'document_id': 2, 'page': 7, 'prompt': 'Choose the original answer.',
         'response': {'format': 'single_choice', 'choices': ['One', 'Two']}},
        {'type': 'ask', 'prompt': 'What do you think?', 'purpose': 'reasoning', 'response': {'format': 'text'}}],
        'closing': 'We can return to this idea.'}
    result = page_script.compile_script(value, passage, context, 'en-US')
    assert result['segments'][1]['text'] == 'Original story. More story.'
    task = result['segments'][2]
    assert task['origin'] == 'required_book'
    assert task['content']['choices'][1]['label'] == 'Two'
    assert task['source_refs'][0]['page'] == 7
    # Reading all worksheet text is not a mechanical generation requirement.
    value['turns'].pop(0)
    page_script.compile_script(value, passage, context, 'en-US')
    # A PDF writer supplies faithful reading words and page references directly,
    # without a pre-transcribed sentence inventory.
    value['turns'].insert(0, {'type':'read','text':'The original story, with natural typography.',
        'document_id':2,'page_start':7,'page_end':7})
    made=page_script.compile_script(value, {'sentences':[]}, context, 'en-US')
    assert made['segments'][1]['text']=='The original story, with natural typography.'
    assert made['segments'][1]['source_refs'][0]['page']==7
    # A PDF lesson with a text layer may reference numbered sentences or transcribe.
    assert page_script.schema(passage,context,'en-US').provider_json_schema()['$defs']['Read']['properties']['first']['type']==['integer','null']
    context['visual_source']['pages'][0]['role'] = 'answer_key'
    with pytest.raises(ValueError, match='student page'):
        page_script.compile_script(value, passage, context, 'en-US')


def test_selected_pages_are_edition_bound_and_keys_are_private(harness, monkeypatch):
    h=harness; kid=child(h)
    upload(h); enroll(h,kid['id']); reading=index(h,kid['id']); topic=reading['topics'][0]
    resources=[]
    for role in ['workbook','answer_key']:
        path=h.add_file(make_pdf([[role+' original page.']]),role+'.pdf')
        with h.ctx.store.transaction() as tx:
            job=h.ctx.books.begin(tx,topic['subject_id'],path,role,answer_for=resources[0]['id'] if resources else None)
        h.ctx.books.process(job['id']);resources.append(h.ctx.store.get('subject_books',job['book_id']))
    refs=[{'document_id':b['document_id'],'page_start':1,'page_end':1} for b in resources]
    r=h.call('PUT',f"/api/topics/{topic['id']}/source-pages",json={'sources':refs,'expected_revision':0})
    assert r.status_code==200,r.text
    from tutoring import visual_source,passages
    package=passages.load(h.ctx,topic)
    pdf,meta=visual_source.prepare(h.ctx,topic,package,'')
    student,public,(private,review)=navigation.attach(h.ctx,topic,pdf,meta)
    assert len(PdfReader(io.BytesIO(student)).pages)==2
    assert len(PdfReader(io.BytesIO(private)).pages)==3
    assert not any(p['role']=='answer_key' for p in public['pages'])
    assert review['pages'][-1]['role']=='answer_key'
    # No source inventory may run before the script writer.
    from tutoring import lesson_source_index
    monkeypatch.setattr(lesson_source_index,'ensure',lambda *a,**k:pytest.fail('No preflight extraction'))
    seen=[]
    def write(text,*args,**kwargs):
        seen.append((text,kwargs['pdf']))
        return {'welcome':'Welcome.','turns':[{'type':'read','first':0,'last':len(package['sentences'])-1}], 'closing':'Until next time.'},'test-writer'
    monkeypatch.setattr(guide,'write_plan',write)
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**k:{'findings':[]})
    result=h.call('POST','/api/tutor/reader/guide',json={'learner':kid['id'],'topic':topic['id'],'prepare_voice':False})
    assert result.status_code==200,result.text
    assert result.json()['current']
    # The writer reads the key page (teacher-only) to record answers; the child's pages never include it.
    assert len(PdfReader(io.BytesIO(seen[0][1])).pages)==3 and 'ANSWER KEY PAGES' in seen[0][0]
    planner=h.ctx.store.get('guides',result.json()['guide_id'])['context_snapshot']['lesson_sources']['planner']
    assert not any(p['role']=='answer_key' for p in planner['pages'])
    assert 'reading_ids' not in seen[0][0] and 'task_id' not in seen[0][0]
    assert not h.ctx.store.all('book_units')
    # A change of selected pages invalidates future reuse, preserving the saved guide.
    revision=r.json()['revision']
    changed=h.call('PUT',f"/api/topics/{topic['id']}/source-pages",json={'sources':[],'expected_revision':revision})
    assert changed.status_code==200,changed.text
    loaded=h.call('GET','/api/tutor/reader',params={'learner':kid['id'],'topic':topic['id']}).json()
    assert not loaded['guide']['current']


def test_voice_samples_are_read_only_and_selected_voice_does_not_replace_audio(harness, monkeypatch):
    import httpx
    from dependencies import select_context
    from routers.tutor import _narrator
    h=harness; kid=child(h)
    upload(h); enroll(h,kid['id']); reading=index(h,kid['id']);topic=reading['topics'][0]
    calls=[]
    def respond(request):
        calls.append(request)
        assert request.method=='GET' and request.url.path=='/v2/voices'
        return httpx.Response(200,json={'voices':[{'voice_id':'available-voice-123','name':'Narrator','labels':{'accent':'British'},'preview_url':'https://example.com/sample.mp3'}]})
    monkeypatch.setattr(h.ctx.ai,'key',lambda provider:'synthetic-only-key')
    h.ctx.ai.http=httpx.Client(transport=httpx.MockTransport(respond))
    h.ctx.config.update(tts={'provider':'elevenlabs'})
    listed=h.call('GET','/api/ai/elevenlabs/voices')
    assert listed.status_code==200,listed.text
    assert not listed.json()['speech_requested']
    r=h.call('PUT',f"/api/topics/{topic['id']}/narrator",json={'voice':'available-voice-123'})
    assert r.status_code==200,r.text
    with select_context(h.ctx):assert _narrator(topic)[0]=='available-voice-123'
    assert len(calls)==1 and not h.ctx.store.all('audio_tracks')
    denied=h.call('PUT',f"/api/topics/{topic['id']}/narrator",json={'voice':'unavailable-123'})
    assert denied.status_code==400


def test_retired_whole_book_authoring_endpoints_cannot_purchase_generation(harness, monkeypatch):
    h=harness
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**k:pytest.fail('Retired endpoint must not generate'))
    r=h.call('POST','/api/subjects/1/book-collection/analyze',json={'fingerprint':'old','maximum_usd':1})
    assert r.status_code==410,r.text
    r=h.call('POST','/api/subjects/1/book-companions/1')
    assert r.status_code==410,r.text
