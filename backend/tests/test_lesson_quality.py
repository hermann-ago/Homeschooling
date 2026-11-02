"""Literary source text and original tasks survive worksheet simplification."""
import copy
import hashlib

import pytest

from tutoring import guide,lesson_quality
from tests.pdf_fixture import make_pdf


def test_checked_book_options_replace_generated_options_without_changing_identity():
    task={'id':'book-1','instruction':'Select all the even numbers.','document_id':8,'page':12,
        'answer_format':'multiple_select','choices':[{'id':'a','label':'2'},{'id':'b','label':'3'},{'id':'c','label':'4'}]}
    plan={'segments':[{'type':'activity','activity_kind':'ask_question','content':{
        'prompt':task['instruction'],'choices':[{'id':'x','label':'Invented'},{'id':'y','label':'Alternative'}],
        'response_modes':['choice','text'],'source_refs':[{'document_id':8,'page':12,'quote':task['instruction']}]}}]}
    bound=lesson_quality.bind_tasks(plan,{'tasks':[task]})['segments'][0]
    assert bound['origin']=='required_book'
    assert bound['content']['choices']==task['choices']
    assert bound['content']['answer_format']=='multiple_select'
    assert bound['content']['source_refs'][0]['page']==12
    assert guide.GuideSegment.model_validate(bound).content.choices[0].id=='a'


















def test_task_excerpt_requires_exact_substantial_unique_source_identity():
    task={'document_id':1,'page':2,'instruction':'Listen to the reading. Now find and mark each letter R.'}
    refs=[{'document_id':1,'page':2,'quote':'Now find and mark each letter R.'}]
    assert lesson_quality.task_matches(task,refs,[task])
    assert not lesson_quality.task_matches(task,[{**refs[0],'page':3}],[task])
    assert not lesson_quality.task_matches(task,[{**refs[0],'quote':'letter R'}],[task])
    other={**task,'instruction':'Draw one circle. Now find and mark each letter R.'}
    assert not lesson_quality.task_matches(task,refs,[task,other])






