"""The shared planner can add pedagogy without fabricating source assignments."""
import copy

import pytest

from services.ai_provider import strict_schema
from tests.test_tutoring import seed_history
from tutoring import guide
from tutoring.books import scan_version


@pytest.mark.parametrize("segment", [
    {"type": "activity", "activity_kind": "request_book_work", "content": {"prompt": "Do invented exercise 999."}},
    {"type": "activity", "activity_kind": "ask_question", "content": {"prompt": "Answer this."}, "source_refs": [{"exercise_id": "invented"}]},
    {"type": "action", "text": "Do this exercise.", "exercise_id": "invented"},
])
def test_planner_cannot_fabricate_required_work_even_through_nested_metadata(segment):
    with pytest.raises(guide.GuideError):
        guide.sanitize_planner_activities({"mode": "expand", "segments": [segment]})


def test_planner_origins_and_concepts_are_bounded_without_mutating_cached_reply():
    plan = {"mode": "expand", "segments": [{"type": "activity", "activity_kind": "tell_it_back",
            "origin": "required_book", "content": {"prompt": "Retell the passage."}, "concept_ids": ["checked", "invented"]}]}
    before = copy.deepcopy(plan)
    clean = guide.sanitize_planner_activities(plan, ["checked"])
    assert plan == before
    assert clean["segments"][0]["origin"] == "adaptive"
    assert clean["segments"][0]["concept_ids"] == ["checked"]


def worksheet_plan():
    return {'mode':'tidy','segments':[
        {'type':'intro','text':'Let us practice a letter.'},
        {'type':'read','from':0,'to':0,'text':'Look at the models for the letter.'},
        {'type':'activity','activity_kind':'request_book_work','origin':'required_book',
         'content':{'prompt':'Trace the letter, then send a photo of your work.',
             'book_name':'An AI book name','printed_page':'wrong','exercise_reference':'Invented 999',
             'evidence_requirement':'handwriting','response_modes':['photo','parent_review'],
             'source_refs':[{'document_id':1,'page':4,'sentence_index':0,'quote':'Trace the letter R.'}]}},
        {'type':'recap','text':'You practiced a letter.'}]}


def worksheet_source():
    return {'document_id':1,'topic_id':2,'book_name':'Original book.pdf','offset':2,
            'sentences':[{'text':'Trace the letter R.'}], 'pages':{4:'Trace the letter R.',5:'Color the picture.'}}


def test_source_bound_paper_task_preserves_capture_and_uses_server_locators():
    plan = worksheet_plan()
    original = copy.deepcopy(plan)
    cleaned = guide.sanitize_planner_activities(plan,book_source=worksheet_source())
    activity = cleaned['segments'][2]
    assert plan == original
    assert activity['activity_kind'] == 'request_book_work' and activity['origin'] == 'required_book'
    assert activity['content']['book_name'] == 'Original book.pdf'
    assert activity['content']['printed_page'] == '2'
    assert activity['content']['exercise_reference'] is None and activity['content']['exercise_id'] is None
    built = guide.build(worksheet_source()['sentences'],cleaned)
    physical = next(a for a in built['activities'] if a['kind']=='request_book_work')
    assert physical['content']['evidence_requirement']=='handwriting'
    assert physical['content']['response_modes']==['photo','parent_review']
    assert built['sentences'][physical['end_sentence']]['pause_after']==physical['id']


@pytest.mark.parametrize('changes',[
    {'document_id':2},{'page':99},{'page':5},{'topic_id':999},
    {'sentence_index':99},{'quote':'Invented letter instruction.'},{'quote':None},
    {'exercise_id':'invented'}, {'version_id':'invented'},
])
def test_paper_task_requires_its_actual_assigned_page_and_instruction(changes):
    plan = worksheet_plan()
    plan['segments'][2]['content']['source_refs'][0].update(changes)
    with pytest.raises(guide.GuideError):
        guide.sanitize_planner_activities(plan,book_source=worksheet_source())


def test_conflicting_unquoted_page_locator_cannot_override_the_verified_instruction():
    plan=worksheet_plan()
    plan['segments'][2]['source_refs']=[{'document_id':1,'page':5,'label':'An invented exercise label'}]
    with pytest.raises(guide.GuideError):
        guide.sanitize_planner_activities(plan,book_source=worksheet_source())


