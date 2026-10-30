"""Synthetic activity contracts, legacy compatibility and source-safe sequencing."""
import copy
import json

import pytest

from tutoring.activities import ACTIVITY_KINDS, definitions, requires_response, validate_activity
from tutoring import guide


def test_provider_nullable_reading_fields_do_not_change_an_introduction_or_live_explanation():
    from tutoring.activities import ActivityProposal
    content={'text':'Look at the letter.','title':None,'source_refs':[],
             'first':None,'last':None,'document_id':None,'page':None}
    plan=guide.GuidePlan.model_validate({'mode':'tidy','segments':[
        {'type':'activity','activity_kind':'introduce','content':content}]})
    clean=plan.model_dump(by_alias=True)
    assert not {'first','last','document_id','page'} & clean['segments'][0]['content'].keys()
    assert guide.sanitize_planner_activities(clean)['segments'][0]['content']['text']==content['text']
    proposal=ActivityProposal.model_validate({'kind':'explain_or_observe','content':content})
    assert not {'first','last','document_id','page'} & proposal.model_dump()['content'].keys()
    # Non-empty fields belonging to another activity remain an error.
    with pytest.raises(ValueError):guide.GuidePlan.model_validate({'mode':'tidy','segments':[
        {'type':'activity','activity_kind':'introduce','content':{**content,'first':0}}]})


def examples():
    question = {"prompt": "Explain your answer."}
    return {
        "review_progress": {}, "prepare_lesson": {}, "introduce": {"text": "Welcome. Today we compare routes."},
        "read_source": {"text": "The source sentence.", "first": 0, "last": 0},
        "explain_or_observe": {"text": "Look at the route on the map."}, "ask_question": question,
        "request_book_work": {"prompt": "Write in your book.", "book_name": "Synthetic Math", "printed_page": "12", "exercise_reference": "3"},
        "capture_and_confirm": question, "hint_or_follow_up": {"text": "Look at the first step."},
        "give_feedback": {"text": "Your explanation is saved."}, "record_learning_evidence": {"submission_id": "synthetic-submission"},
        "close_lesson": {"text": "We compared two routes.", "unfinished": ["The final question"]},
        "worked_example": {"text": "Watch this example.", "steps": [{"text": "Group the tens."}, {"text": "Add the ones."}], "practice_prompt": "Try a similar example."},
        "explain_thinking": question, "check_prerequisite": {**question, "prerequisite": "Grouping tens"},
        "visual_demonstration": {"text": "Find three.", "visual": {"type": "number_line", "minimum": 0, "maximum": 5, "step": 1, "points": [{"value": 3, "label": "three"}]}},
        "take_break_and_return": {"text": "Take a short break.", "return_message": "We were grouping tens."},
        "tell_it_back": question,
        "compare_and_connect": {**question, "items": [{"id": "a", "title": "First", "text": "A land route."}, {"id": "b", "title": "Second", "text": "A sea route."}]},
        "predict_then_check": {"prompt": "Predict the next step and explain why.", "reveal": {"text": "The next source section."}, "reflection_prompt": "How did your prediction compare?"},
        "find_and_fix_mistake": {"prompt": "Find and fix the error.", "example": "2 + 2 = 5"},
        "apply_somewhere_new": {**question, "scenario": "Use the method to count a different collection."},
        "recall_later": {"prompt": "Explain the idea before looking at the example."},
    }


def test_all_twenty_three_tools_share_closed_provider_independent_contracts():
    catalog = definitions()
    assert tuple(item["kind"] for item in catalog) == ACTIVITY_KINDS
    assert set(examples()) == set(ACTIVITY_KINDS) and len(catalog) == 23
    for definition in catalog:
        content = validate_activity(definition["kind"], examples()[definition["kind"]])
        assert content is not examples()[definition["kind"]]
        assert definition["input_schema"]["additionalProperties"] is False
        assert definition["result_schema"]["additionalProperties"] is False
        assert definition["version"] == 1
        assert bool(definition["renderer"]) == definition["child_facing"]
        json.dumps(definition, allow_nan=False)
    assert all(not item["child_facing"] for item in catalog if item["kind"] in
               ("review_progress", "prepare_lesson", "record_learning_evidence"))


