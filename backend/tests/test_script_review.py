import copy
import json
import pytest
from storage.schema import TABLES
from tests.test_interactive import prepare, start, pause, change
from tests.test_tutoring import seed_history
from tutoring import script_review, source_annotations, skills


def note_payload(h,s,**extra):
    doc=h.ctx.store.get('documents',s['genghis']['document_id'])
    return {'document_id':doc['id'],'expected_sha256':doc['sha256'],'expected_version':0,
        'first_page':2,'last_page':2,'title':'A checked source clarification',
        'teaching_note':'Distinguish what this edition says from a checked correction.',
        'assessment_note':'Private exception: do not penalize a supported source correction.',
        'references':['https://example.org/original-source'],**extra}


def test_notes_reuse_exact_edition_across_subjects_but_not_other_pages_and_keep_versions(harness):
    h=harness;s=seed_history(h);subject=s['history']['id'];topic=s['genghis']
    path=f'/api/subjects/{subject}/source-notes';body=note_payload(h,s)
    result=h.call('PUT',path,json=body)
    assert result.status_code==200,result.text
    assert result.json()['version']==1 and (h.drive/result.json()['file_path']).exists()
    assert h.call('PUT',path,json=body).status_code==409
    assert h.call('GET',path,role='tutor').status_code==403
    assert 'assessment_note' not in source_annotations.packet(h.ctx.store,topic)[0]
    assert source_annotations.packet(h.ctx.store,topic,assessment=True)[0]['assessment_note']==body['assessment_note']
    assert 'assessment_note' not in h.ctx.tutor.context(s['lucas']['id'],subject)['source_annotations'][0]
    assert h.ctx.tutor.grading(topic,[1])['source_annotations'][0]['assessment_note']==body['assessment_note']
    assert not source_annotations.packet(h.ctx.store,s['conquest'])
    with h.ctx.store.transaction() as tx:
        other=tx.insert('subjects',{'child_id':s['lucas']['id'],'name':'Another subject'})
        other_topic=tx.insert('topics',{**{k:topic[k] for k in ('document_id','title','page_start','page_end','start_at','stop_before')},'subject_id':other['id']})
    assert source_annotations.packet(h.ctx.store,other_topic)==source_annotations.packet(h.ctx.store,topic)
    assert h.call('PUT',path,json={**body,'expected_version':1,'active':False}).status_code==200
    assert not source_annotations.packet(h.ctx.store,other_topic)
    h.restart()
    assert len(h.call('GET',path).json()['history'])==2
    assert TABLES['source_annotations'].teacher_only and TABLES['lesson_script_reviews'].teacher_only


def test_notes_reject_wrong_edition_out_of_range_and_unknown_book(harness):
    h=harness;s=seed_history(h);path=f"/api/subjects/{s['history']['id']}/source-notes"
    for extra in ({'expected_sha256':'0'*64},{'last_page':99},{'document_id':999}):
        assert h.call('PUT',path,json=note_payload(h,s,**extra)).status_code==400
    assert not h.ctx.store.all('source_annotations')


def test_automatic_review_is_saved_scoped_cached_and_private(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    row=h.ctx.store.get('guides',g['guide_id'])
    assert g['script_review']['status']=='approved'
    assert script_review.latest(h.ctx,row['id'])['method']=='ai'
    h.restart()
    assert script_review.status(h.ctx,row)['status']=='approved'
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**k:pytest.fail('Saved review must be reused'))
    assert script_review.run(h.ctx,row)['status']=='approved'
    script_review.require_audio(h.ctx,g)
    public=h.call('GET','/api/tutor/reader',params={'learner':s['lucas']['id'],'topic':s['genghis']['id']},role='learner').json()['guide']
    assert public['script_review']['status']=='approved'
    assert 'findings' not in public['script_review'] and 'input_sha256' not in public['script_review']
    assert h.call('GET',f"/api/tutor/guides/{row['id']}/review",role='tutor').status_code==403
    from tutoring.material_skills import save
    with h.ctx.store.transaction() as tx:save(h.ctx,tx,'script-review','Check source claims and waiting questions.',0)
    assert script_review.status(h.ctx,row)['status']=='outdated'
    with pytest.raises(ValueError,match='Audio has not'):script_review.require_audio(h.ctx,g)
    assert not h.ctx.store.all('activity_responses')


@pytest.mark.parametrize('category,status',[('task','needs_changes'),('factual','needs_source_review')])
def test_blocking_review_preserves_script_and_prevents_audio(harness,monkeypatch,category,status):
    h=harness;s,g=prepare(h,monkeypatch)
    row=h.ctx.store.get('guides',g['guide_id'])
    with h.ctx.store.transaction() as tx:tx.delete('lesson_script_reviews',script_review.latest(h.ctx,row['id'])['id'])
    def review(prompt,**kwargs):
        assert not h.ctx.store._lock._is_owned()
        assert issubclass(kwargs['schema'],script_review.Review)
        return {'findings':[{'category':category,'severity':'blocking','activity_ids':[g['activities'][0]['id']],
            'detail':'This turn needs adjustment.','suggestion':'Use the checked source and one clear instruction.'}]}
    monkeypatch.setattr(h.ctx.ai,'generate',review)
    result=script_review.run(h.ctx,row)
    assert result['status']==status
    from tutoring import narration
    with pytest.raises(ValueError,match='Audio has not'):narration.generate(h.ctx,s['genghis'],g)
    assert h.ctx.store.get('guides',row['id'])==row
    assert not h.ctx.store.all('attempts')


