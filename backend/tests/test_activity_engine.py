"""Synthetic, offline checks of capture, identity, transitions and replay."""
import json
import uuid

import pytest
import httpx

from tutoring.activity_engine import service
from tutoring.service import TutorConflict, TutorError
from tutoring import interactive
from tests.test_interactive import prepare, start, correct


def engine_lesson(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    legacy = start(harness, seeded, guide)
    engine = service(harness.ctx)
    return engine, engine.state(legacy["session_id"]), seeded


def invoke(engine, state, kind="ask_question", content=None, operation=None):
    return engine.invoke(state["session_id"], state["revision"], operation or str(uuid.uuid4()), kind,
        content or {"prompt": "Explain what changed."})


def event(engine, state, kind, payload=None, operation=None, **override):
    active = state["active_activity"]
    return engine.command(state["session_id"], state["revision"], operation or str(uuid.uuid4()), active["id"],
        override.get("interaction_id", active["interaction"]["id"]), kind, payload or {})


@pytest.mark.parametrize('kind', ['tell_it_back', 'explain_thinking'])
@pytest.mark.parametrize('method', ['typed', 'dictation'])
def test_explanation_is_captured_in_answer_without_duplicate_reasoning(harness, monkeypatch, kind, method):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, kind=kind, content={'prompt': 'Explain what happened and why.',
        'response_modes': ['text', 'device_dictation'], 'evidence_requirement': 'reasoning', 'require_reasoning': True})
    text = 'The small bird helped because it remembered the kindness.'
    state = event(engine, state, 'submit_response', {'response_id': 'actual-explanation', 'method': method, 'text': text})
    saved = harness.ctx.store.get('activity_responses', 'actual-explanation')
    assert saved['original']['text'] == text
    assert not saved['reasoning']  # Never manufacture a separate learner explanation.
    assert saved['status'] == ('awaiting_confirmation' if method == 'dictation' else 'confirmed')
    assert not harness.ctx.store.all('attempts')  # Capturing an explanation does not grade it.


def test_choice_still_needs_explicit_reasoning(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, kind='explain_thinking', content={'prompt': 'Choose and explain.',
        'response_modes': ['choice'], 'choices': [{'id': 'a', 'label': 'A small bird'}, {'id': 'b', 'label': 'A large bear'}], 'require_reasoning': True})
    with pytest.raises(TutorError, match='reasoning'):
        event(engine, state, 'submit_response', {'response_id': 'choice-only', 'method': 'choice', 'choice_ids': ['a']})
    assert not harness.ctx.store.all('activity_responses')


@pytest.mark.parametrize('origin,result,allowed', [('adaptive', 'Partly correct', True),
    ('adaptive', 'Not yet', False), ('required_book', 'Partly correct', False)])
def test_discussion_continue_preserves_real_assessment_and_unanswered_followup(harness, monkeypatch, origin, result, allowed):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, kind='tell_it_back', content={'prompt': 'Retell the story.'})
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_actions', f"{state['session_id']}:{state['active_activity']['id']}", {'origin': origin})
    prompts = []
    def feedback(prompt, *args, **kwargs):
        prompts.append(prompt)
        return {'feedback': 'You remembered the main events. The bird also remembered the kindness.',
            'result': result, 'follow_up': 'Why did the bird help?', 'ready_to_continue': False}
    monkeypatch.setattr(interactive, 'gemini_turn', feedback)
    state = event(engine, state, 'submit_response', {'response_id': 'discussion-answer', 'text': 'The bird helped the bear.', 'assess_after_save': True})
    assert ('FLEXIBLE GENERATED DISCUSSION' in prompts[0]) == (origin == 'adaptive')
    assert state['active_activity']['can_continue_discussion'] is allowed
    followup = state['active_activity']['interaction']['id']
    attempts = harness.ctx.store.all('attempts')
    if not allowed:
        with pytest.raises(TutorConflict): event(engine, state, 'continue')
    else:
        before = state
        event(engine, state, 'continue', operation='continue-discussion')
        event(engine, before, 'continue', operation='continue-discussion')
        assert harness.ctx.store.get('activity_interactions', followup)['status'] == 'deferred'
        assert len(harness.ctx.store.all('activity_responses')) == 1
    assert harness.ctx.store.all('attempts') == attempts


