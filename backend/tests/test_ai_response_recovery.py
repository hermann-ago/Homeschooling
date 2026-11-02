import json
import httpx
import pytest
import request_context
from services.ai_provider import AIService, UnusableResponseError, strict_schema,provider_schema
from tests.test_ai_costs import SmallResponse
from tutoring.guide import GuidePlan


def test_explicit_provider_is_scoped_and_does_not_change_family_settings(harness):
    from concurrent.futures import ThreadPoolExecutor
    ai=harness.ctx.ai
    original=ai.selection()
    with ai.using_provider('google'):
        assert ai.selection()[0]=='google'
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(ai.selection).result()==original
        with ai.using_provider('openai'):
            assert ai.selection()[0]=='openai'
        assert ai.selection()[0]=='google'
    assert ai.selection()==original


def test_google_current_model_counts_thinking_and_keeps_it_out_of_script(harness,monkeypatch):
    from services.ai_provider import GOOGLE_TEXT_MODEL
    monkeypatch.setenv('GEMINI_API_KEY','test-key-never-real')
    def respond(request):
        assert GOOGLE_TEXT_MODEL in request.url.path
        if request.url.path.endswith(':countTokens'):
            return httpx.Response(200,json={'totalTokens':100})
        return httpx.Response(200,json={'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':20,'thoughtsTokenCount':30},
            'candidates':[{'finishReason':'STOP','content':{'parts':[{'thought':True,'text':'private reasoning'},
                {'text':'{"answer":"saved","note":null}'}]}}]})
    ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(respond)))
    with ai.using_provider('google'):
        assert ai.generate('Synthetic Google script',schema=SmallResponse)['answer']=='saved'
    request=ai.ledger.requests()[-1]
    assert request['model']==GOOGLE_TEXT_MODEL
    assert ai.ledger.outcome(request['id'])['usage']['output_tokens']==50


@pytest.mark.parametrize('reply,code',[
    ({'status':'completed','output':[]},'provider_empty'),
    ({'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'},'output':[]},'provider_length_limit'),
    ({'status':'failed','error':{'code':'server_error'},'output':[]},'provider_failed'),
    ({'status':'completed','output':[{'content':[{'type':'refusal','refusal':'declined'}]}]},'provider_refusal'),
])
def test_known_failed_replies_are_classified_saved_and_not_repurchased(harness,monkeypatch,reply,code):
    monkeypatch.setenv('OPENAI_API_KEY','test-key-never-real')
    sent=[]
    def respond(request):
        if request.url.path.endswith('/input_tokens'):return httpx.Response(200,json={'input_tokens':100})
        sent.append(request)
        return httpx.Response(200,json={**reply,'usage':{'input_tokens':100,'output_tokens':0}})
    for attempt in range(2):
        ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(respond)))
        marker=request_context.begin(request_context.RequestContext('different-http-operation-'+str(attempt)))
        try:
            with pytest.raises(UnusableResponseError) as error:ai.generate('Synthetic failed script',schema=SmallResponse)
        finally:request_context.end(marker)
        assert error.value.code==code
        outcome=ai.ledger.outcome(ai.cache_id('Synthetic failed script',schema=SmallResponse))
        assert outcome['code']==code and outcome['usage']['output_tokens']==0
    assert len(sent)==1


@pytest.mark.parametrize('recovered',[True,False])
def test_one_explicit_replacement_survives_restart_and_ordinary_retries(harness,monkeypatch,recovered):
    monkeypatch.setenv('OPENAI_API_KEY','test-key-never-real')
    sent=[]
    def respond(request):
        if request.url.path.endswith('/input_tokens'):return httpx.Response(200,json={'input_tokens':100})
        sent.append(request)
        output=[{'content':[{'type':'output_text','text':'{"answer":"saved","note":null}'}]}] if recovered and len(sent)>1 else []
        return httpx.Response(200,json={'status':'completed','output':output,'usage':{'input_tokens':100,'output_tokens':10 if output else 0}})
    ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(UnusableResponseError):ai.generate('Synthetic recovery',schema=SmallResponse)
    for attempt in range(2):
        ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(respond)))
        if recovered:assert ai.generate('Synthetic recovery',schema=SmallResponse,replace_invalid=True)['answer']=='saved'
        else:
            with pytest.raises(UnusableResponseError):ai.generate('Synthetic recovery',schema=SmallResponse,replace_invalid=True)
    if recovered:assert ai.generate('Synthetic recovery',schema=SmallResponse)['answer']=='saved'
    assert len(sent)==2


def test_ambiguous_transport_outcome_never_becomes_a_fresh_purchase(harness,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-key-never-real')
    sent=[]
    def respond(request):
        if request.url.path.endswith('/input_tokens'):return httpx.Response(200,json={'input_tokens':100})
        sent.append(request);raise httpx.ReadTimeout('unknown')
    for attempt in range(2):
        ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(respond)))
        with pytest.raises(ValueError):ai.generate('Unknown synthetic script',schema=SmallResponse)
    assert len(sent)==1 and ai.ledger.summary(ai.limits)['categories']['teaching']['uncertain_usd']>0


