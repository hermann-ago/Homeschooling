import copy
import pytest

from tests.test_activity_engine import engine_lesson, invoke, event
from tests.test_interactive import correct
from tutoring import guide, interactive
from tutoring.service import TutorConflict, TutorError


def new_script(h,seeded,monkeypatch):
    monkeypatch.setattr(guide,'write_plan',lambda text,models,**kwargs:({'mode':'expand','segments':[
        {'type':'intro','text':'A new friendly opening.'},{'type':'read','from':0,'to':99},
        {'type':'action','text':'Explain one idea.','action_kind':'answer'}]},'synthetic'))
    result=h.call('POST','/api/tutor/reader/guide',json={'learner':seeded['lucas']['id'],
        'topic':seeded['genghis']['id'],'rewrite':True,'prepare_voice':False})
    assert result.status_code==200,result.text
    return result.json()['guide_id']


def test_replacement_preserves_original_evidence_and_is_durably_idempotent(harness,monkeypatch):
    h=harness;engine,state,seeded=engine_lesson(h,monkeypatch)
    state=invoke(engine,state)
    monkeypatch.setattr(interactive,'gemini_turn',correct)
    state=event(engine,state,'submit_response',{'response_id':'old-answer','text':'He united them.','assess_after_save':True})
    before=copy.deepcopy(h.ctx.store.all('attempts'))
    old_playback=h.ctx.store.get('lesson_playback',state['session_id'])
    fresh=new_script(h,seeded,monkeypatch)
    made=engine.replace_script(state['session_id'],fresh,state['revision'],'replace-synthetic-script')
    assert made['session_id']!=state['session_id']
    assert made['playback']['guide_id']==fresh
    assert made['active_activity']['kind']=='introduce'
    assert h.ctx.store.get('tutor_sessions',state['session_id'])['status']=='superseded'
    assert h.ctx.store.get('lesson_playback',state['session_id'])==old_playback
    assert h.ctx.store.all('attempts')==before
    assert not h.ctx.store.get('topics',seeded['genghis']['id'])['completed']
    old=engine.state(state['session_id'])
    assert old['active_activity'] is None
    assert old['attempt_navigation']['resume_repeat']['id']==made['session_id']
    assert engine.replace_script(state['session_id'],fresh,state['revision'],'replace-synthetic-script')['session_id']==made['session_id']
    with pytest.raises(TutorConflict):
        engine.replace_script(state['session_id'],old_playback['guide_id'],state['revision'],'replace-synthetic-script')


def test_replacement_requires_current_revision_and_owned_guide(harness,monkeypatch):
    h=harness;engine,state,seeded=engine_lesson(h,monkeypatch)
    fresh=new_script(h,seeded,monkeypatch)
    with pytest.raises(TutorConflict):engine.replace_script(state['session_id'],fresh,state['revision']-1,'stale-replace')
    with pytest.raises(TutorError):engine.replace_script(state['session_id'],'missing-guide',state['revision'],'foreign-replace')
    assert h.ctx.store.get('tutor_sessions',state['session_id'])['status']=='active'
    assert len(h.ctx.store.find('tutor_sessions',topic_id=seeded['genghis']['id']))==2  # seeded historical + current
    response=h.call('POST',f"/api/tutor/sessions/{state['session_id']}/replace-script",role='tutor',json={
        'guide_id':fresh,'expected_revision':state['revision'],'operation_id':'desktop-must-not-replace'})
    assert response.status_code==403
