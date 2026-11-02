"""PDF-first preparation uses synthetic books, mocked providers, and no child evidence."""
import copy
import hashlib
import io
import json

import pytest
from pypdf import PdfReader

from tests.pdf_fixture import make_pdf
from tests.test_interactive import prepare
from tests.test_tutoring import seed_history
from tests.test_workbooks import add_catalog
from tutoring import passages, script_review, visual_source
from tutoring.guide import GuideError


def text(pdf):
    return '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def linked_sources(h):
    seed=seed_history(h)
    book=add_catalog(h,seed)
    pdf=make_pdf([['Private key for exercise one.', 'The checked answer is the union of tribes.']])
    path=h.add_file(pdf,'Books/Private key.pdf')
    with h.ctx.store.transaction() as tx:
        doc=tx.insert('documents',{'original_filename':'Private key.pdf','file_path':path,
            'sha256':hashlib.sha256(pdf).hexdigest(),'page_count':1,'size_bytes':len(pdf)})
        key=tx.insert('subject_books',{'id':'synthetic-key','subject_id':seed['history']['id'],
            'document_id':doc['id'],'role':'answer_key','status':'ready'})
        for version in tx.all('exercise_versions'):
            tx.update('exercise_versions',version['id'],{'data':{**version['data'],
                'answer_source':{'book_id':key['id'],'sha256':doc['sha256'],'pages':[1]}}})
    package=passages.load(h.ctx,seed['genghis'])
    assigned,metadata=visual_source.prepare(h.ctx,seed['genghis'],package,'')
    return seed,book,visual_source.linked(h.ctx,seed['genghis'],assigned,metadata,h.ctx.books.eligible(seed['genghis']))


def test_linked_pages_are_deduplicated_and_keys_are_only_in_private_review(harness):
    h=harness;seed,book,(planner,metadata,(review,review_metadata))=linked_sources(h)
    assert len(PdfReader(io.BytesIO(planner)).pages)==3  # two reading pages, one exercise page
    assert len(PdfReader(io.BytesIO(review)).pages)==4  # same key page shared by both exercises
    assert 'Student exercises' in text(planner)
    assert 'PRIVATE ANSWERS' not in text(planner)  # embedded unassigned key page excluded
    assert 'Private key' not in text(planner) and 'Private key' in text(review)
    assert [p['role'] for p in review_metadata['pages']]==['assigned_reading','assigned_reading','exercise','answer_key']
    assert metadata['boundaries']['stop_before']==seed['genghis']['stop_before']
    assert not h.ctx.store.all('book_companions') and not h.ctx.store.all('attempts')


@pytest.mark.parametrize('change',['key-edition','key-subject','exercise-edition','exercise-owner'])
def test_source_bundle_rejects_changed_editions_and_cross_subject_links(harness,change):
    h=harness;seed,book,_=linked_sources(h)
    exercises=h.ctx.books.eligible(seed['genghis'])
    with h.ctx.store.transaction() as tx:
        if change=='key-edition':
            key=tx.get('subject_books','synthetic-key')
            tx.update('documents',key['document_id'],{'sha256':'0'*64})
        if change=='key-subject':
            subject=tx.insert('subjects',{'child_id':seed['lucas']['id'],'name':'Unrelated subject'})
            tx.update('subject_books','synthetic-key',{'subject_id':subject['id']})
        if change=='exercise-edition':tx.update('documents',book['document_id'],{'sha256':'0'*64})
        if change=='exercise-owner':exercises[0]['version_id']=exercises[1]['version_id']
    package=passages.load(h.ctx,seed['genghis'])
    pdf,metadata=visual_source.prepare(h.ctx,seed['genghis'],package,'')
    with pytest.raises(GuideError):visual_source.linked(h.ctx,seed['genghis'],pdf,metadata,exercises)


def test_general_export_excludes_private_source_artifacts_and_assessment_context(harness,monkeypatch):
    from storage.backups import export_excel
    from openpyxl import load_workbook
    h=harness;seed,g=prepare(h,monkeypatch)
    row=h.ctx.store.get('guides',g['guide_id'])
    frozen=copy.deepcopy(row['context_snapshot'])
    frozen['source_assessment_notes']=[{'assessment_note':'PRIVATE-CHECK-NOTE'}]
    frozen['lesson_sources']['reviewer']['file_path']='PRIVATE-KEY-PDF'
    with h.ctx.store.transaction() as tx:tx.update('guides',row['id'],{'context_snapshot':frozen})
    path=export_excel(h.ctx.store)
    book=load_workbook(h.drive/path,read_only=True)
    values=json.dumps([list(r) for sheet in book for r in sheet.values],default=str)
    assert 'PRIVATE-CHECK-NOTE' not in values and 'PRIVATE-KEY-PDF' not in values
    assert h.ctx.store.get('guides',row['id'])['context_snapshot']==frozen


def test_legacy_review_identity_does_not_gain_new_pdf_inputs(harness,monkeypatch):
    h=harness;_,g=prepare(h,monkeypatch);row=h.ctx.store.get('guides',g['guide_id'])
    legacy=copy.deepcopy(row)
    legacy['context_snapshot'].pop('lesson_sources')
    data=script_review.inputs(h.ctx,legacy)
    assert data['version']==1 and 'lesson_sources' not in data
    assert visual_source.review_pdf(h.ctx,legacy) is None


def test_pdf_edition_change_invalidates_new_preparation_but_preserves_pinned_session(harness,monkeypatch):
    h=harness;seed,g=prepare(h,monkeypatch);topic=seed['genghis']
    package=passages.load(h.ctx,topic)
    with h.ctx.store.transaction() as tx:tx.update('documents',seed['book']['id'],{'sha256':'0'*64})
    assert not h.ctx.tutor.guide(topic,package)['current']
    assert h.ctx.tutor.guide(topic,package,g['guide_id'])['current']


def test_unavailable_frozen_review_source_fails_without_a_new_provider_request(harness,monkeypatch):
    h=harness;_,g=prepare(h,monkeypatch);row=h.ctx.store.get('guides',g['guide_id'])
    with h.ctx.store.transaction() as tx:tx.delete('lesson_script_reviews',script_review.latest(h.ctx,row['id'])['id'])
    artifact=row['context_snapshot']['lesson_sources']['reviewer']
    h.add_file(b'Unavailable original PDF',artifact['file_path'])
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *_a,**_k:pytest.fail('Do not buy a review without its original PDF'))
    assert script_review.run(h.ctx,row)['status']=='failed'
    assert script_review.run(h.ctx,row)['status']=='failed'
    with pytest.raises(ValueError,match='Audio has not'):script_review.require_audio(h.ctx,g)


def test_pdf_planner_omits_lossy_descriptions_but_keeps_exact_obligations_and_text_fallback():
    source={'subject_sources':{'page_structure':[{'description':'A lossy visual interpretation'}],
                              'current_concepts':[{'id':'observed-concept'}]},
            'source_requirements':{'readings':[{'id':'exact-source'}]},'visual_source':{'mode':'visual_pages'}}
    visual_source.prefer_original_pages(source)
    assert 'page_structure' not in source['subject_sources']
    assert source['source_requirements']['readings'][0]['id']=='exact-source'
    assert source['subject_sources']['current_concepts'][0]['id']=='observed-concept'
    text_only={'subject_sources':{'page_structure':[{'description':'Text fallback needs this'}]}}
    before=copy.deepcopy(text_only);visual_source.prefer_original_pages(text_only)
    assert text_only==before
