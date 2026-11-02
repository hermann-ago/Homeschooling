"""Guided lessons: the AI adds a teacher's voice, but the book text is always read in full and in order."""
import pytest

from tests.test_tutoring import FakeTTS, seed_history
from tutoring import audio as audio_mod
from tutoring import guide as guide_mod
from tutoring import passages

BOOK = [{"text": f"Book sentence {i}."} for i in range(8)]


def spoken(guide):
    return [(s["kind"], s["source"]) for s in guide["sentences"]]


def test_expand_reads_every_book_sentence_once_in_order_whatever_the_plan_says():
    plan = {"mode": "expand", "segments": [
        {"type": "intro", "text": "Hello **Lucas**. Today we meet the Mongols."},
        {"type": "read", "from": 0, "to": 1},
        {"type": "explain", "text": "A tribe is a big family group."},
        {"type": "read", "from": 4, "to": 5},   # skips 2-3: they are read here anyway
        {"type": "read", "from": 3, "to": 4},   # overlaps: nothing is read twice
        {"type": "recap", "text": "The Mongols joined together."},  # 6-7 were never planned
        {"type": "sing", "text": "Unknown segment types are dropped."},
    ]}
    guide = guide_mod.build(BOOK, plan)
    books = [source for kind, source in spoken(guide) if kind == "book"]
    assert books == list(range(8))
    assert guide["sentences"][0]["text"] == "Hello Lucas."  # markdown removed
    assert [s["type"] for s in guide["segments"]] == ["intro", "read", "explain", "read", "read", "read", "recap"]
    assert guide["segments"][3:6] == [{"type": "read", "from": 2, "to": 5},  # starts where reading stopped
                                      {"type": "read", "from": 6, "to": 6},  # an overlap moves on, never repeats
                                      {"type": "read", "from": 7, "to": 7}]  # the unplanned tail, before the recap
    assert all(s["text"] == BOOK[s["source"]]["text"] for s in guide["sentences"] if s["kind"] == "book")


def test_a_plan_without_reading_still_reads_the_book():
    guide = guide_mod.build(BOOK[:2], {"segments": [{"type": "intro", "text": "Let us begin."}]})
    assert spoken(guide) == [("teacher", None), ("book", 0), ("book", 1)]


def test_fuller_introduction_survives_preparation_and_activity_projection():
    welcome = ' '.join(['Olá, vamos descobrir os sons com calma e fazer uma pequena brincadeira.'] * 15)
    assert guide_mod.MAX_TEACHER_CHARACTERS < len(welcome) < guide_mod.MAX_INTRO_CHARACTERS
    guide = guide_mod.build(BOOK[:2], {'mode': 'expand', 'segments': [
        {'type': 'intro', 'text': welcome},
        {'type': 'read', 'from': 0, 'to': 1},
        {'type': 'explain', 'text': 'Uma explicação curta. ' * 100},
    ]})
    assert guide['segments'][0]['text'] == welcome
    introduction = next(activity for activity in guide_mod.guide_activities(guide) if activity['kind'] == 'introduce')
    assert introduction['content']['text'] == welcome
    assert [sentence['source'] for sentence in guide['sentences'] if sentence['kind'] == 'book'] == [0, 1]
    explanation = next(segment for segment in guide['segments'] if segment['type'] == 'explain')
    assert len(explanation['text']) <= guide_mod.MAX_TEACHER_CHARACTERS


def test_introduction_remains_bounded_separately_from_other_teacher_content():
    guide = guide_mod.build(BOOK[:1], {'mode': 'expand', 'segments': [{'type': 'intro', 'text': 'A' * 3000}]})
    assert len(guide['segments'][0]['text']) == guide_mod.MAX_INTRO_CHARACTERS


def test_tidy_rewrites_a_teacher_script_and_keeps_where_it_came_from():
    plan = {"mode": "tidy", "segments": [
        {"type": "read", "from": 0, "to": 3, "text": "Look at the word ship. It has the sound sh. Say it with me."},
        {"type": "read", "from": 9, "to": 12, "text": "An invalid range keeps the text but not the link."},
    ]}
    guide = guide_mod.build(BOOK, plan)
    assert guide["mode"] == "tidy"
    assert [s["source"] for s in guide["sentences"]] == [0, 1, 2, None]


def test_tidy_reading_keeps_full_directions_instead_of_cutting_at_700_characters():
    text=' '.join(['Read the instructions carefully before beginning your work.']*15)+' Circle the two correct answers.'
    assert len(text)>700
    built=guide_mod.build(BOOK[:2],{'mode':'tidy','segments':[{'type':'read','from':0,'to':1,'text':text}]})
    assert built['segments'][0]['text']==text
    assert ' '.join(s['text'] for s in built['sentences'])==text


def test_tidy_does_not_substitute_raw_source_when_spoken_text_is_missing():
    with pytest.raises(ValueError):guide_mod.GuidePlan.model_validate({'mode':'tidy','segments':[{'type':'read','from':0,'to':1}]})
    with pytest.raises(guide_mod.GuideError,match='raw extraction was not substituted'):
        guide_mod.build(BOOK,{'mode':'tidy','segments':[{'type':'read','from':0,'to':1}]})