def test_adaptive_detour_under_required_book_stays_strict(harness, monkeypatch):
    from tutoring.assessment_policy import flexible_discussion
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    root = f"{state['session_id']}:{state['active_activity']['id']}"
    with harness.ctx.store.transaction() as tx:
        parent = tx.update('lesson_actions', root, {'origin': 'required_book'})
        child = {**parent, 'id': 'synthetic-child', 'origin': 'adaptive', 'parent_activity_id': parent['action_id']}
        assert not flexible_discussion(tx, child)


def test_showing_is_pending_and_retry_preserves_card_and_wrong_payload_conflicts(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    original_revision = state["revision"]
    shown = invoke(engine, state, operation="show-one-question")
    replay = invoke(engine, state, operation="show-one-question")
    assert replay["activity_id"] == shown["activity_id"]
    assert replay["interaction_id"] == shown["interaction_id"]
    assert replay["pending"] and shown["active_activity"]["interaction"]["status"] == "awaiting_input"
    assert not harness.ctx.store.all("attempts")
    assert original_revision < shown["revision"]
    with pytest.raises(TutorConflict):
        invoke(engine, shown, content={"prompt": "Different question"}, operation="show-one-question")


def test_one_click_save_and_assess_replays_without_duplicate_evidence(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    original = state
    calls = []
    def assess(*args):
        # Capture is committed before entering the provider.
        assert harness.ctx.store.get("activity_responses", "one-click")["confirmed_text"] == "He united them."
        calls.append(True)
        return correct(*args)
    monkeypatch.setattr(interactive, "gemini_turn", assess)
    payload = {"response_id": "one-click", "text": "He united them.", "assess_after_save": True}
    state = event(engine, state, "submit_response", payload, operation="one-click-operation")
    assert state["active_activity"]["status"] == "answered"
    harness.restart()
    engine = service(harness.ctx)
    event(engine, original, "submit_response", payload, operation="one-click-operation")
    assert len(calls) == 1
    assert len(harness.ctx.store.all("activity_responses")) == 1
    assert len(harness.ctx.store.all("attempts")) == 1


def test_confirm_and_check_recovers_legacy_photo_without_duplicate_purchases(harness, monkeypatch):
    engine,state,_=engine_lesson(harness,monkeypatch)
    state=invoke(engine,state,content={'prompt':'What happened?','response_modes':['text','device_dictation']})
    state=event(engine,state,'submit_response',{'response_id':'legacy-capture','method':'dictation','text':'He united them.'})
    with harness.ctx.store.transaction() as tx:tx.update('activity_responses','legacy-capture',{'method':'photo'})
    calls=[]
    def assess(*args,**kwargs):calls.append(True);return correct(*args)
    monkeypatch.setattr(interactive,'gemini_turn',assess)
    before=state
    payload={'response_id':'legacy-capture','text':'He united them.','assess_after_confirm':True}
    state=event(engine,state,'confirm_response',payload,operation='confirm-check')
    event(engine,before,'confirm_response',payload,operation='confirm-check')
    assert state['active_activity']['status']=='answered'
    assert len(calls)==1 and len(harness.ctx.store.all('attempts'))==1
    assert harness.ctx.store.get('activity_responses','legacy-capture')['original']['text']=='He united them.'


def test_empty_photo_cannot_be_submitted_as_photographic_evidence(harness, monkeypatch):
    engine,state,_=engine_lesson(harness,monkeypatch)
    state=invoke(engine,state,content={'prompt':'Send your work.','response_modes':['photo']})
    with pytest.raises(TutorError,match='Attach a photo'):
        event(engine,state,'submit_response',{'response_id':'no-photo','method':'photo','text':'A typed word'})
    assert not harness.ctx.store.all('activity_responses')


@pytest.mark.parametrize('word,result',[('leão','Correct'),('leao','Not yet')])
def test_typed_spelling_checks_diacritics_without_a_photograph(harness,monkeypatch,word,result):
    engine,state,_=engine_lesson(harness,monkeypatch)
    state=invoke(engine,state,'request_book_work',{'prompt':'Coloque o til: leao.',
        'evidence_requirement':'spelling','response_modes':['photo','parent_review']})
    assert state['active_activity']['interaction']['status']=='awaiting_input'
    def assess(prompt,*args,**kwargs):
        assert 'Evidence target: spelling.' in prompt and 'accent/diacritic placement' in prompt
        return {'feedback':'Checked the typed spelling.','result':result,'ready_to_continue':result=='Correct'}
    monkeypatch.setattr(interactive,'gemini_turn',assess)
    state=event(engine,state,'submit_response',{'response_id':'accent-answer','method':'typed','text':word,'assess_after_save':True})
    assert state['active_activity']['responses'][0]['status']=='assessed'
    assert harness.ctx.store.all('attempts')[0]['first_result']==result
    assert harness.ctx.store.get('activity_responses','accent-answer')['original']['text']==word
    assert not harness.ctx.store.all('evidence_files')


def test_old_written_steps_accent_gate_recovers_saved_word(harness,monkeypatch):
    engine,state,_=engine_lesson(harness,monkeypatch)
    state=invoke(engine,state,'request_book_work',{'prompt':'Coloque o til: leao.','evidence_requirement':'spelling','response_modes':['text']})
    state=event(engine,state,'submit_response',{'response_id':'saved-accent','method':'typed','text':'leão'})
    with harness.ctx.store.transaction() as tx:
        tx.update('activity_responses','saved-accent',{'method':'written_steps','status':'parent_review'})
        tx.update('activity_interactions',state['active_activity']['interaction']['id'],{'status':'parent_review'})
    state=engine.state(state['session_id'])
    assert state['active_activity']['responses'][0]['answer_only_recheck_available']
    monkeypatch.setattr(interactive,'gemini_turn',correct)
    state=event(engine,state,'assess',{'response_id':'saved-accent'})
    assert state['active_activity']['status']=='answered'
    assert harness.ctx.store.get('activity_responses','saved-accent')['original']['text']=='leão'


def test_old_photo_gate_can_check_confirmed_answer_without_parent_ui(harness, monkeypatch):
    engine,state,_=engine_lesson(harness,monkeypatch)
    state=invoke(engine,state,content={'prompt':'What happened?','response_modes':['text','device_dictation']})
    state=event(engine,state,'submit_response',{'response_id':'old-gate','method':'dictation','text':'He united them.'})
    state=event(engine,state,'confirm_response',{'response_id':'old-gate','text':'He united them.'})
    with harness.ctx.store.transaction() as tx:
        tx.update('activity_responses','old-gate',{'method':'photo','status':'parent_review'})
        tx.update('activity_interactions',state['active_activity']['interaction']['id'],{'status':'parent_review'})
    state=engine.state(state['session_id'])
    assert state['active_activity']['responses'][0]['answer_only_recheck_available']
    monkeypatch.setattr(interactive,'gemini_turn',correct)
    state=event(engine,state,'assess',{'response_id':'old-gate'})
    assert state['active_activity']['status']=='answered'
    assert len(harness.ctx.store.all('activity_responses'))==1
    assert len(harness.ctx.store.all('attempts'))==1


def test_explicit_feedback_replacement_keeps_response_and_frozen_context(harness, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-openai-key-never-real')
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    calls = []
    def respond(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        calls.append(json.loads(request.content)['input'][0]['content'][0]['text'])
        text = json.dumps({'feedback': 'Synthetic feedback.', 'result': 'Correct', 'ready_to_continue': True})
        if len(calls) == 1:
            text += ' corrupt separator {"result":"Not yet"}'
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]})
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    state = event(engine, state, 'submit_response', {'response_id': 'preserved-response', 'text': 'Original words', 'assess_after_save': True})
    response = state['active_activity']['responses'][0]
    assert response['feedback_failure'] == 'invalid_reply'
    assert not response['feedback_replacement_used']
    assert not harness.ctx.store.all('attempts')
    state = event(engine, state, 'assess', {'response_id': response['id']})
    assert len(calls) == 1
    before_repair = state
    payload = {'response_id': response['id'], 'replace_invalid_reply': True}
    state = event(engine, state, 'assess', payload, operation='explicit-replacement')
    assert state['active_activity']['responses'][0]['status'] == 'assessed'
    assert state['active_activity']['responses'][0]['feedback_replacement_used']
    assert calls[1].startswith(calls[0])  # original response/context remains frozen
    harness.restart()
    engine = service(harness.ctx)
    event(engine, before_repair, 'assess', payload, operation='explicit-replacement')
    assert len(calls) == 2
    responses = harness.ctx.store.all('activity_responses')
    assert len(responses) == 1 and responses[0]['original']['text'] == 'Original words'
    assert len(harness.ctx.store.all('attempts')) == 1


def test_exhausted_provider_credit_is_named_and_answer_retries_later(harness, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-openai-key-never-real')
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    credit = []
    def respond(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        if not credit:
            return httpx.Response(429, json={'error': {'code': 'credit_balance_exhausted', 'type': 'insufficient_quota'}})
        text = json.dumps({'feedback': 'Synthetic feedback.', 'result': 'Correct', 'ready_to_continue': True})
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]})
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    state = event(engine, state, 'submit_response', {'response_id': 'no-credit', 'text': 'Original words', 'assess_after_save': True})
    assert 'out of credits' in state['error']
    response = state['active_activity']['responses'][0]
    assert response['feedback_failure'] == 'provider_quota'
    credit.append(True)
    state = event(engine, state, 'assess', {'response_id': response['id']})
    assert state['active_activity']['responses'][0]['status'] == 'assessed'
    assert harness.ctx.store.get('activity_responses', 'no-credit')['original']['text'] == 'Original words'


