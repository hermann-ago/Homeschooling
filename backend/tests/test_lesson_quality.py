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


def test_source_exercise_format_survives_portable_json_schema():
    from tutoring.book_companion import Exercise
    source=Exercise.model_validate({'id':'source-1','reference':'16','pages':[81],
        'prompt':'True or false: a triangle has four sides.','answer_format':'true_false'})
    restored=Exercise.model_validate_json(source.model_dump_json())
    assert restored.answer_format=='true_false'
    assert [c.id for c in restored.choices]==['true','false']
    with pytest.raises(ValueError):Exercise.model_validate({**source.model_dump(), 'choices':[{'id':'true','label':'True','correct':False}]})


def fixture(h):
    text='A tiny invented poem. The red kite meets the moon.'
    instruction='Circle the letter R.'
    data=make_pdf([[text,instruction]])
    path=h.add_file(data,'Books/Synthetic literacy.pdf')
    with h.ctx.store.transaction() as tx:
        child=tx.insert('children',{'name':'Practice learner'})
        subject=tx.insert('subjects',{'name':'Portuguese','child_id':child['id']})
        doc=tx.insert('documents',{'file_path':path,'original_filename':'Synthetic literacy.pdf','source':'drive',
            'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data),'page_count':1})
        topic=tx.insert('topics',{'subject_id':subject['id'],'document_id':doc['id'],'title':'Letter practice','page_start':1,'page_end':1})
    from tutoring.book_companion import native,persist
    body=native(data,'Synthetic literacy.pdf','textbook','')
    body['pages'][0].update(status='checked',review_method='visual',student_safe=True,issues=[],reading_blocks=[text])
    body['exercises']=[{'id':'original-task-1','reference':'1','section':'','pages':[1],'printed_page':'1','prompt':instruction,'kind':'handwritten','answer':None}]
    with h.ctx.store.transaction() as tx:persist(h.ctx,tx,subject['id'],doc,body,0)
    from tutoring.passages import load
    package=load(h.ctx,topic)
    manifest=lesson_quality.requirements(h.ctx,topic,package)
    plan={'mode':'tidy','segments':[{'type':'intro','text':'Let us look at a letter.'},
        {'type':'read','from':0,'to':0,'source_block_id':manifest['readings'][0]['id']},
        {'type':'activity','activity_kind':'explain_or_observe','content':{'text':instruction,
            'source_refs':[{'document_id':doc['id'],'page':1,'quote':instruction}]}},
        {'type':'recap','text':'You can return to any of these pages.'}]}
    return child,subject,topic,package,manifest,plan


def test_original_reading_is_inserted_by_id_and_references_remain_source_bound(harness):
    _,_,_,package,manifest,plan=fixture(harness)
    original=copy.deepcopy(plan)
    resolved=lesson_quality.resolve_readings(plan,manifest)
    assert plan==original
    built=guide.build(package['sentences'],resolved)
    result=lesson_quality.validate(built,manifest)
    assert result['readings_preserved']==1 and result['tasks_represented']==1
    reading=next(a for a in built['activities'] if a['kind']=='read_source')
    assert reading['content']['text']==manifest['readings'][0]['text']
    assert reading['source_refs'][0]['page']==1


def test_checked_shared_stem_and_visual_task_need_not_be_contiguous_reading(harness):
    _,_,topic,package,_,_=fixture(harness)
    from tutoring.book_companion import row_id
    doc=harness.ctx.store.get('documents',topic['document_id'])
    identity=row_id(doc['sha256'],'textbook')
    row=harness.ctx.store.get('book_companions',identity)
    body=copy.deepcopy(row['data'])
    body['exercises'][0]['prompt']='Copy each word from the table: sun, moon, kite.'
    with harness.ctx.store.transaction() as tx:tx.update('book_companions',identity,{'data':body})
    manifest=lesson_quality.requirements(harness.ctx,topic,package)
    assert manifest['tasks'][0]['instruction']==body['exercises'][0]['prompt']
    assert manifest['readings'][0]['text']=='A tiny invented poem. The red kite meets the moon.'
    body['pages'][0]['status']='needs_review'
    with harness.ctx.store.transaction() as tx:tx.update('book_companions',identity,{'data':body})
    assert lesson_quality.requirements(harness.ctx,topic,package)['tasks']==[]


@pytest.mark.parametrize('mutation',['omit','paraphrase','duplicate','no-task'])
def test_quality_checks_reject_missing_literature_and_tasks(harness,mutation):
    _,_,_,package,manifest,plan=fixture(harness)
    resolved=lesson_quality.resolve_readings(plan,manifest)
    if mutation=='omit':resolved['segments'].pop(1)
    if mutation=='paraphrase':resolved['segments'][1]['text']='Listen to the poem now.'
    if mutation=='duplicate':resolved['segments'].insert(2,copy.deepcopy(resolved['segments'][1]))
    if mutation=='no-task':resolved['segments'].pop(2)
    with pytest.raises(guide.GuideError):lesson_quality.validate(guide.build(package['sentences'],resolved),manifest)


def test_each_original_task_has_its_own_waiting_step(harness):
    _,_,_,package,manifest,plan=fixture(harness)
    manifest['tasks'].append({**manifest['tasks'][0],'id':'original-task-2','reference':'2'})
    with pytest.raises(ValueError,match='separate waiting activity'):
        guide.plan_schema(manifest).model_validate(plan)
    with pytest.raises(guide.GuideError,match='waiting activity'):
        lesson_quality.validate(guide.build(package['sentences'],lesson_quality.resolve_readings(plan,manifest)),manifest)
    plan['segments'].insert(3,copy.deepcopy(plan['segments'][2]))
    guide.plan_schema(manifest).model_validate(plan)
    assert lesson_quality.validate(guide.build(package['sentences'],lesson_quality.resolve_readings(plan,manifest)),manifest)['tasks_represented']==2


def test_registered_reading_and_split_instruction_citations_use_the_same_contract(harness):
    _,_,_,package,manifest,plan=fixture(harness)
    source=manifest['readings'][0]
    plan['segments'][1]={'type':'activity','activity_kind':'read_source','content':{
        'text':source['text'],'first':source['from'],'last':source['to'],
        'document_id':source['document_id'],'page':source['page']}}
    ref=plan['segments'][2]['content']['source_refs'][0]
    plan['segments'][2]['content']['source_refs']=[{**ref,'quote':'Circle the'},{**ref,'quote':'letter R.'}]
    original=copy.deepcopy(plan)
    validated=guide.plan_schema(manifest).model_validate(plan).model_dump(by_alias=True)
    assert plan==original and validated['segments'][1]['source_block_id']==source['id']
    built=guide.build(package['sentences'],lesson_quality.resolve_readings(validated,manifest))
    assert lesson_quality.validate(built,manifest)['tasks_represented']==1
    plan['segments'][1]['content']['text']='Listen to the poem.'
    with pytest.raises(ValueError,match='source_block_id'):
        guide.plan_schema(manifest).model_validate(plan)


def test_reading_adapter_does_not_accept_a_foreign_source_reference(harness):
    _,_,_,_,manifest,plan=fixture(harness)
    reading=manifest['readings'][0]
    plan['segments'][1]={'type':'activity','activity_kind':'read_source','content':{
        'text':reading['text'],'first':0,'last':0,'document_id':reading['document_id']+100}}
    with pytest.raises(ValueError,match='source_block_id'):
        guide.plan_schema(manifest).model_validate(plan)


def test_task_excerpt_requires_exact_substantial_unique_source_identity():
    task={'document_id':1,'page':2,'instruction':'Listen to the reading. Now find and mark each letter R.'}
    refs=[{'document_id':1,'page':2,'quote':'Now find and mark each letter R.'}]
    assert lesson_quality.task_matches(task,refs,[task])
    assert not lesson_quality.task_matches(task,[{**refs[0],'page':3}],[task])
    assert not lesson_quality.task_matches(task,[{**refs[0],'quote':'letter R'}],[task])
    other={**task,'instruction':'Draw one circle. Now find and mark each letter R.'}
    assert not lesson_quality.task_matches(task,refs,[task,other])


def test_provider_validator_rejects_omitted_source_content_before_voice_and_reuses_explicit_replacement(harness,monkeypatch):
    import json,httpx
    from services.ai_provider import AIService,InvalidStructuredResponseError
    _,_,_,_,manifest,plan=fixture(harness)
    schema=guide.plan_schema(manifest)
    invalid=copy.deepcopy(plan)
    invalid['segments'][1].pop('source_block_id');invalid['segments'][1]['text']='Listen to the poem.'
    monkeypatch.setenv('OPENAI_API_KEY','synthetic')
    calls=[]
    def reply(request):
        if request.url.path.endswith('/input_tokens'):return httpx.Response(200,json={'input_tokens':100})
        calls.append(request)
        value=invalid if len(calls)==1 else plan
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':100,'output_tokens':100},
            'output':[{'content':[{'type':'output_text','text':json.dumps(value)}]}]})
    ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(reply)))
    for _ in range(2):
        with pytest.raises(InvalidStructuredResponseError):ai.generate('Synthetic checked lesson',schema=schema)
    assert len(calls)==1
    assert ai.has_invalid_cached_reply('Synthetic checked lesson',schema=schema)
    result=ai.generate('Synthetic checked lesson',schema=schema,replace_invalid=True)
    assert result['segments'][1]['source_block_id']==manifest['readings'][0]['id']
    assert ai.generate('Synthetic checked lesson',schema=schema)==result
    assert len(calls)==2