def test_tidy_read_source_activity_keeps_teaching_text_and_source_range():
    built=guide_mod.build(BOOK,{'mode':'tidy','segments':[{'type':'activity','activity_kind':'read_source',
        'content':{'text':'Look at the large letter. Trace it slowly.','first':0,'last':1}}]})
    assert built['segments']==[{'type':'read','from':0,'to':1,'text':'Look at the large letter. Trace it slowly.'}]
    assert all('Book sentence' not in s['text'] for s in built['sentences'])


def test_a_changed_passage_makes_the_guide_out_of_date(harness, monkeypatch):
    s = seed_history(harness)
    topic_id = s["genghis"]["id"]
    monkeypatch.setattr(guide_mod, "write_plan", lambda text, models, **kwargs: ({"segments": [{"type": "read", "from": 0, "to": 9}]}, "test-model"))
    body = {"learner": s["lucas"]["id"], "topic": topic_id}
    assert harness.call("POST", "/api/tutor/reader/guide", json=body).status_code == 200
    with harness.ctx.store.transaction() as tx:
        tx.update("topics", topic_id, {"stop_before": None})
    reader = harness.call("GET", "/api/tutor/reader", params=body).json()
    assert reader["guide"]["current"] is False
    voice = harness.call("POST", "/api/tutor/reader/narration", json={**body, "guide": True})
    assert voice.status_code == 400


def test_the_tutor_bridge_cannot_write_guides_and_ai_failures_are_explained(harness, monkeypatch):
    s = seed_history(harness)
    body = {"learner": s["lucas"]["id"], "topic": s["genghis"]["id"]}
    assert harness.call("POST", "/api/tutor/reader/guide", role="tutor", json=body).status_code == 403

    def broken(text, models, **kwargs):
        raise guide_mod.GuideError("The AI could not write the guide: quota")
    monkeypatch.setattr(guide_mod, "write_plan", broken)
    failed = harness.call("POST", "/api/tutor/reader/guide", json=body)
    assert failed.status_code == 502 and "quota" in failed.json()["detail"]
    assert harness.ctx.store.find("guides", topic_id=s["genghis"]["id"]) == []


def test_unavailable_models_do_not_trigger_an_upgrade_or_provider_switch(harness, monkeypatch):
    import pytest
    calls = []

    def writer(text, model):
        calls.append(model)
        raise guide_mod.GuideError("404 NOT_FOUND")

    monkeypatch.setattr(guide_mod, "gemini_writer", writer)
    with pytest.raises(guide_mod.GuideError, match="404"):
        guide_mod.write_plan("prompt", ("retired-model", "working-model"))
    assert calls == ["gpt-6-luna"]


def test_duplicate_complete_plans_recover_cached_response_without_provider_call(harness, monkeypatch):
    import json
    import httpx
    from services.ai_provider import validated, StructuredResponseError
    from tests.test_ai_costs import SmallResponse

    plan = {"mode": "expand", "segments": [
        {"type": "intro", "text": "Hello, Lucas."},
        {"type": "read", "from": 0, "to": 7},
        {"type": "action", "text": "What joined the tribes?", "action_kind": "answer"}]}
    raw = json.dumps(plan)
    normalized = guide_mod.GuidePlan.model_validate(plan).model_dump(by_alias=True)
    response = raw + '<|im_end|>,\u4f0a\u4eba\n' + raw + ']} \n' + json.dumps(normalized)
    assert validated(response, guide_mod.GuidePlan) == normalized

    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200, json={'input_tokens': 100})
        return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 100},
            'output': [{'content': [{'type': 'output_text', 'text': response}]}]})
    ai = harness.ctx.ai
    ai.http = httpx.Client(transport=httpx.MockTransport(respond))
    assert ai.generate('Duplicate lesson plan', schema=guide_mod.GuidePlan) == normalized
    harness.restart()
    harness.ctx.ai.http = httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('Cached lesson sent again')))
    assert harness.ctx.ai.generate('Duplicate lesson plan', schema=guide_mod.GuidePlan) == normalized
    assert len(calls) == 2
    # Grading and all other schemas must not inherit lesson-specific recovery.
    with pytest.raises(StructuredResponseError):
        validated('{"answer":"yes"}{"answer":"yes"}', SmallResponse)


@pytest.mark.parametrize('tail', [
    '{"mode":"tidy","segments":[{"type":"read","text":"Different."}]}',
    '{"mode":"expand","segments":[',
    'Extra commentary',
    '{"mode":"expand","segments":[],"unrequested":true}',
])
def test_duplicate_recovery_rejects_ambiguous_incomplete_or_extra_content(tail):
    import json
    from services.ai_provider import validated, StructuredResponseError
    raw = json.dumps({"mode": "expand", "segments": [{"type": "read", "from": 0, "to": 1}]})
    with pytest.raises(StructuredResponseError):
        validated(raw + '\n' + tail, guide_mod.GuidePlan)


