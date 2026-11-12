"""The tutor turns the page only where the lesson changes gear."""
from tutoring import tutor_voice


class Db:
    def __init__(self, actions):
        self.actions = actions

    def find(self, table, **filters):
        return [a for a in self.actions if all(a.get(k) == v for k, v in filters.items())]


def step(action_id, kind, order, prompt="", status="pending", parent=None):
    return {"id": f"s:{action_id}", "session_id": "s", "action_id": action_id, "activity_kind": kind,
            "activity_order": order, "prompt": prompt, "status": status, "parent_activity_id": parent}


def test_a_lead_in_only_where_a_reading_an_explanation_or_the_end_follows():
    done = step("exercise-1", "request_book_work", 1000, "Round 4,382,000.")
    lesson = [done, step("question-1", "explain_or_observe", 1001, "Your question", parent="exercise-1"),
              step("exercise-2", "request_book_work", 2000, "Add these."), step("explain-1", "explain_or_observe", 3000, "Rounding keeps the place.")]
    assert tutor_voice.coming_next(Db(lesson), "s", done) is None  # another exercise presents itself
    lesson[2]["status"] = "answered"
    assert tutor_voice.coming_next(Db(lesson), "s", done) == "the tutor's explanation: Rounding keeps the place."
    assert tutor_voice.coming_next(Db([done, step("lesson-close", "close_lesson", 9000, "Finish")]), "s", done) == "the end of the lesson"
    assert tutor_voice.coming_next(Db([done]), "s", done) is None
    # A finished lesson, replayed: by position alone.
    finished = [dict(a, status="answered") for a in lesson]
    assert tutor_voice.coming_next(Db(finished), "s", finished[0], pending_only=False) is None
