from datetime import date
import pytest

from tests.test_tutoring import seed_history
from tests.test_interactive import prepare, start
from tutoring import family_skill, guide as guide_mod


def test_shared_skill_versions_ages_and_files_survive_restart(harness):
    h=harness
    seeded=seed_history(h)
    initial=h.call('GET','/api/tutor/teaching-style').json()
    child=seeded['lucas']['id']
    body={'content':initial['skill']['content']+'\nAllow a quiet moment to think.',
          'profiles':{str(child):{'age':9,'as_of':date.today().isoformat()}},'expected_version':0}
    saved=h.call('PUT','/api/tutor/teaching-style',json=body)
    assert saved.status_code==200, saved.text
    assert saved.json()['version']==1
    assert (h.drive/saved.json()['file_path']).is_file()
    assert h.call('PUT','/api/tutor/teaching-style',json=body).status_code==409
    assert h.call('PUT','/api/tutor/teaching-style',role='tutor',json=body).status_code==403
    h.restart()
    inventory=h.call('GET','/api/tutor/teaching-style').json()
    assert [r['version'] for r in inventory['history']]==[1,0]
    assert inventory['skill']['profiles']==body['profiles']
    assert not h.ctx.store.all('activity_responses')


@pytest.mark.parametrize('profile', [{'age':True,'as_of':None},{'age':-1,'as_of':None},
                                     {'birth_year':True},{'birth_year':date.today().year+1},
                                     {'birth_year':date.today().year-6,'age':6},
                                     {'birth_date':'bad-date'},{'birth_date':'2999-01-01'},
                                     {'birth_date':'2017-05-19','age':9},
                                     {'age':9,'as_of':'bad-date'},{'age':9,'as_of':'2999-01-01'}])
def test_invalid_profile_does_not_save_partial_versions(harness,profile):
    seeded=seed_history(harness)
    response=harness.call('PUT','/api/tutor/teaching-style',json={'content':'Teach naturally.',
       'profiles':{str(seeded['lucas']['id']):profile},'expected_version':0})
    assert response.status_code==400
    assert not harness.ctx.store.all('family_tutor_skills')


def test_birth_year_is_preserved_and_only_a_range_reaches_the_tutor(harness):
    h=harness; seeded=seed_history(h); child=seeded['lucas']['id']
    year=date.today().year
    with h.ctx.store.transaction() as tx:
        family_skill.save(tx,'Use age-aware language.',{str(child):{'birth_year':year-9,'as_of':date.today().isoformat()}},0)
    profile=family_skill.packet(h.ctx.store,child)['learner_profile']
    assert profile['birth_year']==year-9
    assert profile['age_range']==[8,9] and profile['age_range_year']==year
    assert 'age' not in profile and 'birth_date' not in profile
    assert 'age_range' not in family_skill.current(h.ctx.store)['profiles'][str(child)]
    h.restart()
    assert family_skill.packet(h.ctx.store,child)['learner_profile']==profile
    with h.ctx.store.transaction() as tx:
        family_skill.save(tx,'Use age-aware language.',{str(child):{'birth_year':year}},1)
    assert family_skill.packet(h.ctx.store,child)['learner_profile']['age_range']==[0,0]


def test_exact_birthday_updates_age_at_the_birthday_without_rewriting_saved_profile(harness,monkeypatch):
    h=harness; seeded=seed_history(h); child=seeded['lucas']['id']
    class ClockDate(date):
        now=date(2026,10,21)
        @classmethod
        def today(cls):return cls.now
    monkeypatch.setattr(family_skill,'date',ClockDate)
    with h.ctx.store.transaction() as tx:
        family_skill.save(tx,'Use age-aware language.',{str(child):{'birth_date':'2025-10-25','as_of':'2026-10-21'}},0)
    before=family_skill.packet(h.ctx.store,child)
    assert before['learner_profile']['age']==0
    assert before['learner_profile']['age_basis']=='birth_date'
    ClockDate.now=date(2026,10,24)
    assert family_skill.packet(h.ctx.store,child)['sha256']==before['sha256']
    ClockDate.now=date(2026,10,25)
    assert family_skill.packet(h.ctx.store,child)['learner_profile']['age']==1
    assert family_skill.packet(h.ctx.store,child)['sha256']!=before['sha256']
    assert family_skill.current(h.ctx.store)['profiles'][str(child)]=={'birth_date':'2025-10-25','as_of':'2026-10-21'}


