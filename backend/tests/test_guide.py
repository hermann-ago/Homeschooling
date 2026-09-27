"""Guided lessons: the AI adds a teacher's voice, but the book text is always read in full and in order."""
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


def test_tidy_rewrites_a_teacher_script_and_keeps_where_it_came_from():
    plan = {"mode": "tidy", "segments": [
        {"type": "read", "from": 0, "to": 3, "text": "Look at the word ship. It has the sound sh. Say it with me."},
        {"type": "read", "from": 9, "to": 12, "text": "An invalid range keeps the text but not the link."},
    ]}
    guide = guide_mod.build(BOOK, plan)
    assert guide["mode"] == "tidy"
    assert [s["source"] for s in guide["sentences"]] == [0, 1, 2, None]


def test_guided_lesson_is_written_saved_voiced_and_kept_apart_from_the_book_voice(harness, tmp_path, monkeypatch):
    s = seed_history(harness)
    topic = harness.ctx.store.get("topics", s["genghis"]["id"])
    prompts = []

    def fake_plan(text, models):
        prompts.append(text)
        return {"mode": "expand", "segments": [
            {"type": "intro", "text": "Hi Lucas. Today we meet Genghis Khan."},
            {"type": "read", "from": 0, "to": 1},
            {"type": "explain", "text": "Felt is thick cloth made of wool."},
            {"type": "read", "from": 2, "to": 99},
            {"type": "recap", "text": "The tribes became one people."}]}, models[0]

    monkeypatch.setattr(guide_mod, "write_plan", fake_plan)
    body = {"learner": s["lucas"]["id"], "topic": topic["id"]}
    made = harness.call("POST", "/api/tutor/reader/guide", json=body)
    assert made.status_code == 200, made.text
    guide = made.json()
    book = passages.load(harness.ctx, topic)["sentences"]
    assert [x["text"] for x in guide["sentences"] if x["kind"] == "book"] == [x["text"] for x in book]
    assert guide["current"] is True and "Lucas" in prompts[0] and "[0] " in prompts[0]
    saved = harness.ctx.store.find("guides", topic_id=topic["id"])
    assert len(saved) == 1 and (harness.drive / saved[0]["guide_path"]).exists()

    again = harness.call("POST", "/api/tutor/reader/guide", json=body).json()
    assert again["guide_id"] == guide["guide_id"] and len(prompts) == 1  # reused, not rewritten

    monkeypatch.setattr("config.home_tutor_dir", lambda: tmp_path / "HomeTutor")
    monkeypatch.setattr(audio_mod, "GoogleTTS", lambda project: FakeTTS())
    estimate = harness.call("POST", "/api/tutor/reader/narration", json={**body, "guide": True}).json()
    assert estimate["characters"] == sum(len(x["text"]) for x in guide["sentences"])
    built = harness.call("POST", "/api/tutor/reader/narration", json={**body, "guide": True, "dry_run": False})
    assert built.status_code == 200, built.text

    reader = harness.call("GET", "/api/tutor/reader", params=body).json()
    assert reader["audio"] == []  # the book text has no voice yet
    assert [t["synchronized"] for t in reader["guide"]["audio"]] == [True]


def test_a_changed_passage_makes_the_guide_out_of_date(harness, monkeypatch):
    s = seed_history(harness)
    topic_id = s["genghis"]["id"]
    monkeypatch.setattr(guide_mod, "write_plan", lambda text, models: ({"segments": [{"type": "read", "from": 0, "to": 9}]}, "test-model"))
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

    def broken(text, models):
        raise guide_mod.GuideError("The AI could not write the guide: quota")
    monkeypatch.setattr(guide_mod, "write_plan", broken)
    failed = harness.call("POST", "/api/tutor/reader/guide", json=body)
    assert failed.status_code == 502 and "quota" in failed.json()["detail"]
    assert harness.ctx.store.find("guides", topic_id=s["genghis"]["id"]) == []


def test_the_next_model_is_tried_when_one_is_unavailable(monkeypatch):
    calls = []

    def writer(text, model):
        calls.append(model)
        if model == "retired-model":
            raise guide_mod.GuideError("404 NOT_FOUND")
        return {"segments": []}

    monkeypatch.setattr(guide_mod, "gemini_writer", writer)
    assert guide_mod.write_plan("prompt", ("retired-model", "working-model")) == ({"segments": []}, "working-model")
    assert calls == ["retired-model", "working-model"]
