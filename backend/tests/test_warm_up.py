"""Before a lesson: last time, today and next, plus the last lesson's closing words."""


def test_warm_up_names_neighbours_and_reuses_the_last_closing(harness, monkeypatch):
    from tests.test_activity_engine import engine_lesson, event
    from tutoring import interactive
    engine, state, seeded = engine_lesson(harness, monkeypatch)
    store = harness.ctx.store
    session = store.get('tutor_sessions', state['session_id'])
    done = store.get('topics', session['topic_id'])
    with store.transaction() as tx:
        tx.update('topics', done['id'], {'completed': True, 'is_core': True, 'chapter_order': 1})
        today = tx.insert('topics', {'subject_id': done['subject_id'], 'title': 'Lesson B', 'page_start': 3, 'page_end': 3,
                                     'chapter_order': 2, 'is_core': True})
        tx.insert('topics', {'subject_id': done['subject_id'], 'title': 'Lesson C', 'page_start': 4, 'page_end': 4,
                             'chapter_order': 3, 'is_core': True})
    warm = harness.ctx.tutor.warm_up(store.get('topics', today['id']))
    assert warm['today'] == 'Lesson B' and warm['next'] == 'Lesson C'
    assert warm['last']['title'] == done['title'] and warm['last']['summary']  # the saved guide's closing words
    first = harness.ctx.tutor.warm_up(store.get('topics', done['id']))
    assert first['last'] is None and first['next'] == 'Lesson B'