def test_compact_provider_segments_keep_canonical_validation_and_drop_irrelevant_fields():
    schema=strict_schema(GuidePlan)
    assert schema['$defs']['SpokenPlanSegment']['required']==['type','text']
    assert set(schema['$defs']['ReadingPlanSegment']['required'])=={'type','from','to','text','source_block_id'}
    assert 'activity_kind' not in schema['$defs']['ReadingPlanSegment']['properties']
    assert 'content' not in schema['$defs']['SpokenPlanSegment']['properties']
    plan=GuidePlan.model_validate({'mode':'expand','segments':[{'type':'intro','text':'Welcome.'},
        {'type':'read','from':0,'to':2,'text':None},{'type':'action','text':'What changed?','action_kind':'answer','concept_ids':[]}]})
    assert len(plan.segments)==3
    with pytest.raises(ValueError):GuidePlan.model_validate({'mode':'expand','segments':[{'type':'activity',
        'activity_kind':'ask_question','content':{'text':'Wrong content type'}}]})


def test_google_adapter_keeps_native_activity_objects_and_validates_bounds_locally():
    schema=provider_schema(GuidePlan,'google')
    assert 'maxItems' not in schema['properties']['segments']
    assert 'title' in schema['$defs']['ComparisonItem']['properties']
    assert schema['$defs']['PlannedAskQuestion']['properties']['content']['$ref']=='#/$defs/QuestionContent'
    assert schema['$defs']['PlannedReadSource']['properties']['content']['$ref']=='#/$defs/ReadContent'
    with pytest.raises(ValueError):GuidePlan.model_validate({'mode':'expand','segments':[{'type':'intro','text':'Hello'}]*201})
    with pytest.raises(ValueError):GuidePlan.model_validate({'mode':'expand','segments':[{'type':'activity','activity_kind':'ask_question',
        'content':{'prompt':'Hello','choices':[{'id':str(i),'label':'Choice'} for i in range(13)],'response_modes':['choice']}}]})


def test_original_page_script_replaces_whitespace_stall_once_without_accepting_partial_work(harness, monkeypatch):
    from tutoring import page_script, book_questions
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-key-never-real')
    harness.config.update(ai={**harness.config.get('ai'), 'monthly_generation_enabled': True})
    passage = {'title': 'An invented second chapter', 'sentences': []}
    context = {'visual_source': {'pages': [
        {'document_id': 3, 'page': page, 'role': 'assigned_reading'} for page in range(17, 23)]},
        'book_question_policy': book_questions.VERSION}
    schema = page_script.schema(passage, context, 'en-US')
    prompt = page_script.prompt(passage, subject='Reading', learner='the reader', grade='3',
        language='en-US', learner_context=context)
    script = {'welcome': 'Let us read the next chapter.', 'turns': [
        {'type': 'read', 'text': 'An invented bird shared its grain.\n\nThe mouse thanked it.',
         'document_id': 3, 'page_start': 17, 'page_end': 19},
        {'type': 'say', 'text': 'Sharing the grain gave the mouse something to eat.'}], 'closing': 'We reached the end.'}
    sent = []
    def respond(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        body = json.loads(request.content)
        controls = body['text']['format']['schema']['$defs']
        assert controls['Response']['type'] == controls['BookChoiceResponse']['type'] == 'object'
        assert 'anyOf' not in controls['Response'] and 'anyOf' not in controls['BookChoiceResponse']
        assert 'compact JSON' in body['input'][0]['content'][0]['text']
        sent.append(body)
        if len(sent) == 1:
            # Same observed failure boundary: an unfinished response object,
            # followed by thousands of whitespace tokens, is never repaired.
            return httpx.Response(200, json={'status': 'incomplete',
                'incomplete_details': {'reason': 'max_output_tokens'},
                'usage': {'input_tokens': 100, 'output_tokens': 16384},
                'output': [{'content': [{'type': 'output_text',
                    'text': '{"welcome":"Read.","turns":[{"type":"book_work","response":{' + ' \n\t' * 18000}]}]})
        return httpx.Response(200, json={'status': 'completed',
            'usage': {'input_tokens': 100, 'output_tokens': 400},
            'output': [{'content': [{'type': 'output_text', 'text': json.dumps(script, separators=(',', ':'))}]}]})
    for attempt in range(3):
        ai = AIService(harness.ctx, httpx.Client(transport=httpx.MockTransport(respond)))
        with ai.preparing_lesson():
            if attempt < 2:
                with pytest.raises(UnusableResponseError, match='output limit'):
                    ai.generate(prompt, schema=schema, max_output=16384)
            else:
                recovered = ai.generate(prompt, schema=schema, max_output=16384, replace_invalid=True)
                assert ai.generate(prompt, schema=schema, max_output=16384) == recovered
    plan = page_script.compile_script(recovered, passage, context, 'en-US')
    assert plan['segments'][1]['text'] == script['turns'][0]['text']
    assert plan['segments'][2]['text'] == script['turns'][1]['text']
    assert not any(s['type'] in ('activity', 'action') for s in plan['segments'])
    assert plan['segments'][-1]['text'] == script['closing']
    assert len(sent) == 2


@pytest.mark.parametrize('response', [
    {'format': 'single_choice', 'choices': ['Only one']},
    {'format': 'text', 'choices': ['Unexpected', 'Options']},
    {'format': 'matching', 'matching_items': ['Bird', 'Mouse'], 'matching_options': ['Grain']},
])
def test_flat_page_response_controls_still_reject_invalid_combinations(response):
    from tutoring.page_script import Script
    with pytest.raises(ValueError):
        Script.model_validate({'welcome': 'Welcome.', 'turns': [
            {'type': 'book_work', 'document_id': 3, 'page': 20, 'prompt': 'Original work.', 'response': response}],
            'closing': 'Goodbye.'})
