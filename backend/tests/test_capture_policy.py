from types import SimpleNamespace
import hashlib
import pytest
from tutoring.capture_policy import answer_only_task, activity_content, task_content
from tests.pdf_fixture import make_pdf


def test_preparation_binds_capture_to_exact_comprehension_task():
    from tutoring.guide import _source_bound_book_work
    quote='Fill the blanks with words from the story: the little ____.'
    task={'document_id':8,'page':1,'instruction':quote}
    source={'document_id':8,'topic_id':2,'book_name':'Story.pdf','offset':0,
        'pages':{1:quote},'sentences':[{'text':quote}],'tasks':[task]}
    result=_source_bound_book_work({'content':{'prompt':'Write the missing word.','evidence_requirement':'handwriting',
        'response_modes':['photo','parent_review'],'source_refs':[{'document_id':8,'page':1,'quote':quote}]}},source)
    assert result['content']['evidence_requirement']=='answer'
    assert 'text' in result['content']['response_modes']
    assert result['origin']=='required_book' and result['content']['source_refs'][0]['quote']==quote


def test_checked_accent_task_accepts_typed_spelling_without_dropping_the_accent_requirement():
    content={'prompt':'Add the accent.','evidence_requirement':'handwriting','response_modes':['photo','parent_review']}
    fixed=task_content(content,{'instruction':'Observe as palavras abaixo e coloque o til onde necessário: a) Leao'})
    assert fixed['evidence_requirement']=='spelling'
    assert fixed['response_modes']==['text','photo','parent_review']
    assert content['evidence_requirement']=='handwriting'


@pytest.mark.parametrize('prompt,expected', [
    ('Preencha as lacunas com palavras ou expressões do texto: b) teu ____', True),
    ('Fill the blanks with words from the passage: the little ____', True),
    ('Copie as palavras do texto para melhorar a caligrafia.', False),
    ('Coloque o til nas palavras: leao, mae.', False),
    ('Mostre os cálculos e explique o resultado.', False),
    ('Complete the spelling blanks with words from the text.', False)])
def test_only_source_identified_answer_tasks_relax_handwriting(prompt, expected):
    assert answer_only_task(prompt) is expected


def test_checked_source_corrects_old_capture_without_rewriting_it(harness):
    h=harness;quote='Fill the blanks with words from the story: the little ____.'
    data=make_pdf([[quote]])
    path=h.add_file(data,'Books/Story.pdf')
    with h.ctx.store.transaction() as tx:
        child=tx.insert('children',{'name':'Practice learner'})
        subject=tx.insert('subjects',{'child_id':child['id'],'name':'Literacy'})
        doc=tx.insert('documents',{'file_path':path,'sha256':hashlib.sha256(data).hexdigest(),'original_filename':'Story.pdf','page_count':1})
        topic=tx.insert('topics',{'subject_id':subject['id'],'document_id':doc['id'],'title':'Story','page_start':1,'page_end':1})
    from tutoring.book_companion import native,persist,row_id
    body=native(data,'Story.pdf','textbook','')
    body['pages'][0].update(status='checked',review_method='visual',student_safe=True,issues=[])
    body['exercises']=[{'id':'blank','reference':'1','pages':[1],'prompt':quote,'kind':'handwritten','answer':None}]
    with h.ctx.store.transaction() as tx:persist(h.ctx,tx,subject['id'],doc,body,0)
    content={'prompt':'Write the answer in your book.','evidence_requirement':'handwriting','response_modes':['photo','parent_review'],
             'source_refs':[{'document_id':doc['id'],'page':1,'quote':quote}]}
    action={'activity_kind':'request_book_work','activity_content':content,'topic_id':topic['id']}
    corrected=activity_content(h.ctx,action)
    assert corrected['evidence_requirement']=='answer' and 'text' in corrected['response_modes']
    assert content['evidence_requirement']=='handwriting'
    assert activity_content(h.ctx,{**action,'assignment_item_id':'required-written-exercise'})==content
    with h.ctx.store.transaction() as tx:
        row=tx.get('book_companions',row_id(doc['sha256'],'textbook'))
        row['data']['pages'][0]['status']='needs_review'
        tx.update('book_companions',row['id'],{'data':row['data']})
    assert activity_content(h.ctx,action)==content
    assert task_content({**content,'evidence_requirement':'spelling'},{'instruction':quote})['evidence_requirement']=='spelling'