def test_one_click_cannot_bypass_transcript_confirmation(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, content={"prompt": "What happened?", "response_modes": ["device_dictation"]})
    with pytest.raises(TutorError):
        event(engine, state, "submit_response", {"response_id": "not-confirmed", "method": "dictation", "text": "United", "assess_after_save": True})
    assert not harness.ctx.store.all("activity_responses")


def test_simple_choice_does_not_require_reasoning_or_claim_independent_understanding(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    content = {"prompt": "Choose lowercase r.", "response_modes": ["choice"], "choices": [{"id": "r", "label": "r"}, {"id": "p", "label": "p"}]}
    state = invoke(engine, state, content=content)
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    state = event(engine, state, "submit_response", {"response_id": "letter-choice", "method": "choice", "choice_ids": ["r"], "assess_after_save": True})
    assert state["active_activity"]["status"] == "answered"
    attempt = harness.ctx.store.all("attempts")[0]
    assert attempt["first_result"] == "Correct" and attempt["independence"] == "not_assessed"
    state = invoke(engine, state, content={**content, "require_reasoning": True})
    with pytest.raises(TutorError, match="reasoning"):
        event(engine, state, "submit_response", {"response_id": "method-required", "method": "choice", "choice_ids": ["r"]})


def test_true_false_saves_labels_reasoning_and_followup_uses_text(harness, monkeypatch):
    engine,state,_=engine_lesson(harness,monkeypatch)
    state=invoke(engine,state,content={'prompt':'A triangle has four sides.', 'answer_format':'true_false'})
    initial=state
    for choices in (['true','false'],['false','false'],['unknown'],'false'):
        with pytest.raises(TutorError):
            event(engine,state,'submit_response',{'response_id':str(uuid.uuid4()),'method':'choice','choice_ids':choices})
    monkeypatch.setattr(interactive,'gemini_turn',lambda *_:{'feedback':'Tell me your reason.', 'result':'Partly correct','follow_up':'How many sides does it have?'})
    payload={'response_id':'false-answer','method':'choice','choice_ids':['false'],'reasoning':'I counted three.', 'assess_after_save':True}
    state=event(engine,state,'submit_response',payload,operation='binary-submit')
    response=harness.ctx.store.get('activity_responses','false-answer')
    assert response['original']['choice_ids']==['false'] and response['confirmed_text']=='False'
    assert response['reasoning']=='I counted three.'
    assert state['active_activity']['content']['choices']==[]
    assert 'text' in state['active_activity']['content']['response_modes']
    harness.restart();engine=service(harness.ctx)
    event(engine,initial,'submit_response',payload,operation='binary-submit')
    state=engine.state(state['session_id'])
    state=event(engine,state,'submit_response',{'response_id':'explanation','method':'typed','text':'Three.'})
    assert len(harness.ctx.store.all('activity_responses'))==2
    assert harness.ctx.store.get('activity_responses','false-answer')['original']['choice_ids']==['false']


def test_select_all_validates_and_saves_source_order(harness,monkeypatch):
    engine,state,_=engine_lesson(harness,monkeypatch)
    state=invoke(engine,state,content={'prompt':'Select the even numbers.','answer_format':'multiple_select',
        'choices':[{'id':'a','label':'2'},{'id':'b','label':'3'},{'id':'c','label':'4'}]})
    state=event(engine,state,'submit_response',{'response_id':'evens','method':'choice','choice_ids':['c','a']})
    response=harness.ctx.store.get('activity_responses','evens')
    assert response['confirmed_text']=='2; 4' and response['original']['choice_ids']==['a','c']


def test_dictation_confirmation_then_assessment_and_followup_are_distinct(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, content={"prompt": "What happened?", "response_modes": ["text", "device_dictation"]})
    state = event(engine, state, "submit_response", {"response_id": "spoken-first", "method": "dictation", "text": "He unyted them"})
    assert state["active_activity"]["interaction"]["status"] == "awaiting_confirmation"
    with pytest.raises(TutorConflict):
        event(engine, state, "assess", {"response_id": "spoken-first"})
    state = event(engine, state, "confirm_response", {"response_id": "spoken-first", "text": "He united them."})
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    state = event(engine, state, "assess", {"response_id": "spoken-first"})
    response = harness.ctx.store.get("activity_responses", "spoken-first")
    assert response["original"]["text"] == "He unyted them"
    assert response["confirmed_text"] == "He united them."
    assert response["status"] == "assessed"
    assert state["active_activity"]["status"] == "answered"
    assert harness.ctx.store.all("attempts")[0]["first_answer"] == "He united them."
    assert state["playback"]["action_id"] == state["active_activity"]["id"]


def test_wrong_answer_hint_revision_has_owned_interaction_ids(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    first_interaction = state["active_activity"]["interaction"]["id"]
    state = event(engine, state, "submit_response", {"response_id": "first-incorrect", "text": "They fought."})
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: {"feedback": "Read the tribes paragraph.",
        "help": "A source pointer", "result": "Not yet", "follow_up": "What changed for the tribes?"})
    state = event(engine, state, "assess", {"response_id": "first-incorrect"})
    assert state["active_activity"]["interaction"]["id"] != first_interaction
    with pytest.raises(TutorConflict):
        event(engine, state, "submit_response", {"response_id": "late-reply", "text": "They united."}, interaction_id=first_interaction)
    state = event(engine, state, "submit_response", {"response_id": "second-answer", "text": "He united them."})
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    state = event(engine, state, "assess", {"response_id": "second-answer"})
    attempts = harness.ctx.store.find("attempts", session_id=state["session_id"])
    assert attempts[0]["first_answer"] == "They fought."
    assert attempts[1]["revised_answer"] == "He united them."
    assert attempts[1]["independence"] == "with_help"


def test_capture_survives_restart_break_and_assessment_failure(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    state = event(engine, state, "submit_response", {"response_id": "recover-answer", "text": "He united them."})
    state = event(engine, state, "take_break")
    harness.restart()
    engine = service(harness.ctx)
    state = engine.state(state["session_id"])
    assert state["on_break"] and state["active_activity"]["responses"][0]["original"]["text"] == "He united them."
    state = event(engine, state, "resume")
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: (_ for _ in ()).throw(ValueError("offline")))
    state = event(engine, state, "assess", {"response_id": "recover-answer"}, operation="assessment-retry")
    assert state["active_activity"]["interaction"]["status"] == "assessment_failed"
    assert not harness.ctx.store.all("attempts")
    monkeypatch.setattr(interactive, "gemini_turn", correct)
    state = event(engine, state, "assess", {"response_id": "recover-answer"}, operation="assessment-retry")
    assert len(harness.ctx.store.all("attempts")) == 1
    assert state["active_activity"]["responses"][0]["status"] == "assessed"


def test_physical_work_acknowledgement_and_missing_visual_evidence_never_score(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, "request_book_work", {"prompt": "Write the calculation in your book.",
        "book_name": "Synthetic mathematics", "exercise_reference": "3", "evidence_requirement": "written_steps"})
    assert state["active_activity"]["interaction"]["status"] == "awaiting_work"
    with pytest.raises(TutorConflict):
        event(engine, state, "submit_response", {"response_id": "too-early", "text": "4"})
    state = event(engine, state, "physical_complete")
    state = event(engine, state, "submit_response", {"response_id": "paper-answer", "text": "4"})
    state = event(engine, state, "assess", {"response_id": "paper-answer"})
    assert state["active_activity"]["interaction"]["status"] == "parent_review"
    assert not harness.ctx.store.all("attempts") and not harness.ctx.store.all("reviews")
    state = event(engine, state, "parent_review", {"response_id": "paper-answer", "text": "2 + 2 = 4", "result": "Correct", "note": "Parent inspected the written steps."})
    assert harness.ctx.store.all("attempts")[0]["first_answer"] == "2 + 2 = 4"
    assert state["active_activity"]["status"] == "answered"


@pytest.mark.parametrize('ready', [False, True])
def test_source_disagreement_can_continue_without_regrading_or_parent_observation(harness, monkeypatch, ready):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, 'request_book_work', {'prompt': 'According to the book, what material was used?',
        'book_name': 'Synthetic history', 'exercise_reference': '11'})
    state = event(engine, state, 'physical_complete')
    calls = []
    def disputed(prompt, *_):
        assert 'For a book-wording question' in prompt
        calls.append(prompt)
        return {'feedback': 'Your answer matches the book; other sources differ.',
            'result': 'Source disputed', 'ready_to_continue': ready}
    monkeypatch.setattr(interactive, 'gemini_turn', disputed)
    state = event(engine, state, 'submit_response', {'response_id': 'source-answer', 'text': 'The book material.', 'assess_after_save': True})
    active = state['active_activity']
    assert active['responses'][0]['source_disputed']
    attempts = harness.ctx.store.all('attempts')
    assert len(attempts) == 1 and attempts[0]['first_result'] == 'Source disputed'
    with pytest.raises(TutorError):
        event(engine, state, 'acknowledge_source_issue', {'response_id': 'not-this-response'})
    command = {'operation_id': 'source-note-continue', 'expected_revision': state['revision'],
        'activity_id': active['id'], 'interaction_id': active['interaction']['id'],
        'type': 'acknowledge_source_issue', 'payload': {'response_id': 'source-answer'}}
    url = f"/api/tutor/sessions/{state['session_id']}/activity-events"
    continued = harness.call('POST', url, json=command)
    assert continued.status_code == 200, continued.text
    after = continued.json()
    assert after['active_activity']['id'] != active['id']
    saved = next(a for a in after['activities'] if a['id'] == active['id'])
    assert saved['status'] == 'answered'
    assert saved['interaction']['status'] == 'completed'
    assert saved['responses'][0]['source_issue_acknowledged']
    assert saved['responses'][0]['confirmed_text'] == 'The book material.'
    summary = engine._learning_summary(engine._session(state['session_id']), harness.ctx.store.find('lesson_actions', session_id=state['session_id']))
    assert summary['answers']['checked'] == 0
    assert active['id'] not in {item['activity_id'] for item in summary['pending_work']}
    harness.restart()
    repeated = harness.call('POST', url, json=command)
    assert repeated.status_code == 200
    assert repeated.json()['active_activity']['id'] == after['active_activity']['id']
    assert harness.ctx.store.all('attempts') == attempts
    assert not harness.ctx.store.all('reviews')
    assert len(calls) == 1