@pytest.mark.parametrize("content", [
    {"text": "<script>alert(1)</script>"}, {"text": "<img src=x onerror=alert(1)>"},
    {"text": "javascript:alert(1)"}, {"text": "data:text/html,hello"},
    {"text": "Hello", "html": "custom markup"}, {"text": "Hello", "css": "color:red"},
])
def test_model_content_cannot_supply_markup_styles_or_executable_ui(content):
    with pytest.raises(ValueError):
        validate_activity("introduce", content)


def test_response_modes_require_real_choices_and_normalize_old_dictation_label():
    captured = validate_activity("capture_and_confirm", {"prompt": "What did you write?", "response_modes": ["audio", "text"]})
    assert captured["response_modes"] == ["device_dictation", "text"]
    assert captured["confirmation_required"] is True
    with pytest.raises(ValueError):
        validate_activity("ask_question", {"prompt": "Choose.", "response_modes": ["choice"]})
    with pytest.raises(ValueError):
        validate_activity("ask_question", {"prompt": "Choose.", "response_modes": ["choice"], "choices": [{"id": "a", "label": "First"}, {"id": "a", "label": "Second"}]})
    assert requires_response("explain_thinking", examples()["explain_thinking"])
    assert not requires_response("introduce", examples()["introduce"])


def test_answer_formats_are_validated_and_legacy_choices_still_work():
    true_false = validate_activity('ask_question', {'prompt':'A triangle has three sides.', 'answer_format':'true_false'})
    assert true_false['response_modes'] == ['choice','text']
    assert true_false['choices'] == [{'id':'true','label':'True'},{'id':'false','label':'False'}]
    portuguese = validate_activity('request_book_work', {'prompt':'Verdadeiro ou falso?', 'answer_format':'true_false',
        'choices':[{'id':'true','label':'Verdadeiro'},{'id':'false','label':'Falso'}]})
    assert portuguese['choices'][1]['label']=='Falso'
    for bad in (
        {'answer_format':'true_false','choices':[{'id':'a','label':'True'},{'id':'b','label':'False'}]},
        {'answer_format':'multiple_select','choices':[{'id':'a','label':'Only option'}]},
        {'answer_format':'single_choice','choices':[{'id':'a','label':'A','correct':True},{'id':'b','label':'B'}]},
        {'answer_format':'text','choices':[{'id':'a','label':'A'},{'id':'b','label':'B'}]},
    ):
        with pytest.raises(ValueError):validate_activity('ask_question',{'prompt':'Choose.',**bad})
    assert validate_activity('ask_question', {'prompt':'Choose.', 'response_modes':['choice'],
        'choices':[{'id':'a','label':'A'},{'id':'b','label':'B'}]})['answer_format']=='single_choice'


def test_source_choice_format_survives_required_exercise_adapter():
    kind, content, origin=guide._legacy_activity({'type':'action','action_kind':'handwritten','exercise_id':'original',
        'exercise':{'answer_format':'true_false','choices':[{'id':'true','label':'Verdadeiro'},{'id':'false','label':'Falso'}]}}, 'Do the original task.')
    assert kind=='request_book_work' and origin=='required_book'
    assert content['answer_format']=='true_false' and content['choices'][1]['label']=='Falso'
    assert content['exercise_id']=='original'


