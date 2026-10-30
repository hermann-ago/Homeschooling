"""Preparation units are source evidence, not compulsory extra learner clicks."""
import copy
import pytest

from tutoring import guide,lesson_quality
from tutoring.answer_controls import binary_subitems,book_controls


def test_checked_title_story_and_attribution_are_one_turn_with_all_provenance():
    source=[{'text':x} for x in ('An invented fable.','A wren helped a bear.','An invented author.')]
    readings=[{'id':f'r{i}','document_id':4,'page':1+i//2,'text':s['text'],'from':i,'to':i}
              for i,s in enumerate(source)]
    manifest={'readings':readings,'tasks':[],'checked_pages':[1,2]}
    plan={'mode':'tidy','segments':[{'type':'intro','text':'Let us listen.'},
        *[{'type':'read','from':r['from'],'to':r['to'],'source_block_id':r['id']} for r in readings],
        {'type':'action','text':'Who helped whom?','action_kind':'answer'}]}
    resolved=lesson_quality.resolve_readings(plan,manifest);original=copy.deepcopy(resolved)
    compiled=lesson_quality.coherent_readings(resolved)
    assert resolved==original
    assert compiled['segments'][1]['source_block_ids']==['r0','r1','r2']
    assert [r['page'] for r in compiled['segments'][1]['source_refs']]==[1,1,2]
    built=guide.build(source,compiled)
    assert len(built['activities'])==3 and built['activities'][-1]['content']['prompt']=='Who helped whom?'
    assert lesson_quality.validate(built,manifest)['readings_preserved']==3
    # A saved guide is never silently regrouped when it is loaded again.
    old=guide.build(source,resolved)
    assert len(guide.guide_activities(old))==5
    overlapping=copy.deepcopy(resolved)
    overlapping['segments'][2]['from']=0
    assert len(lesson_quality.coherent_readings(overlapping)['segments'])==3


def test_reading_compilation_never_crosses_work_or_unchecked_gaps():
    plan={'segments':[{'type':'read','from':0,'to':0,'text':'One.','source_block_id':'r1'},
        {'type':'read','from':2,'to':2,'text':'Three.','source_block_id':'r3'},
        {'type':'action','text':'Your turn.','action_kind':'answer'},
        {'type':'read','from':3,'to':3,'text':'Four.','source_block_id':'r4'},
        {'type':'read','from':4,'to':4,'text':'Unverified.'}]}
    assert lesson_quality.coherent_readings(plan)==plan


def test_checked_typography_uses_exact_transcription_without_inventing_words():
    original='A\no tiny bird fi nally learned the mean-\ning.'
    correct='Ao tiny bird finally learned the meaning.'
    page={'elements':[{'kind':'text','text':correct}]}
    assert lesson_quality.checked_reading_text(original,page)==correct
    assert lesson_quality.checked_reading_text(original,{'elements':[{'kind':'text','text':correct.replace('bird','bear')}]})==original
    assert lesson_quality.checked_reading_text('A well-known bird.',{'elements':[{'kind':'text','text':'A wellknown bird.'}]})=='A well-known bird.'


def test_binary_statement_list_keeps_each_item_and_its_original_instruction():
    task={'id':'checked-list','pages':[13],'reference':'Reading','prompt':
        'Decida se é verdadeira ou falsa:\nA small bird helped.\nThe bear flew.'}
    parts=binary_subitems(task)
    assert [p['id'] for p in parts]==['checked-list:statement-1','checked-list:statement-2']
    assert all(p['prompt'].startswith('Decida se é verdadeira ou falsa:\n') for p in parts)
    assert parts[1]['prompt'].endswith('The bear flew.')
    assert book_controls(parts[0])['choices']==[{'id':'true','label':'Verdadeiro'},{'id':'false','label':'Falso'}]
    assert book_controls(task)=={}  # never one binary selector for a whole list
    ambiguous={**task,'prompt':'True or false:\nA bird with a\nvery long name helped.'}
    assert binary_subitems(ambiguous)==[ambiguous]


def test_preparation_context_supplies_family_and_source_contract_once():
    text=guide.prompt({'title':'A fable','sentences':[{'text':'A bird helped.'}]},subject='Literacy',
        learner='Practice learner',grade='3',language='en-US',learner_context={
            'family_tutoring':{'content':'UNIQUE-FAMILY-STYLE','learner_profile':{}},
            'source_requirements':{'readings':[{'id':'story','from':0,'to':0}],'tasks':[]}})
    assert text.count('UNIQUE-FAMILY-STYLE')==1
    assert 'source_block_id' in text and 'source_requirements' not in text


def test_new_preparation_uses_checked_typography_and_individual_binary_items(harness):
    from tests.test_lesson_quality import fixture
    from tutoring.book_companion import row_id
    _,subject,topic,package,_,_=fixture(harness)
    doc=harness.ctx.store.get('documents',topic['document_id'])
    rid=row_id(doc['sha256'],'textbook')
    row=harness.ctx.store.get('book_companions',rid)
    body=copy.deepcopy(row['data'])
    body['pages'][0]['reading_blocks']=['A tiny invented poem. The red kite meets the moon.']
    body['pages'][0]['elements']=[{'kind':'text','text':'A tiny invented poem.\nThe red kite meets the moon.'}]
    body['exercises']=[{'id':'binary-set','reference':'1','section':'','pages':[1],
        'prompt':'True or false:\nA kite meets the moon.\nThe kite is green.','kind':'activity','answer':None}]
    with harness.ctx.store.transaction() as tx:tx.update('book_companions',rid,{'data':body})
    manifest=lesson_quality.requirements(harness.ctx,topic,package)
    assert manifest['readings'][0]['typography']=='equivalent_checked_transcription'
    assert len(manifest['tasks'])==2
    assert all(t['answer_format']=='true_false' for t in manifest['tasks'])
    source=guide.book_work_source(harness.ctx,topic,package)
    part=manifest['tasks'][1]
    plan={'mode':'tidy','segments':[
        {'type':'read','from':0,'to':1,'source_block_id':manifest['readings'][0]['id']},
        *[{'type':'activity','activity_kind':'request_book_work','content':{
            'prompt':task['instruction'],'response_modes':['text'],
            'source_refs':[{'document_id':doc['id'],'page':1,'quote':task['instruction']}]
        }} for task in manifest['tasks']]]}
    plan=lesson_quality.resolve_readings(plan,manifest)
    plan=guide.sanitize_planner_activities(plan,book_source=source)
    plan=lesson_quality.bind_tasks(plan,manifest)
    built=guide.build(package['sentences'],lesson_quality.coherent_readings(plan))
    assert lesson_quality.validate(built,manifest)['tasks_represented']==2
    assert built['activities'][2]['content']['answer_format']=='true_false'
    assert built['activities'][2]['source_refs'] or built['activities'][2]['content']['source_refs']


def test_layout_update_versions_the_api_script_without_purchasing_or_changing_records(harness,monkeypatch):
    from tests.test_lesson_quality import fixture
    from tutoring import skills,script_review
    h=harness;_,subject,topic,package,manifest,plan=fixture(h)
    reading=manifest['readings'][0]
    # Simulate an older approved plan with two checked source blocks in one
    # flattened sentence, the exact title/story boundary found in the pilot.
    first,rest=reading['text'].split('. ',1)
    manifest['readings']=[{**reading,'id':'title','text':first+'.','from':0,'to':0},
                         {**reading,'id':'body','text':rest,'from':0,'to':1}]
    plan['segments'][1:2]=[{'type':'read','source_block_id':r['id'],'from':r['from'],'to':r['to']}
                          for r in manifest['readings']]
    original=guide.build(package['sentences'],lesson_quality.resolve_readings(plan,manifest))
    original['source_coverage']=lesson_quality.validate(original,manifest)
    skill=skills.packet(h.ctx.store,subject)
    with h.ctx.store.transaction() as tx:
        row=guide.save(tx,topic,package,original,model='original-api-model',language='en-US',skill=skill,
                       learner_context={'source_requirements':manifest})
    row=h.ctx.store.get('guides',row['id'])
    script_review.run(h.ctx,row,human=True)
    before={t:copy.deepcopy(h.ctx.store.all(t)) for t in ('attempts','tutor_sessions','lesson_playback','activity_responses')}
    monkeypatch.setattr(h.ctx.ai,'generate',lambda *a,**kw:pytest.fail('Layout cannot buy generation'))
    url=f"/api/tutor/guides/{row['id']}/reading-layout"
    assert h.call('POST',url,json={'expected_sha256':'0'*64}).status_code==400
    response=h.call('POST',url,json={'expected_sha256':row['guide_sha256']},key='reading-layout-once')
    assert response.status_code==200,response.text
    new=response.json()
    assert new['guide_id']!=row['id'] and new['model']=='original-api-model'
    assert len(new['activities'])==len(original['activities'])-1
    assert new['script_review']['method']=='layout_review' and new['script_review']['status']=='approved'
    assert new['source_coverage']['readings_preserved']==2
    assert before=={t:h.ctx.store.all(t) for t in before}
    assert h.ctx.store.get('guides',row['id'])==row
    assert h.call('POST',url,json={'expected_sha256':row['guide_sha256']},key='reading-layout-once').json()==new
    assert h.call('POST',url,json={'expected_sha256':row['guide_sha256']},role='tutor').status_code==403