def test_source_output_contract_shows_executable_read_segments_and_scopes_provider_ids(harness):
    import json
    _,_,_,_,manifest,_=fixture(harness)
    contract=guide.source_output_contract(manifest)
    reading=manifest['readings'][0]
    lines=contract.splitlines()
    expected=[{'type':'read','from':reading['from'],'to':reading['to'],
               'source_block_id':reading['id'],'text':None}]
    assert any(line==json.dumps(expected,ensure_ascii=False) for line in lines)
    assert manifest['tasks'][0]['instruction'] in contract
    schema=guide.plan_schema(manifest).provider_json_schema()
    assert schema['$defs']['ReadingPlanSegment']['properties']['source_block_id']['anyOf'][0]['enum']==[reading['id']]
    assert guide.source_output_contract({})==''


@pytest.mark.parametrize('instruction',['Escute a leitura. Agora encontre e assinale as letras.',
                                     'Listen to the poem. Then mark each letter.'])
def test_listen_then_work_pauses_follow_the_complete_reading(harness,instruction):
    _,_,_,package,manifest,plan=fixture(harness)
    task=manifest['tasks'][0];task['instruction']=instruction
    work=plan['segments'][2];work['content']['source_refs'][0]['quote']=instruction
    assert lesson_quality.task_reading_dependencies(task,manifest)==[manifest['readings'][0]['id']]
    guide.plan_schema(manifest).model_validate(plan)
    assert 'wait_after_readings' in guide.source_output_contract(manifest)
    wrong=copy.deepcopy(plan);wrong['segments'][1],wrong['segments'][2]=wrong['segments'][2],wrong['segments'][1]
    with pytest.raises(ValueError,match='after its required source reading'):
        guide.plan_schema(manifest).model_validate(wrong)
    with pytest.raises(guide.GuideError,match='wait after'):
        lesson_quality.validate(guide.build(package['sentences'],lesson_quality.resolve_readings(wrong,manifest)),manifest)