def test_legacy_book_controls_use_explicit_public_directions_never_answers():
    from tutoring.answer_controls import book_controls
    assert book_controls({'section':'True or false','prompt':'The tribes joined together.','answer':'PRIVATE'})['answer_format']=='true_false'
    assert book_controls({'prompt':'Verdadeiro ou falso: um triângulo tem três lados.'})['choices'][1]['label']=='Falso'
    assert book_controls({'section':'True or false','prompt':'1. First statement.\n2. Second statement.'})=={}
    assert book_controls({'prompt':'What happened?', 'answer':'True'})=={}
    source={'section':'Multiple choice','prompt':'Choose the answer.\nA. First option.\nB. Second option.'}
    assert book_controls(source)['choices']==[{'id':'A','label':'A. First option.'},{'id':'B','label':'B. Second option.'}]
    assert book_controls({**source,'prompt':source['prompt']+'\nA wrapped or unclear continuation.'})=={}
    binary={'section':'C. True or False. Write true or false.',
        'prompt':'C. True or False. Write true or false.\n15. The wall was stronger.', 'answer_format':None}
    assert book_controls(binary)['answer_format']=='true_false'
    lower={'section':'B. Multiple Choice. Circle the best choice.',
        'prompt':'B. Multiple Choice. Circle the best choice.\n9. Choose a tool.\na. A saw\nb. A hammer'}
    assert book_controls(lower)['choices']==[{'id':'a','label':'a. A saw'},{'id':'b','label':'b. A hammer'}]
    assert book_controls({**lower,'prompt':lower['prompt']+'\na continuation'})=={}


def test_book_question_speech_avoids_repeated_section_heading_and_keeps_statement():
    exercise={'id':'original','version_id':'original-v1','book_name':'SOTW2_Tests.pdf','pages':[88],
        'printed_page':'85','reference':'15','section':'C. True or False. Write true or false.',
        'prompt':'C. True or False. Write true or false.\n15. The wall was stronger.', 'kind':'answer'}
    plan=guide.with_book_exercises({'mode':'expand','segments':[{'type':'read','from':0,'to':0}]},
        [exercise],[{'text':'An original source sentence.'}],'History')
    action=next(s for s in plan['segments'] if s.get('exercise_id'))
    assert action['text']=='Your book, page 85, exercise 15.\n\nThe wall was stronger.'
    assert action['exercise']['prompt']==exercise['prompt']
    built=guide.build([{'text':'An original source sentence.'}],plan)
    work=next(a for a in built['activities'] if a['kind']=='request_book_work')
    assert work['content']['book_name']=='SOTW2_Tests.pdf'
    assert work['content']['answer_format']=='true_false'


@pytest.mark.parametrize("visual", [
    {"type": "number_line", "minimum": 0, "maximum": float("nan")},
    {"type": "number_line", "minimum": 0, "maximum": float("inf")},
    {"type": "number_line", "minimum": 0, "maximum": 2, "step": 0.00001},
    {"type": "number_line", "minimum": 0, "maximum": 2, "points": [{"value": 3, "label": "Outside"}]},
    {"type": "book_illustration", "document_id": 1},
    {"type": "diagram", "nodes": [{"id": "a", "label": "One"}], "edges": [{"from_id": "a", "to_id": "missing"}]},
])
def test_visuals_use_finite_bounded_values_and_real_structured_references(visual):
    with pytest.raises(ValueError):
        validate_activity("visual_demonstration", {"text": "Look here.", "visual": visual})


BOOK = [{"text": f"Book sentence {i}."} for i in range(8)]


def test_legacy_normalization_preserves_original_task_ids_sentences_and_audio_identity():
    built = guide.build(BOOK, {"mode": "expand", "segments": [
        {"type": "intro", "text": "Welcome to the lesson."}, {"type": "read", "from": 0, "to": 7},
        {"type": "action", "text": "What did you notice?", "action_kind": "answer"},
        {"type": "recap", "text": "We looked closely."}]})
    legacy = {key: copy.deepcopy(value) for key, value in built.items() if key != "activities"}
    before = copy.deepcopy(legacy)
    sha = guide.guide_sha(legacy["sentences"])
    normalized = guide.guide_activities(legacy)
    assert legacy == before and guide.guide_sha(legacy["sentences"]) == sha
    assert [item["kind"] for item in normalized] == ["introduce", "read_source", "ask_question", "close_lesson"]
    assert normalized[2]["id"] == built["actions"][0]["id"] == "action-1"
    assert normalized[2]["resume_index"] == built["actions"][0]["resume_index"]
    assert normalized[1]["content"]["text"] == " ".join(s["text"] for s in BOOK)


