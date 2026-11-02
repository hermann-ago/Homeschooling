"""Natural authoring is compiled locally; actual child evidence stays engine-owned."""
import copy
import json

import httpx
import pytest
from pydantic import ValidationError

from services.ai_provider import strict_schema, PREPARATION_MODEL
from tutoring import guide, lesson_quality, teaching_script as writer


def source():
    passage={'title':'An invented fable','sentences':[{'text':v} for v in (
        'The bear and the wren.','A wren freed a bear.','An invented author.','Write these words.') ]}
    manifest={'checked_pages':[1,2],'readings':[
        {'id':f'r{i}','document_id':3,'page':1+i//2,'text':s['text'],'from':i,'to':i}
        for i,s in enumerate(passage['sentences'][:3])],
        'tasks':[{'id':f'w{i}','document_id':3,'page':2,'reference':str(i),
                  'instruction':f'Write the word with its accent: {word}.','answer_format':'text','choices':[]}
                 for i,word in enumerate(('leao','limoes'))]}
    script={'welcome':'Olá! Vamos descobrir como alguém bem pequeno pode ajudar.',
        'turns':[{'type':'read','reading_ids':['r0','r1','r2']},
            {'type':'ask','purpose':'retelling','prompt':'Por que a ave ajudou o urso?'},
            {'type':'say','text':'O til ajuda a mostrar um som nasal. Vamos observar esse sinal com calma.'},
            {'type':'practice','items':[{'task_id':t['id'],'prompt':t['instruction'],
                'response':{'format':'spelling'}} for t in manifest['tasks']]}],
        'closing':'Você pode voltar à história quando quiser.'}
    return passage,manifest,script


def compile_and_build(passage,manifest,script):
    plan=writer.compile_script(script,passage,manifest,'pt-BR')
    resolved=lesson_quality.coherent_readings(lesson_quality.resolve_readings(plan,manifest))
    return guide.build(passage['sentences'],resolved,faithful=True,instruction_only=not manifest['readings'])


def test_complete_reading_is_one_turn_and_words_tasks_and_options_survive():
    passage,manifest,script=source();original=copy.deepcopy(script)
    # Longer explanations must not be clipped to the old 700-character limit.
    script['turns'][2]['text']='Uma explicação com espaço para respirar. '*25+'Este final precisa ser preservado.'
    built=compile_and_build(passage,manifest,script)
    assert len([a for a in built['activities'] if a['kind']=='read_source'])==1
    assert built['segments'][0]['text']==script['welcome']
    assert built['segments'][3]['text']==script['turns'][2]['text']
    assert built['segments'][-1]['text']==script['closing']
    assert lesson_quality.validate(built,manifest)['tasks_represented']==2
    work=[a for a in built['activities'] if a['kind']=='request_book_work']
    assert [a['content']['prompt'] for a in work]==[i['prompt'] for i in original['turns'][-1]['items']]
    assert all(a['origin']=='required_book' and a['content']['evidence_requirement']=='spelling' for a in work)
    assert all(a['content']['response_modes']==['text','photo'] for a in work)
    assert work[0]['source_refs']==[{'document_id':3,'page':2,'quote':manifest['tasks'][0]['instruction']}]


@pytest.mark.parametrize('change',['missing-reading','reordered-reading','duplicate-reading','missing-task','duplicate-task','unknown-task','unknown-reading'])
def test_source_bound_reply_fails_before_accepted_cache_without_inventing_repairs(change):
    passage,manifest,script=source()
    if change=='missing-reading':script['turns'][0]['reading_ids'].pop()
    if change=='reordered-reading':script['turns'][0]['reading_ids'].reverse()
    if change=='duplicate-reading':script['turns'][0]['reading_ids'].append('r2')
    if change=='missing-task':script['turns'][-1]['items'].pop()
    if change=='duplicate-task':script['turns'][-1]['items'].append(copy.deepcopy(script['turns'][-1]['items'][0]))
    if change=='unknown-task':script['turns'][-1]['items'][0]['task_id']='not-assigned'
    if change=='unknown-reading':script['turns'][0]['reading_ids'][0]='not-assigned'
    with pytest.raises(ValidationError):writer.schema(passage,manifest,'pt-BR').model_validate(script)


def test_listen_then_work_cannot_be_placed_before_the_reading():
    passage,manifest,script=source()
    manifest['tasks'][0]['instruction']='Ouça o poema e depois escreva a palavra.'
    manifest['tasks'][0]['page']=1
    script['turns'].insert(0,script['turns'].pop())
    with pytest.raises(ValidationError,match='listening'):writer.schema(passage,manifest,'pt-BR').model_validate(script)


def test_checked_book_controls_override_writer_choices_without_revealing_key():
    passage,manifest,script=source()
    task=manifest['tasks'][0]
    task.update(answer_format='true_false',choices=[{'id':'true','label':'Verdadeiro'},{'id':'false','label':'Falso'}])
    script['turns'][-1]['items'][0]['response']={'format':'single_choice','choices':['Wrong option','Another option']}
    compiled=writer.compile_script(script,passage,manifest,'pt-BR')
    work=[s for s in compiled['segments'] if s.get('activity_kind')=='request_book_work'][0]
    assert work['content']['choices']==task['choices']
    assert work['content']['answer_format']=='true_false'


def test_matching_keeps_both_columns_and_handwriting_remains_distinct():
    passage,manifest,script=source()
    script['turns'][-1]['items'][0]['response']={'format':'matching',
        'matching_items':['Bird','Fish'],'matching_options':['Water','Air']}
    script['turns'][-1]['items'][1]['response']={'format':'handwriting'}
    plan=writer.compile_script(script,passage,manifest,'en-US')
    work=[s['content'] for s in plan['segments'] if s.get('activity_kind')=='request_book_work']
    assert [v['label'] for v in work[0]['matching']['options']]==['Water','Air']
    assert not any('correct' in v for v in work[0]['matching']['options'])
    assert work[1]['response_modes']==['photo','parent_review'] and work[1]['evidence_requirement']=='handwriting'


def test_instruction_only_worksheet_does_not_invent_reading_or_discussion():
    passage,manifest,script=source();manifest['readings']=[]
    script['turns']=script['turns'][-1:]
    built=compile_and_build(passage,manifest,script)
    assert [a['kind'] for a in built['activities']]==['introduce','request_book_work','request_book_work','close_lesson']
    assert lesson_quality.validate(built,manifest)['tasks_represented']==2


def test_unindexed_text_fallback_covers_actual_sentences_once_without_silent_tail():
    passage,_,_=source();manifest={'readings':[],'tasks':[],'checked_pages':[]}
    script={'welcome':'Let us read.','turns':[{'type':'read','first':0,'last':3}], 'closing':'We reached our stopping place.'}
    built=compile_and_build(passage,manifest,script)
    assert [s['source'] for s in built['sentences'] if s['kind']=='book']==[0,1,2,3]
    script['turns'][0]['last']=2
    with pytest.raises(ValidationError,match='complete'):writer.schema(passage,manifest,'en-US').model_validate(script)


def test_authoring_schema_excludes_engine_ids_evidence_jobs_and_private_answers():
    schema=json.dumps(strict_schema(writer.TeachingScript))
    legacy=json.dumps(strict_schema(guide.GuidePlan))
    for field in ('response_modes','activity_kind','source_refs','exercise_id','parent_activity_id','correct_answer','revision'):
        assert field not in schema
    assert len(schema)<len(legacy)/4
    passage,manifest,script=source()
    with pytest.raises(ValidationError):writer.TeachingScript.model_validate({**script,'commands':['advance']})
    script['turns'][1]['prompt']='<script>run()</script>'
    with pytest.raises(ValidationError):writer.TeachingScript.model_validate(script)


@pytest.mark.parametrize('style_advice',[False,True])
def test_application_prepares_with_new_writer_schema_and_keeps_source_script_private(harness,monkeypatch,style_advice):
    from tests.test_lesson_quality import fixture
    from tutoring.script_review import Review
    h=harness;child,_,topic,package,manifest,_=fixture(h)
    script={'welcome':'Vamos ouvir uma história e olhar uma letra.',
        'turns':[{'type':'read','first':manifest['readings'][0]['from'],'last':manifest['readings'][0]['to']},
            {'type':'book_work','document_id':topic['document_id'],'page':package['pdf_pages']['start'],
                'prompt':'Aponte a letra R no livro.','response':{'format':'observe'}}],
        'closing':'Podemos voltar a essas palavras depois.'}
    calls=[]
    def generate(prompt,**kwargs):
        calls.append(kwargs)
        schema=kwargs['schema']
        assert kwargs.get('pdf') and not h.ctx.store._lock._is_owned()
        if issubclass(schema,Review):
            assert 'FOCUSED SCRIPT CHECK' in prompt
            assert 'Reserve source_conflict for a genuine disagreement' in prompt
            assert 'Never classify a missing printed example alone as a source dispute' in prompt
            return {'findings':[{'category':'tone','severity':'blocking','activity_ids':[],
                'detail':'I would prefer a shorter welcome.','suggestion':'Shorten it.'}] if style_advice else []}
        from tutoring.page_script import Script
        assert issubclass(schema,Script)
        assert 'OUTPUT FORMAT' in prompt and 'activity_kind' not in prompt
        return schema.model_validate(script).model_dump()
    monkeypatch.setattr(h.ctx.ai,'generate',generate)
    before={t:copy.deepcopy(h.ctx.store.all(t)) for t in ('attempts','tutor_sessions','lesson_playback','activity_responses')}
    response=h.call('POST','/api/tutor/reader/guide',json={'learner':child['id'],'topic':topic['id'],'prepare_voice':False})
    assert response.status_code==200,response.text
    saved=response.json();assert saved['script_review']['status']=='approved'
    assert saved['source_coverage']['readings_preserved']==0  # No pre-extracted coverage inventory.
    assert [a['kind'] for a in saved['activities']]==['introduce','read_source','explain_or_observe','close_lesson']
    frozen=h.ctx.store.get('guides',saved['guide_id'])['context_snapshot']
    assert frozen['preparation_policy']=='original-pages-3' and frozen['teaching_script']['script']['welcome']==script['welcome']
    if style_advice:
        from tutoring.script_review import latest
        assert saved['script_review']['advice_count']==1
        reviewed=latest(h.ctx,saved['guide_id'])['data']
        assert reviewed['findings'][0]['severity']=='advice' and reviewed['style_proposals'][0]['severity']=='blocking'
    assert 'teaching_script' not in response.text and 'task_id' not in response.text
    count=len(calls)
    assert h.call('POST','/api/tutor/reader/guide',json={'learner':child['id'],'topic':topic['id'],'prepare_voice':False}).json()['guide_id']==saved['guide_id']
    assert len(calls)==count==2
    assert before=={t:h.ctx.store.all(t) for t in before}


def test_real_provider_adapter_uses_high_reasoning_and_reuses_authored_reply(harness,monkeypatch):
    h=harness;passage,manifest,script=source();requests=[]
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-test-only')
    def respond(request):
        body=json.loads(request.content)
        if request.url.path.endswith('/input_tokens'):return httpx.Response(200,json={'input_tokens':100})
        requests.append(body)
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':100,'output_tokens':150},
            'output':[{'content':[{'type':'output_text','text':json.dumps(script)}]}]})
    h.ctx.ai.http=httpx.Client(transport=httpx.MockTransport(respond))
    schema=writer.schema(passage,manifest,'pt-BR')
    with h.ctx.ai.preparing_lesson():
        first=h.ctx.ai.generate('Synthetic teaching script',schema=schema)
        assert h.ctx.ai.generate('Synthetic teaching script',schema=schema)==first
    assert len(requests)==1
    assert requests[0]['model']==PREPARATION_MODEL and requests[0]['reasoning']['effort']=='high'
    assert len(h.ctx.ai.ledger.requests())==1


def test_writer_receives_age_context_and_precise_source_but_not_engine_workbook_payload():
    passage,manifest,_=source()
    text=writer.prompt(passage,subject='Portuguese',learner='Practice child',grade='3',language='pt-BR',
        learner_context={'source_requirements':manifest,'workbook_exercises':[{'answer':'PRIVATE-SOLUTION'}],
            'family_tutoring':{'content':'Be warm.','learner_profile':{'age':9}},'learning_memory':{'observations':['Needs time for spelling.']},
            'source_annotations':[{'note':'CHECKED-SOURCE-NOTE'}]})
    assert '"age": 9' in text and 'Needs time for spelling.' in text
    assert 'PRIVATE-SOLUTION' not in text and '"id": "w0"' in text
    assert 'CHECKED-SOURCE-NOTE' in text