def test_age_context_selects_only_its_learner_and_does_not_change_with_sibling(harness):
    h=harness; seeded=seed_history(h)
    with h.ctx.store.transaction() as tx:
        other=tx.insert('children',{'name':'Synthetic younger learner'})
        family_skill.save(tx,'Shared teaching style.',{str(seeded['lucas']['id']):{'age':9,'as_of':None},
             str(other['id']):{'age':6,'as_of':None}},0)
    packet=family_skill.packet(h.ctx.store,seeded['lucas']['id'])
    assert packet['learner_profile']=={'age':9,'as_of':None}
    assert 'Synthetic younger learner' not in family_skill.instructions(packet)
    with h.ctx.store.transaction() as tx:
        profiles={**family_skill.current(tx)['profiles'],str(other['id']):{'age':7,'as_of':None}}
        family_skill.save(tx,'Shared teaching style.',profiles,1)
    assert family_skill.packet(h.ctx.store,seeded['lucas']['id'])['sha256']==packet['sha256']


def test_preparation_and_live_feedback_pin_shared_style_and_age(harness,monkeypatch):
    h=harness; seeded,first=prepare(h,monkeypatch)
    initial=family_skill.current(h.ctx.store)
    child=seeded['lucas']['id']
    content=initial['content']+'\nFROZEN-FRIENDLY-STYLE'
    body={'content':content,'profiles':{str(child):{'age':9,'as_of':None}},'expected_version':0}
    assert h.call('PUT','/api/tutor/teaching-style',json=body).status_code==200
    plan_writer=guide_mod.write_plan
    prompts=[]
    monkeypatch.setattr(guide_mod,'write_plan',lambda text,models,**kwargs:(prompts.append(text) or plan_writer(text,models,**kwargs)))
    made=h.call('POST','/api/tutor/reader/guide',json={'learner':child,'topic':seeded['genghis']['id'],'rewrite':True})
    assert made.status_code==200,made.text
    assert 'FROZEN-FRIENDLY-STYLE' in prompts[0] and '"age": 9' in prompts[0]
    prepared=made.json();state=start(h,seeded,prepared)
    assert h.call('PUT','/api/tutor/teaching-style',json={**body,'content':content.replace('FROZEN-FRIENDLY-STYLE','NEW-STYLE'),
       'expected_version':1}).status_code==200
    params={'learner':child,'topic':seeded['genghis']['id']}
    assert not h.call('GET','/api/tutor/reader',params=params).json()['guide']['current']
    assert h.call('GET','/api/tutor/reader',params={**params,'session':state['session_id']}).json()['guide']['current']
    session=h.ctx.store.get('tutor_sessions',state['session_id'])
    action=h.ctx.store.find('lesson_actions',session_id=session['id'])[0]
    prompt,_,_=h.ctx.tutor.interactive._prompt(session,action,{'id':'synthetic-probe','evidence_ids':[]})
    assert 'FROZEN-FRIENDLY-STYLE' in prompt and 'NEW-STYLE' not in prompt
    assert not h.ctx.store.find('attempts',session_id=session['id'])


def test_shared_skill_changes_in_test_mode_stay_isolated(harness):
    from services.test_mode import compatible_topic, manager
    from tests.test_test_mode import enter, call
    h=harness; seeded=seed_history(h)
    h.ctx._assign_subject_folders();h.ctx.books.backfill()
    from tutoring import skills
    skills.ensure(h.ctx)
    token=enter(h); test=manager(h.ctx).get(token)
    body={'content':'Only for this synthetic rehearsal.','profiles':{},'expected_version':0}
    result=call(h,'PUT','/api/tutor/teaching-style',token,json=body)
    assert result.status_code==200,result.text
    assert family_skill.current(h.ctx.store)['version']==0
    assert family_skill.current(test.store)['version']==1
    assert not compatible_topic(test,seeded['genghis']['id'])


def test_script_preview_does_not_schedule_paid_voice(harness,monkeypatch):
    from tutoring import narration
    h=harness;seeded,_=prepare(h,monkeypatch)
    calls=[]
    h.config.update(tts={'enabled':True,'provider':'google-gemini','voice':'Achird','rate':.9})
    monkeypatch.setattr(narration,'generate',lambda *args,**kwargs:calls.append(True))
    response=h.call('POST','/api/tutor/reader/guide',json={'learner':seeded['lucas']['id'],
        'topic':seeded['genghis']['id'],'rewrite':True,'prepare_voice':False})
    assert response.status_code==200,response.text
    assert not calls and not h.ctx.ai.ledger.jobs()
