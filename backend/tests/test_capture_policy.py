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




def test_original_page_scripts_keep_the_writers_declared_evidence():
    # A handwriting task the writer chose from the page is not relaxed by subject heuristics.
    content = {'prompt': 'Coloque o til nas palavras.', 'evidence_requirement': 'handwriting',
               'response_modes': ['photo', 'parent_review']}
    playback = {'context_snapshot': {'prepared_guide': {'teaching_script': {'version': 'original-pages-3'}}}}
    ctx = SimpleNamespace(store=SimpleNamespace(get=lambda table, key: playback if table == 'lesson_playback' else
                                                pytest.fail('Declared evidence needs no companion lookup')))
    action = {'session_id': 's', 'activity_kind': 'request_book_work', 'activity_content': content}
    assert activity_content(ctx, action) == content
