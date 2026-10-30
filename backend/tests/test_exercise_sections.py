import copy
import pytest
from tutoring.exercise_sections import sections
from tutoring.activities import QuestionContent
from tests.test_activity_engine import engine_lesson,invoke,event
from tutoring.service import TutorError


def item(index,**changes):
    return {'id':f's:a{index}','action_id':f'a{index}','session_id':'s','activity_kind':'ask_question',
        'activity_content':{'answer_format':'true_false'},'origin':'required_book','status':'pending',
        'source_refs':[{'document_id':8,'page':4}],**changes}


def test_sections_use_contiguous_public_source_identity_without_future_prompts():
    actions=[item(1,status='answered'),item(2),item(3,source_refs=[{'document_id':8,'page':5}]),item(4,origin='adaptive')]
    before=copy.deepcopy(actions);grouped=sections(actions)
    assert actions==before and set(grouped)=={'a1','a2'}
    assert grouped['a2']['item']==2 and grouped['a2']['total']==2 and grouped['a2']['completed']==1
    assert grouped['a1']['id']==grouped['a2']['id']
    assert 'prompt' not in str(grouped)
    assert not sections([item(1),item(2,parent_activity_id='a1')])


def test_matching_contract_and_actual_response_are_structured_and_durable(harness,monkeypatch):
    engine,state,_=engine_lesson(harness,monkeypatch)
    matching={'items':[{'id':'bird','label':'Bird'},{'id':'fish','label':'Fish'}],
        'options':[{'id':'water','label':'Water'},{'id':'air','label':'Air'}]}
    state=invoke(engine,state,content={'prompt':'Match each animal to its habitat.','matching':matching})
    state=event(engine,state,'save_draft',{'response_id':'matches-answer','method':'typed','matches':{'bird':'air'}})
    assert state['active_activity']['draft']['matches']=={'bird':'air'}
    for invalid in ({'bird':'air'},{'bird':'air','fish':'air'},{'bird':'invented','fish':'water'}):
        with pytest.raises(TutorError,match='available match'):
            event(engine,state,'submit_response',{'response_id':'matches-answer','method':'typed','matches':invalid})
    state=event(engine,state,'submit_response',{'response_id':'matches-answer','method':'typed',
        'text':'Untrusted alternate text','matches':{'fish':'water','bird':'air'}})
    saved=harness.ctx.store.get('activity_responses','matches-answer')
    assert saved['confirmed_text']=='Bird → Air\nFish → Water'
    assert saved['original']['matches']=={'fish':'water','bird':'air'}
    assert not harness.ctx.store.find('attempts',session_id=state['session_id'])
    with pytest.raises(ValueError):QuestionContent(prompt='Match',matching={**matching,'items':[matching['items'][0]]})