def test_checked_shared_stem_task_uses_page_quote_instead_of_guessed_sentence():
    source=worksheet_source()
    instruction='Complete each word: b) s_n.'
    source['pages'][4]='Complete each word: a) m_on. b) s_n.'
    source['tasks']=[{'document_id':1,'page':4,'instruction':instruction}]
    plan=worksheet_plan()
    ref=plan['segments'][2]['content']['source_refs'][0]
    ref.update(quote=instruction,sentence_index=0)
    before=copy.deepcopy(plan)
    result=guide.sanitize_planner_activities(plan,book_source=source)
    assert plan==before
    saved=result['segments'][2]['content']['source_refs'][0]
    assert saved['quote']==instruction and saved['page']==4 and saved['sentence_index'] is None
    for changes in ({'page':5},{'quote':'Complete each word: b) invented.'}):
        changed=copy.deepcopy(plan);changed['segments'][2]['content']['source_refs'][0].update(changes)
        with pytest.raises(guide.GuideError):guide.sanitize_planner_activities(changed,book_source=source)


def test_preparation_accepts_a_real_paper_task_without_an_exercise_catalog(harness,monkeypatch):
    import hashlib
    from tests.pdf_fixture import make_pdf
    from tests.test_lesson_overview import reach_question
    from tests.test_activity_engine import event
    from tutoring.activity_engine import service
    h=harness
    pdf=make_pdf([['Trace the letter R.']])
    path=h.add_file(pdf,'Books/Tracing.pdf')
    with h.ctx.store.transaction() as tx:
        child=tx.insert('children',{'name':'Practice learner'})
        subject=tx.insert('subjects',{'child_id':child['id'],'name':'Portuguese'})
        book=tx.insert('documents',{'original_filename':'Tracing.pdf','file_path':path,'page_count':1,
            'sha256':hashlib.sha256(pdf).hexdigest(),'size_bytes':len(pdf),'source':'drive'})
        topic=tx.insert('topics',{'subject_id':subject['id'],'document_id':book['id'],'title':'Letter R','page_start':1,'page_end':1})
    plan=worksheet_plan()
    ref=plan['segments'][2]['content']['source_refs'][0]
    ref.update(document_id=book['id'],page=1)
    from tutoring.script_review import Review
    from tutoring.books import ScanResult
    def source_and_review(*args,**kwargs):
        if isinstance(kwargs.get('schema'), type) and issubclass(kwargs['schema'], Review):return {'findings':[]}
        assert kwargs.get('schema') is ScanResult
        return {'pages':[{'page':1,'text':'Trace the letter R.','native_reliable':False,'student_safe':True}],
                'exercises':[{'reference':'1','pages':[1],'prompt':'Trace the letter R.','kind':'handwritten'}],
                'answers':[]}
    monkeypatch.setattr(h.ctx.ai,'generate',source_and_review)
    monkeypatch.setattr(guide,'write_plan',lambda *_a,**_k:(copy.deepcopy(plan),'offline synthetic tutor'))
    result=h.call('POST','/api/tutor/reader/guide',json={'learner':child['id'],'topic':topic['id'],'prepare_voice':False})
    assert result.status_code==200,result.text
    prepared=result.json()
    started=h.call('POST','/api/tutor/interactive/start',json={'learner':child['id'],'topic':topic['id'],'guide_id':prepared['guide_id']})
    assert started.status_code==200,started.text
    engine=service(h.ctx)
    state=reach_question(engine,engine.state(started.json()['session_id']))
    assert state['active_activity']['kind']=='request_book_work'
    assert state['active_activity']['interaction']['status']=='awaiting_work'
    state=event(engine,state,'physical_complete')
    assert state['active_activity']['interaction']['status']=='awaiting_input'
    assert not h.ctx.store.all('attempts') and not h.ctx.store.all('assignment_items')
    h.restart()
    assert service(h.ctx).state(state['session_id'])['active_activity']['kind']=='request_book_work'


def test_saved_provider_reply_can_be_revalidated_without_a_second_purchase(harness,monkeypatch):
    import json
    import httpx
    from services.ai_provider import AIService
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    sent=[]
    def reply(request):
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200,json={'input_tokens':100})
        sent.append(request)
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':100,'output_tokens':100},
            'output':[{'content':[{'type':'output_text','text':json.dumps(worksheet_plan())}]}]})
    ai=AIService(harness.ctx,httpx.Client(transport=httpx.MockTransport(reply)))
    first=ai.generate('Synthetic source-bound worksheet',schema=guide.GuidePlan)
    assert ai.has_valid_cached_reply('Synthetic source-bound worksheet',schema=guide.GuidePlan)
    assert not ai.has_valid_cached_reply('A different source-bound worksheet',schema=guide.GuidePlan)
    with pytest.raises(guide.GuideError):guide.sanitize_planner_activities(first)
    second=ai.generate('Synthetic source-bound worksheet',schema=guide.GuidePlan)
    cleaned=guide.sanitize_planner_activities(second,book_source=worksheet_source())
    assert cleaned['segments'][2]['activity_kind']=='request_book_work'
    assert first==second and len(sent)==1


