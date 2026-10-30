import copy
import pytest


def seed(h):
    with h.ctx.store.transaction() as tx:
        child=tx.insert('children',{'name':'Practice learner'})
        subject=tx.insert('subjects',{'child_id':child['id'],'name':'Language Arts'})
        docs=[tx.insert('documents',{'original_filename':'Same book.pdf','page_count':8}) for _ in range(2)]
        topics=[]
        for index,doc in enumerate(docs):
            for order in (0,1):
                topics.append(tx.insert('topics',{'subject_id':subject['id'],'document_id':doc['id'],
                    'pdf_filename':'Same book.pdf','title':f'Lesson {index*60+order+1}',
                    'chapter_order':order,'page_start':order+1,'page_end':order+1,'is_core':index==0}))
    return subject,docs,topics


@pytest.mark.parametrize('method,route',[('PUT','/set-main-book'),('PUT','/set-book-offset'),('DELETE','')])
def test_ambiguous_filename_cannot_change_both_books(harness,method,route):
    h=harness;s,docs,topics=seed(h)
    before=copy.deepcopy(h.ctx.store.all('topics'))
    r=h.call(method,f"/api/subjects/{s['id']}/books{route}",params={'pdf_filename':'Same book.pdf','offset':3})
    assert r.status_code==409,r.text
    assert h.ctx.store.all('topics')==before


def test_book_actions_and_complete_previous_are_scoped_to_document(harness):
    h=harness;s,docs,topics=seed(h)
    base=f"/api/subjects/{s['id']}"
    params={'pdf_filename':'Same book.pdf','document_id':docs[1]['id']}
    r=h.call('PUT',base+'/books/set-book-offset',params={**params,'offset':3})
    assert r.status_code==200,r.text
    assert [h.ctx.store.get('topics',t['id'])['pdf_page_offset'] for t in topics]==[0,0,3,3]
    assert h.call('PUT',base+'/books/set-main-book',params=params).status_code==200
    assert [h.ctx.store.get('topics',t['id'])['is_core'] for t in topics]==[False,False,True,True]
    r=h.call('POST',base+f"/topics/{topics[-1]['id']}/complete-previous")
    assert r.status_code==200,r.text
    assert [h.ctx.store.get('topics',t['id'])['completed'] for t in topics]==[False,False,True,True]
    r=h.call('DELETE',base+'/books',params=params)
    assert r.status_code==204,r.text
    assert all(h.ctx.store.get('topics',t['id']) for t in topics[:2])
    assert all(not h.ctx.store.get('topics',t['id']) for t in topics[2:])


def test_document_from_another_book_cannot_be_selected_by_filename(harness):
    h=harness;s,docs,topics=seed(h)
    r=h.call('PUT',f"/api/subjects/{s['id']}/books/set-book-offset",params={
        'pdf_filename':'Other book.pdf','document_id':docs[0]['id'],'offset':9})
    assert r.status_code==404
    assert [h.ctx.store.get('topics',t['id'])['pdf_page_offset'] for t in topics]==[0]*4


def test_create_lesson_from_collection_is_source_bound_and_does_not_generate(harness, monkeypatch):
    h=harness;s,docs,topics=seed(h)
    with h.ctx.store.transaction() as tx:
        collection=tx.insert('book_collections', {'id':'source-collection','name':'Practice sources'})
        tx.insert('subject_collections', {'id':'binding','subject_id':s['id'],'collection_id':collection['id']})
        tx.insert('collection_books', {'id':'source','collection_id':collection['id'],'document_id':docs[0]['id'],
            'position':0,'role':'combined'})
        tx.insert('collection_books', {'id':'key','collection_id':collection['id'],'document_id':docs[1]['id'],
            'position':1,'role':'answer_key'})
    def forbidden(*args, **kwargs):raise AssertionError('Adding an assigned source must not purchase generation')
    monkeypatch.setattr(h.ctx.ai,'generate',forbidden)
    base=f"/api/subjects/{s['id']}/topics"
    body={'title':'First assigned lesson','page_start':3,'page_end':5,'document_id':docs[0]['id'],
        'pdf_filename':'Untrusted.pdf','chapter_order':2,'language':'pt-BR'}
    before=copy.deepcopy(h.ctx.store.all('topics'))
    for changes in ({'document_id':docs[1]['id']},{'page_end':9},{'page_start':6}, {'completed':True}):
        assert h.call('POST',base,json={**body,**changes}).status_code==400
        assert h.ctx.store.all('topics')==before
    result=h.call('POST',base,json=body,key='create-source-lesson')
    assert result.status_code==201,result.text
    assert result.json()['pdf_filename']=='Same book.pdf'
    assert result.json()['document_id']==docs[0]['id']
    assert result.json()['completed'] is False
    assert h.call('POST',base,json=body,key='create-source-lesson').json()==result.json()
    assert len(h.ctx.store.all('topics'))==len(before)+1
    assert not h.ctx.store.all('tutor_sessions')