def test_source_acknowledgment_cannot_bypass_missing_written_evidence(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, 'request_book_work', {'prompt': 'Show your calculation.',
        'book_name': 'Synthetic math', 'exercise_reference': '1', 'evidence_requirement': 'written_steps'})
    state = event(engine, state, 'physical_complete')
    state = event(engine, state, 'submit_response', {'response_id': 'needs-steps', 'text': '4', 'assess_after_save': True})
    with pytest.raises(TutorConflict):
        event(engine, state, 'acknowledge_source_issue', {'response_id': 'needs-steps'})
    assert state['active_activity']['interaction']['status'] == 'parent_review'
    assert not harness.ctx.store.all('attempts')


def test_prediction_and_worked_example_hide_unreached_content(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    assert "SECRET-KEY-ANSWER" not in json.dumps(state, default=str)
    assert "What did Genghis Khan do with the tribes?" not in json.dumps(state, default=str)
    state = invoke(engine, state, "predict_then_check", {"prompt": "What will happen?", "reveal": {"text": "HIDDEN REVEAL"}, "reflection_prompt": "Was your prediction supported?"})
    assert "HIDDEN REVEAL" not in json.dumps(state, default=str)
    with pytest.raises(TutorConflict):
        event(engine, state, "reveal")
    state = event(engine, state, "submit_response", {"response_id": "prediction", "text": "They unite", "reasoning": "A shared goal"})
    state = event(engine, state, "reveal")
    assert state["active_activity"]["content"]["reveal"]["text"] == "HIDDEN REVEAL"
    assert state["active_activity"]["interaction"]["stage"] == "reflection"
    state = invoke(engine, state, "worked_example", {"text": "Watch the method", "steps": [{"text": "FIRST STAGE"}, {"text": "SECOND STAGE"}], "practice_prompt": "LATER PRACTICE"})
    assert "FIRST STAGE" in json.dumps(state, default=str)
    assert "SECOND STAGE" not in json.dumps(state, default=str)
    assert "LATER PRACTICE" not in json.dumps(state, default=str)
    state = event(engine, state, "advance_stage")
    assert "SECOND STAGE" in json.dumps(state, default=str)
    state = event(engine, state, "advance_stage")
    assert state["active_activity"]["interaction"]["stage"] == "practice"


def test_followup_is_conversation_and_returns_to_original_activity(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    originating = state["active_activity"]["id"]
    monkeypatch.setattr(interactive, "gemini_turn", lambda *args: {"feedback": "A tribe is a community.", "result": "Unanswered", "ready_to_continue": True})
    state = event(engine, state, "request_followup", {"prompt": "What does tribe mean?"})
    assert state["active_activity"]["parent_activity_id"] == originating
    assert not harness.ctx.store.all("attempts")
    state = event(engine, state, "continue")
    assert state["active_activity"]["id"] == originating


def test_response_identity_cannot_cross_sessions_or_prompts(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    with pytest.raises(TutorError):
        event(engine, state, "assess", {"response_id": "not-saved"})
    state = event(engine, state, "submit_response", {"response_id": "owned-response", "text": "Original"})
    with pytest.raises(TutorConflict):
        event(engine, state, "submit_response", {"response_id": "new-while-pending", "text": "Another"})
    assert len(harness.ctx.store.all("activity_responses")) == 1


def test_hint_is_saved_support_without_an_attempt_and_can_retry(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state)
    monkeypatch.setattr(harness.ctx.ai, "generate", lambda *args, **kwargs: {"text": "Look at what happened to the tribes."})
    state = event(engine, state, "request_hint", operation="hint-request-once")
    assert not harness.ctx.store.all("attempts")
    assert state["active_activity"]["messages"][0]["text"] == "Look at what happened to the tribes."
    state = event(engine, state, "request_hint", operation="hint-request-once")
    assert len(state["active_activity"]["messages"]) == 1


def test_unobserved_feedback_result_and_foreign_sources_are_rejected(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    with pytest.raises(TutorError):
        invoke(engine, state, "give_feedback", {"text": "Correct", "result": "Correct", "assessment_status": "assessed"})
    with pytest.raises(TutorError):
        invoke(engine, state, "visual_demonstration", {"text": "Look here", "visual": {"type": "book_illustration", "document_id": 99999, "page": 1}})


def test_hands_on_book_work_waits_for_a_grown_up_and_records_no_grade(harness, monkeypatch):
    engine, state, _ = engine_lesson(harness, monkeypatch)
    state = invoke(engine, state, kind='explain_or_observe', content={'text': 'Colour the big letter T.', 'parent_check': True})
    active = state['active_activity']
    row = next(a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if a['action_id'] == active['id'])
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_actions', row['id'], {'origin': 'required_book'})
    state = engine.state(state['session_id'])
    assert state['active_activity']['interaction']['status'] == 'awaiting_work'
    with pytest.raises(Exception):  # Continue alone cannot skip the grown-up's look.
        event(engine, state, 'continue')
    state = event(engine, engine.state(state['session_id']), 'parent_check', {'result': 'try_again'})
    assert state['active_activity']['id'] == active['id']
    state = event(engine, state, 'parent_check', {'result': 'checked'})
    assert harness.ctx.store.get('lesson_actions', row['id'])['status'] == 'answered'
    checks = [e['payload']['result'] for e in harness.ctx.store.find('activity_events', session_id=state['session_id'])
              if e['event_type'] == 'parent_check']
    assert checks == ['try_again', 'checked'] and not harness.ctx.store.all('attempts')