def test_review_schema_limits_findings_to_actual_activity_ids():
    schema=script_review.review_schema(['observe-1','question-2'])
    valid={'findings':[{'category':'pacing','severity':'advice','activity_ids':['observe-1'],
        'detail':'A synthetic observation.','suggestion':'Allow a little time.'}]}
    assert schema.model_validate(valid).findings[0].activity_ids==['observe-1']
    for bad in ['unknown','observe-1 support-SEPquestion-2']:
        with pytest.raises(ValueError):schema.model_validate({'findings':[{**valid['findings'][0],'activity_ids':[bad]}]})


def test_failed_review_exposes_provider_reason_without_discarding_saved_script(harness, monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    row=h.ctx.store.get('guides',g['guide_id'])
    data=script_review.inputs(h.ctx,row)
    script_review.save(h.ctx,row,data,{'findings':[],'error':'AI provider returned 429. Try again later.'},'ai')
    public=script_review.status(h.ctx,row)
    assert public['status']=='failed' and '429' in public['error']
    with pytest.raises(ValueError,match='429.*Audio has not been requested'):
        script_review.require_audio(h.ctx,g)
    assert h.ctx.store.get('guides',row['id'])==row


def test_reviewer_receives_real_acknowledgment_and_waiting_rules(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch);row=h.ctx.store.get('guides',g['guide_id'])
    with h.ctx.store.transaction() as tx:tx.delete('lesson_script_reviews',script_review.latest(h.ctx,row['id'])['id'])
    def inspect(prompt,**kwargs):
        assert 'acknowledge means the child must explicitly Continue' in prompt
        assert 'Ungraded gestures and observation' in prompt
        assert 'ENGINE RULES:' in prompt
        from tutoring.capture_policy import PREPARATION_INSTRUCTIONS
        assert PREPARATION_INSTRUCTIONS in prompt
        return {'findings':[]}
    monkeypatch.setattr(h.ctx.ai,'generate',inspect)
    assert script_review.run(h.ctx,row)['status']=='approved'


def test_failed_review_requires_explicit_retry_and_rejects_stale_inputs(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch);row=h.ctx.store.get('guides',g['guide_id'])
    with h.ctx.store.transaction() as tx:tx.delete('lesson_script_reviews',script_review.latest(h.ctx,row['id'])['id'])
    calls=[]
    def unavailable(*args,**kwargs):calls.append(1);raise ValueError('Synthetic provider unavailable')
    monkeypatch.setattr(h.ctx.ai,'generate',unavailable)
    assert script_review.run(h.ctx,row)['status']=='failed'
    assert script_review.run(h.ctx,row)['status']=='failed' and len(calls)==1
    base=f"/api/tutor/guides/{row['id']}/review"
    assert h.call('POST',base,json={'expected_input_sha256':'0'*64,'maximum_usd':.05}).status_code==409
    seen=[]
    def repaired(*args,**kwargs):
        from services.ai_provider import _generation_scope
        seen.append(_generation_scope.get());return {'findings':[]}
    monkeypatch.setattr(h.ctx.ai,'generate',repaired)
    digest=h.call('GET',base).json()['input_sha256']
    result=h.call('POST',base,json={'expected_input_sha256':digest,'maximum_usd':.05})
    assert result.status_code==200,result.text
    assert result.json()['status']['status']=='approved' and seen[0].startswith('script-review-')


def test_explicit_rewrite_receives_exact_editorial_feedback_without_auto_generation(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch);row=h.ctx.store.get('guides',g['guide_id'])
    finding={'category':'task','severity':'blocking','activity_ids':[g['activities'][0]['id']],
             'detail':'The opening illustrated page was omitted.','suggestion':'Present its models before the following page.'}
    script_review.save(h.ctx,row,script_review.inputs(h.ctx,row),{'findings':[finding]},'ai')
    feedback=script_review.revision_context(h.ctx,row)
    assert feedback['findings']==[finding]
    assert feedback['previous_activities'][0]['id']==g['activities'][0]['id']
    prompts=[]
    from tutoring import guide
    writer=guide.write_plan
    monkeypatch.setattr(guide,'write_plan',lambda text,models,**kw:(prompts.append(text) or writer(text,models,**kw)))
    made=h.call('POST','/api/tutor/reader/guide',json={
        'learner':s['lucas']['id'],'topic':s['genghis']['id'],'rewrite':True,'prepare_voice':False})
    assert made.status_code==200,made.text
    assert len(prompts)==1 and finding['detail'] in prompts[0] and 'REVISION FEEDBACK' in prompts[0]
    assert not h.ctx.store.all('attempts')


def test_rewrite_keeps_earlier_source_corrections_and_can_address_approved_advice(harness,monkeypatch):
    h=harness;_,g=prepare(h,monkeypatch);row=h.ctx.store.get('guides',g['guide_id'])
    earlier={'category':'task','severity':'blocking','activity_ids':[],
             'detail':'Do not omit the middle picture column.','suggestion':'Inspect all columns.'}
    context={**row['context_snapshot'],'review_feedback':{'source_sha256':row['source_sha256'],
             'findings':[earlier],'earlier_corrections':[]}}
    with h.ctx.store.transaction() as tx:row=tx.update('guides',row['id'],{'context_snapshot':context})
    advice={'category':'pacing','severity':'advice','activity_ids':[g['activities'][0]['id']],
            'detail':'The direction is repeated.','suggestion':'Use only the waiting activity.'}
    report=script_review.save(h.ctx,row,script_review.inputs(h.ctx,row),{'findings':[advice]},'ai')
    assert report['status']=='approved'
    feedback=script_review.revision_context(h.ctx,row)
    assert feedback['findings']==[advice] and feedback['earlier_corrections']==[earlier]
    context['review_feedback']['source_sha256']='0'*64
    with h.ctx.store.transaction() as tx:row=tx.update('guides',row['id'],{'context_snapshot':context})
    assert script_review.revision_context(h.ctx,row)['earlier_corrections']==[]


def test_legacy_revision_chain_retains_a_previously_fixed_visual_omission(harness,monkeypatch):
    h=harness;_,g=prepare(h,monkeypatch);first=h.ctx.store.get('guides',g['guide_id'])
    visual={'category':'task','severity':'blocking','activity_ids':[],
            'detail':'Include the middle pictures.','suggestion':'Consider every column.'}
    order={'category':'task','severity':'blocking','activity_ids':[],
           'detail':'Listen before marking.','suggestion':'Move the work pause after the poem.'}
    with h.ctx.store.transaction() as tx:
        second=tx.insert('guides',{**first,'id':'synthetic-revision-two','context_snapshot':{
            **first['context_snapshot'],'review_feedback':{'guide_id':first['id'],'findings':[visual]}}})
        third=tx.insert('guides',{**first,'id':'synthetic-revision-three','context_snapshot':{
            **first['context_snapshot'],'review_feedback':{'guide_id':second['id'],'findings':[order]}}})
    script_review.save(h.ctx,third,script_review.inputs(h.ctx,third),{'findings':[]},'ai')
    feedback=script_review.revision_context(h.ctx,third)
    assert order in feedback['earlier_corrections'] and visual in feedback['earlier_corrections']


def test_scoped_notes_reach_planner_and_frozen_feedback_without_leaking_to_child(harness,monkeypatch):
    h=harness;s,g=prepare(h,monkeypatch)
    body=note_payload(h,s)
    assert h.call('PUT',f"/api/subjects/{s['history']['id']}/source-notes",json=body).status_code==200
    assert not h.ctx.tutor.guide(s['genghis'],h.ctx.store.get('guides',g['guide_id'])['source_snapshot'])['current']
    # Reuse source-valid segments through the same family-reviewed import path.
    old=h.ctx.store.get('guides',g['guide_id']);content=json.loads(h.ctx.file_bytes(old['guide_path']))
    segments=[{k:v for k,v in seg.items() if k in ('type','text','from','to','action_kind')} for seg in content['segments']]
    payload={'learner':s['lucas']['id'],'topic':s['genghis']['id'],'source_sha256':old['source_sha256'],
        'expected_skill_version':skills.current(h.ctx.store,s['history']['id'])['version'],
        'plan':{'mode':'expand','segments':segments}}
    imported=h.call('POST','/api/tutor/reader/guide/import',json=payload)
    assert imported.status_code==200,imported.text
    g=imported.json();saved=h.ctx.store.get('guides',g['guide_id'])
    assert saved['context_snapshot']['source_annotations'][0]['teaching_note']==body['teaching_note']
    assert 'assessment_note' not in saved['context_snapshot']['source_annotations'][0]
    assert saved['context_snapshot']['source_assessment_notes'][0]['assessment_note']==body['assessment_note']
    state=pause(h,start(h,s,g),g)
    # Editing a note now must not silently reinterpret an existing student's work.
    h.call('PUT',f"/api/subjects/{s['history']['id']}/source-notes",json={**body,'expected_version':1,'assessment_note':'A later exception.'})
    prompts=[]
    from tutoring import interactive
    monkeypatch.setattr(interactive,'gemini_turn',lambda text,images,models:prompts.append(text) or {'feedback':'Thank you.','result':'Source disputed','ready_to_continue':True})
    change(h,state,'answer',action_id='action-1',message_id='frozen-note-check',text='An actual synthetic answer')
    assert body['assessment_note'] in prompts[0] and 'A later exception.' not in prompts[0]
    assert body['assessment_note'] not in json.dumps(h.call('GET','/api/tutor/reader',params={
        'learner':s['lucas']['id'],'topic':s['genghis']['id']},role='learner').json())