def test_legacy_instruction_question_and_handwritten_tasks_keep_their_purpose_and_ids():
    built = guide.build([{"text": "First original sentence."}, {"text": "Second original sentence."}],
        {"mode": "expand", "segments": [{"type": "read", "from": 0, "to": 1},
         {"type": "action", "action_kind": "activity", "text": "Point to the illustration."},
         {"type": "action", "action_kind": "answer", "text": "What did you notice?"},
         {"type": "action", "action_kind": "handwritten", "text": "Complete your assigned paper task."}]})
    assert [a["kind"] for a in built["actions"]] == ["activity", "answer", "handwritten"]
    assert [(a["id"], a["kind"]) for a in built["activities"] if a["id"].startswith("action-")] == [
        ("action-1", "explain_or_observe"), ("action-2", "ask_question"), ("action-3", "request_book_work")]
    assert [s["source"] for s in built["sentences"] if s["kind"] == "book"] == [0, 1]


def test_math_retains_original_exercise_kinds_and_versions_after_source_splits():
    sentences = [{"text": f"Original statement {n}."} for n in range(3)]
    exercises = [{"id": "choice-exercise", "version_id": "original-v2", "kind": "answer", "book_name": "Synthetic Math",
                  "reference": "7", "pages": [3], "requirements": [{"evidence": sentences[0]["text"]}]},
                 {"id": "paper-exercise", "version_id": "original-v5", "kind": "handwritten", "book_name": "Synthetic Math",
                  "reference": "8", "pages": [3], "requirements": [{"evidence": sentences[2]["text"]}]}]
    planned = guide.with_book_exercises({"mode": "expand", "segments": [{"type": "read", "from": 0, "to": 2}]}, exercises, sentences, "Math")
    built = guide.build(sentences, planned)
    assert [(a["exercise_id"], a["version_id"], a["kind"]) for a in built["actions"]] == [
        ("choice-exercise", "original-v2", "answer"), ("paper-exercise", "original-v5", "handwritten")]
    assert all(a["origin"] == "required_book" for a in built["activities"] if a.get("exercise_id"))


def test_planner_schema_contains_closed_conditional_activity_content_for_providers():
    schema = strict_schema(guide.GuidePlan)
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert node["required"] == list(node.get("properties", {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    activities=[node for name,node in schema['$defs'].items() if name.startswith('Planned')]
    assert len(activities)==23
    assert schema['$defs']['PlannedAskQuestion']['properties']['content']['$ref']=='#/$defs/QuestionContent'
    with pytest.raises(ValueError):
        guide.GuidePlan.model_validate({"mode": "expand", "segments": [{"type": "intro", "text": "Hi", "css": "custom"}]})


def test_planner_source_ownership_and_private_pages_are_validated_before_save(harness):
    seeded = seed_history(harness)
    with harness.ctx.store.transaction() as tx:
        foreign = tx.insert("documents", {"original_filename": "Another subject.pdf", "page_count": 4})
        tests = tx.insert("documents", {"original_filename": "Synthetic tests.pdf", "page_count": 4, "sha256": "synthetic-tests"})
        tx.insert("subject_books", {"id": "synthetic-tests", "subject_id": seeded["history"]["id"], "document_id": tests["id"], "role": "test"})
        tx.update("chapters", f"{seeded['history']['id']}:21", {"test_document_id": tests["id"], "key_pdf_page": 4})
    subject = seeded["history"]["id"]
    assert guide.validate_source_references(harness.ctx, subject, {"document_id": seeded["book"]["id"], "page": 2})
    for ref in ({"document_id": foreign["id"], "page": 1}, {"document_id": tests["id"], "page": 4},
                {"document_id": seeded["book"]["id"], "page": 999}):
        with pytest.raises(guide.GuideError):
            guide.validate_source_references(harness.ctx, subject, {"nested": [ref]})


def test_combined_book_illustration_requires_a_checked_student_safe_original_page(harness):
    seeded = seed_history(harness)
    with harness.ctx.store.transaction() as tx:
        tx.insert("subject_books", {"id": "combined-book", "subject_id": seeded["history"]["id"],
                  "document_id": seeded["book"]["id"], "role": "combined"})
    source = {"type": "book_illustration", "document_id": seeded["book"]["id"], "page": 2}
    with pytest.raises(guide.GuideError, match="student-safe"):
        guide.validate_source_references(harness.ctx, seeded["history"]["id"], source)
    with harness.ctx.store.transaction() as tx:
        tx.insert("book_units", {"id": "safe-synthetic-scan", "sha256": seeded["book"]["sha256"], "role": "combined",
                  "version": scan_version("combined"), "data": {"pages": [{"page": 2, "student_safe": True, "teacher_material": False}]}})
    assert guide.validate_source_references(harness.ctx, seeded["history"]["id"], source) == source