def test_typed_planner_activities_validate_and_keep_future_reveal_out_of_narration():
    plan = {"mode": "expand", "segments": [
        {"type": "activity", "activity_kind": "predict_then_check", "content": examples()["predict_then_check"]},
        {"type": "read", "from": 0, "to": 7}]}
    parsed = guide.GuidePlan.model_validate(plan).model_dump(by_alias=True, exclude_none=True)
    built = guide.build(BOOK, parsed)
    assert built["activities"][0]["kind"] == "predict_then_check"
    assert built["activities"][0]["id"] == "activity-1"
    assert "The next source section." not in [s["text"] for s in built["sentences"]]
    assert [s["text"] for s in built["sentences"] if s["kind"] == "book"] == [s["text"] for s in BOOK]
    with pytest.raises(ValueError):
        guide.GuidePlan.model_validate({"mode": "expand", "segments": [
            {"type": "activity", "activity_kind": "unknown", "content": {"text": "Hello"}}]})


def test_math_interleaves_only_after_verified_required_reading_and_history_waits():
    exercises = [{"id": f"ex-{index}", "version_id": f"v-{index}", "reference": str(index), "book_name": "Synthetic workbook",
                  "printed_page": 12, "kind": "handwritten", "requirements": [{"evidence": BOOK[last]["text"]}]} for index, last in enumerate((1, 5))]
    base = {"mode": "expand", "segments": [{"type": "read", "from": 0, "to": 7}, {"type": "recap", "text": "Done."}]}
    math = guide.build(BOOK, guide.with_book_exercises(base, exercises, BOOK, "Math"))
    assert [s["type"] for s in math["segments"]] == ["read", "action", "read", "action", "read", "recap"]
    assert [a["exercise_id"] for a in math["actions"]] == ["ex-0", "ex-1"]
    assert [s["source"] for s in math["sentences"] if s["kind"] == "book"] == list(range(8))
    history = guide.build(BOOK, guide.with_book_exercises(base, exercises, BOOK, "History"))
    first_action = history["actions"][0]["start_sentence"]
    assert len([s for s in history["sentences"][:first_action] if s["kind"] == "book"]) == len(BOOK)
    unclear = copy.deepcopy(exercises[:1])
    unclear[0]["requirements"].append({"evidence": "An unlocated prerequisite."})
    uncertain = guide.build(BOOK, guide.with_book_exercises(base, unclear, BOOK, "Math"))
    assert uncertain["actions"][0]["start_sentence"] == len(BOOK)


def test_legacy_package_adds_contract_without_rewriting_saved_content(harness):
    from tests.test_tutoring import seed_history
    from tutoring import passages
    seeded = seed_history(harness)
    topic = harness.ctx.store.get("topics", seeded["genghis"]["id"])
    passage = passages.load(harness.ctx, topic)
    built = guide.build(passage["sentences"], {"mode": "expand", "segments": [{"type": "read", "from": 0, "to": 999}]})
    with harness.ctx.store.transaction() as tx:
        row = guide.save(tx, topic, passage, built, model="synthetic", language="en-US")
    before = harness.ctx.file_bytes(row["guide_path"], None)
    package = guide.package(harness.ctx, harness.ctx.store.get("guides", row["id"]), True)
    assert package["activity_contract_version"] == 1 and package["activities"][0]["kind"] == "read_source"
    assert package["passage_sha256"] == guide.guide_sha(built["sentences"])
    assert harness.ctx.file_bytes(row["guide_path"], None) == before
