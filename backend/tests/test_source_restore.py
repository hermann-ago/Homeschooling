import copy,hashlib
from tests.pdf_fixture import make_pdf


def fixture(h):
    pdf=make_pdf([['Original cover'],['Lesson 60','An exact verified opening paragraph.'],['Lesson 61','Another exact opening paragraph.']])
    path=h.add_file(pdf,'Books/Original part two.pdf')
    with h.ctx.store.transaction() as tx:
        child=tx.insert('children',{'name':'Practice learner'})
        subject=tx.insert('subjects',{'child_id':child['id'],'name':'Language Arts'})
        doc=tx.insert('documents',{'original_filename':'Wrong old name.pdf','page_count':2})
        topic=tx.insert('topics',{'subject_id':subject['id'],'document_id':doc['id'],'pdf_filename':doc['original_filename'],
            'title':'Lesson 60','page_start':1,'page_end':2,'pdf_page_offset':15,'chapter_order':0,'completed':True})
    doc=h.ctx.store.get('documents',doc['id']);topic=h.ctx.store.get('topics',topic['id'])
    payload={'path':path,'sha256':hashlib.sha256(pdf).hexdigest(),'expected_revision':doc['revision'],
        'note':'Checked original source pages and preserved existing learner identity.',
        'topics':[{'topic_id':topic['id'],'expected_revision':topic['revision'],'page_start':1,'page_end':1,'pdf_page_offset':1,'source_quote':'An exact verified opening paragraph.'}],
        'additional_topics':[{'title':'Lesson 61','chapter_order':1,'page_start':2,'page_end':2,'pdf_page_offset':1,'source_quote':'Another exact opening paragraph.'}]}
    return subject,doc,topic,payload


def test_restore_missing_original_preserves_identity_and_history_without_ai(harness,monkeypatch):
    h=harness;s,doc,topic,p=fixture(h)
    def forbidden(*args,**kw):raise AssertionError('Restoration must not call AI')
    monkeypatch.setattr(h.ctx.ai,'generate',forbidden)
    monkeypatch.setattr(h.ctx.books,'reading_changed',forbidden) # Rematching can queue paid work.
    before={k:copy.deepcopy(h.ctx.store.all(k)) for k in ('attempts','tutor_sessions','guides','completions')}
    url=f"/api/subjects/{s['id']}/documents/{doc['id']}/restore-source"
    result=h.call('PUT',url,json=p)
    assert result.status_code==200,result.text
    saved=h.ctx.store.get('topics',topic['id'])
    assert saved['completed'] and saved['document_id']==doc['id']
    assert saved['pdf_page_offset']==1 and saved['pdf_filename']=='Original part two.pdf'
    assert h.ctx.store.get('documents',doc['id'])['sha256']==p['sha256']
    added=next(t for t in h.ctx.store.all('topics') if t['id']!=topic['id'])
    assert added['title']=='Lesson 61' and not added['completed']
    assert len(h.ctx.store.all('document_restorations'))==1
    assert before=={k:h.ctx.store.all(k) for k in before}
    assert h.call('PUT',url,json=p).status_code==409


def test_wrong_source_quote_and_ownership_do_not_rebind_book(harness):
    h=harness;s,doc,topic,p=fixture(h)
    original=h.ctx.store.get('documents',doc['id'])
    p['topics'][0]['source_quote']='A sentence absent from the original book.'
    url=f"/api/subjects/{s['id']}/documents/{doc['id']}/restore-source"
    assert h.call('PUT',url,json=p).status_code==400
    assert h.ctx.store.get('documents',doc['id'])==original
    p['topics'][0]['source_quote']='An exact verified opening paragraph.'
    p['topics'][0]['topic_id']=99999
    assert h.call('PUT',url,json=p).status_code==400
    assert h.ctx.store.get('documents',doc['id'])==original
