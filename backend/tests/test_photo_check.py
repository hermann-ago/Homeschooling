"""Book work answered with a photo: the lesson moves on while the check runs."""
import pytest

from tests.test_activity_engine import event, invoke
from tests.test_interactive import prepare, start
from tests.test_lesson_overview import reach_question
from tests.test_paced_book_work import PNG, photo
from tutoring import photo_check
from tutoring.activity_engine import service
from tutoring.service import TutorConflict, TutorError


def lesson(harness, monkeypatch, inline=True):
    """The seeded lesson with its question turned into required book work."""
    seeded, guide = prepare(harness, monkeypatch)
    legacy = start(harness, seeded, guide)
    engine = service(harness.ctx)
    engine.background_checks = not inline
    state = engine.state(legacy['session_id'])
    question = next(a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if a['activity_kind'] == 'ask_question')
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_actions', question['id'], {'origin': 'required_book', 'activity_kind': 'request_book_work'})
    return engine, reach_question(engine, engine.state(state['session_id'])), question


def snap(harness, engine, state, name='page.png'):
    evidence = photo(harness, state, name)
    return event(engine, engine.state(state['session_id']), 'snap_work', {'evidence_ids': [evidence]})


def reader(result='Correct', answer='He united the tribes', uncertain=False, feedback='Well done.'):
    def read(prompt, **kwargs):
        assert 'teacher_key' in prompt and kwargs['images']
        import json
        tasks = json.loads(prompt.split(photo_check.TASKS)[1])
        return {'items': [{'item_id': t['item_id'], 'answer': answer, 'uncertain': uncertain, 'result': result, 'feedback': feedback} for t in tasks]}
    return read


def test_a_photo_moves_the_lesson_on_and_a_right_answer_turns_green(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    assert state['active_activity']['snap'] is True
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader())
    evidence = photo(harness, state)
    state = event(engine, engine.state(state['session_id']), 'snap_work', {'evidence_ids': [evidence]})
    assert state['active_activity']['kind'] == 'close_lesson' and state['checking'] is False
    row = harness.ctx.store.get('lesson_actions', question['id'])
    assert row['status'] == 'answered'
    assert state['progress']['items'] == [{'id': question['action_id'], 'outcome': 'first_try'}]
    attempt = harness.ctx.store.all('attempts')[0]
    assert attempt['first_result'] == 'Correct' and attempt['first_answer'] == 'He united the tribes'
    response = harness.ctx.store.find('activity_responses', session_id=state['session_id'])[0]
    assert response['method'] == 'photo' and response['status'] == 'assessed' and response['evidence_ids'] == [evidence]
    state = event(engine, state, 'finish')
    assert harness.ctx.store.get('tutor_sessions', state['session_id'])['status'] == 'completed'


def test_a_wrong_answer_waits_in_the_tracker_and_can_be_fixed_then_returns(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He fought them', feedback='Look again at the tribes.'))
    state = snap(harness, engine, state)
    item = state['progress']['items'][0]
    assert item['outcome'] == 'fix' and item['check']['read'] == 'He fought them' and item['check']['feedback'] == 'Look again at the tribes.'
    # The tracker can voice the tutor's saved reply for this exercise.
    reply = harness.ctx.store.get('lesson_dialogue', item['check']['reply_id'])
    assert reply['role'] == 'teacher' and reply['text'] == 'Look again at the tribes.'
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'fix'
    closing = state['active_activity']['id']
    state = event(engine, state, 'fix_work', {'activity_id': question['action_id']})
    active = state['active_activity']
    assert active['id'] == question['action_id'] and active['status'] == 'pending' and active['snap']
    assert active['fix'] == {'read': 'He fought them', 'result': 'Not yet', 'feedback': 'Look again at the tribes.'}
    with pytest.raises(TutorConflict):  # One fix at a time.
        event(engine, state, 'fix_work', {'activity_id': question['action_id']})
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader())
    state = snap(harness, engine, state, 'again.png')
    assert state['active_activity']['id'] == closing
    assert state['progress']['items'][0]['outcome'] == 'again'
    row = harness.ctx.store.get('lesson_actions', question['id'])
    assert row['status'] == 'answered' and not row['return_cursor']
    assert len(harness.ctx.store.find('activity_responses', session_id=state['session_id'])) == 2
    # The second check knows it is a second try and what was said the first time.
    tasks = [job['input_snapshot']['tasks'][0] for job in sorted(harness.ctx.store.find('activity_jobs', session_id=state['session_id']),
             key=lambda j: str(j['created_at'])) if (job.get('input_snapshot') or {}).get('tasks')]
    assert [t['try_number'] for t in tasks] == [1, 2]
    assert tasks[0]['earlier_replies'] == [] and 'Look again at the tribes.' in tasks[1]['earlier_replies'][-1]


def test_fix_later_returns_without_changing_the_result(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He fought them'))
    state = snap(harness, engine, state)
    closing = state['active_activity']['id']
    state = event(engine, state, 'fix_work', {'activity_id': question['action_id']})
    state = event(engine, state, 'fix_later')
    assert state['active_activity']['id'] == closing
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'fix'
    # Finishing with something left to fix is allowed; it stays to practise and can be continued later.
    state = event(engine, state, 'finish')
    summary = harness.ctx.store.get('tutor_sessions', state['session_id'])['completion_summary']
    assert [w['activity_id'] for w in summary['pending_work']] == [question['action_id']]
    assert summary['photo_checks']['to_practise'] == [question['action_id']]
    assert state['progress']['items'][0]['outcome'] == 'practise'


def test_an_unsure_reading_is_not_marked_wrong(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He ??? them', uncertain=True, feedback='I could not read this.'))
    state = snap(harness, engine, state)
    assert state['progress']['items'][0]['check']['result'] == 'Unreadable'
    assert harness.ctx.store.all('attempts')[0]['first_result'] == 'Unreadable'


def test_a_failed_check_keeps_the_photo_and_retries(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError('provider down')
    monkeypatch.setattr(harness.ctx.ai, 'generate', fail)
    state = snap(harness, engine, state)
    item = state['progress']['items'][0]
    assert item['outcome'] == 'unchecked' and 'Nothing was marked wrong' in item['check']['error']
    assert state['checking'] is False and not harness.ctx.store.all('attempts')
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader())
    state = event(engine, state, 'retry_photo_check', {'activity_id': question['action_id']})
    assert state['progress']['items'][0]['outcome'] == 'first_try'


def test_one_photo_covers_a_whole_true_or_false_set_with_separate_results(harness, monkeypatch):
    engine, state, _ = lesson(harness, monkeypatch)
    statements = ('The Mongols lived in tents.', 'Genghis Khan was born in Rome.', 'The tribes were united.')
    for statement in statements:
        state = invoke(engine, state, content={'prompt': statement, 'answer_format': 'true_false'})
    rows = sorted((a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id'])
                   if a['prompt'] in statements and (a.get('activity_content') or {}).get('answer_format') == 'true_false'),
                  key=lambda a: statements.index(a['prompt']))
    with harness.ctx.store.transaction() as tx:
        for order, row in enumerate(rows):
            tx.update('lesson_actions', row['id'], {'origin': 'required_book', 'source_refs': [{'document_id': 1, 'page': 9}],
                                                    'parent_activity_id': None, 'activity_order': -300 + order})
        tx.update('lesson_playback', state['session_id'], {'action_id': rows[0]['action_id']})
    state = engine.state(state['session_id'])

    def read(prompt, **kwargs):
        assert photo_check.TOGETHER.format(n=3) in prompt  # one photo is meant to show all three
        return {'items': [{'item_id': row['action_id'], 'answer': 'T', 'uncertain': False,
                           'result': 'Not yet' if index == 1 else 'Correct', 'feedback': 'Checked.'} for index, row in enumerate(rows)]}
    monkeypatch.setattr(harness.ctx.ai, 'generate', read)
    # The child is shown every question the one photo covers, not just the first.
    assert state['active_activity']['id'] == rows[0]['action_id']
    assert state['active_activity']['together'] == [{'id': row['action_id'], 'prompt': row['prompt']} for row in rows[1:]]
    state = snap(harness, engine, state)
    statuses = [harness.ctx.store.get('lesson_actions', row['id'])['status'] for row in rows]
    assert statuses == ['answered', 'fix', 'answered']
    assert len(harness.ctx.store.find('activity_jobs', session_id=state['session_id'], kind='photo_check')) == 1


def test_a_running_check_holds_the_finish_and_a_stale_result_is_not_applied(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch, inline=False)
    started = []
    monkeypatch.setattr(photo_check.threading, 'Thread', lambda **kwargs: type('T', (), {'start': lambda self: started.append(kwargs)})())
    state = snap(harness, engine, state)
    assert state['checking'] is True and state['progress']['items'][0]['outcome'] == 'checking' and len(started) == 1
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'checking'
    with pytest.raises(TutorConflict):
        event(engine, state, 'finish')
    # The child goes back to the exercise before the result arrives: that result must not overwrite the new try.
    state = event(engine, engine.state(state['session_id']), 'go_back')
    assert state['active_activity']['id'] == question['action_id'] and state['active_activity']['status'] == 'pending'
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'old photo'))
    job = harness.ctx.store.find('activity_jobs', session_id=state['session_id'], kind='photo_check')[0]
    photo_check.run(engine, job['id'])
    assert harness.ctx.store.get('activity_jobs', job['id'])['status'] == 'completed'
    assert harness.ctx.store.get('lesson_actions', question['id'])['status'] == 'pending' and not harness.ctx.store.all('attempts')


def test_paced_lessons_and_other_steps_do_not_take_photo_answers(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    state = event(engine, state, 'skip')
    assert not state['active_activity'].get('snap')
    with pytest.raises(TutorError):
        event(engine, state, 'snap_work', {'evidence_ids': ['x']})
    assert PNG


def test_a_photo_answer_still_to_fix_is_where_continuing_the_lesson_starts(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He fought them', feedback='Look again at the tribes.'))
    state = snap(harness, engine, state)
    for _ in range(10):
        if state['active_activity'] and state['active_activity']['kind'] == 'close_lesson':
            break
        state = event(engine, state, 'continue')
    state = event(engine, state, 'finish')
    assert [w['activity_id'] for w in state['learning_summary']['pending_work']] == [question['action_id']]
    continued = engine.repeat(state['session_id'], 'continue-the-fix', unfinished_only=True)
    assert continued['active_activity']['id'] == question['action_id']


def hands_on_lesson(harness, monkeypatch):
    """The seeded lesson with its question turned into hands-on book work (lines drawn on the page)."""
    seeded, guide = prepare(harness, monkeypatch)
    legacy = start(harness, seeded, guide)
    engine = service(harness.ctx)
    engine.background_checks = False
    state = engine.state(legacy['session_id'])
    step = next(a for a in harness.ctx.store.find('lesson_actions', session_id=state['session_id']) if a['activity_kind'] == 'ask_question')
    with harness.ctx.store.transaction() as tx:
        tx.update('lesson_actions', step['id'], {'origin': 'required_book', 'activity_kind': 'explain_or_observe', 'kind': 'activity',
            'prompt': 'Draw a line from each word to its meaning.',
            'activity_content': {'text': 'Draw a line from each word to its meaning.', 'parent_check': True}})
    return engine, reach_question(engine, engine.state(state['session_id'])), step


def test_hands_on_work_is_checked_from_a_photo_first(harness, monkeypatch):
    engine, state, step = hands_on_lesson(harness, monkeypatch)
    assert state['active_activity']['id'] == step['action_id'] and state['active_activity']['snap']
    prompts = []
    def read(prompt, **kwargs):
        prompts.append(prompt)
        return reader('Correct', 'Three lines, each to the right meaning')(prompt, **kwargs)
    monkeypatch.setattr(harness.ctx.ai, 'generate', read)
    state = snap(harness, engine, state)
    assert photo_check.MARKS in prompts[0] and '"evidence": "marks"' in prompts[0]
    item = next(i for i in state['progress']['items'] if i['id'] == step['action_id'])
    assert item['outcome'] == 'first_try' and item['hands_on']
    assert harness.ctx.store.get('lesson_actions', step['id'])['status'] == 'answered'


def test_marks_the_photo_cannot_settle_go_to_a_grown_up(harness, monkeypatch):
    engine, state, step = hands_on_lesson(harness, monkeypatch)
    # Even a "Correct" the reader is unsure of is not passed: a grown-up looks.
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Correct', 'Some faint lines', uncertain=True, feedback='I could not see your lines clearly.'))
    state = snap(harness, engine, state)
    item = next(i for i in state['progress']['items'] if i['id'] == step['action_id'])
    assert item['outcome'] == 'grown_up' and item['check']['feedback'] == 'I could not see your lines clearly.'
    assert harness.ctx.store.get('lesson_actions', step['id'])['status'] == 'fix'
    state = event(engine, state, 'grown_up_checked', {'activity_id': step['action_id']})
    item = next(i for i in state['progress']['items'] if i['id'] == step['action_id'])
    assert item['outcome'] == 'done' and harness.ctx.store.get('lesson_actions', step['id'])['status'] == 'answered'
    assert not harness.ctx.store.find('attempts', session_id=state['session_id'])  # looked at, never graded
    with pytest.raises(TutorConflict):
        event(engine, state, 'grown_up_checked', {'activity_id': step['action_id']})


def test_a_clear_miss_in_hands_on_work_is_fixed_like_any_answer_and_a_grown_up_may_still_pass_it(harness, monkeypatch):
    engine, state, step = hands_on_lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'Two lines cross to the wrong meanings', feedback='Look again at the second word.'))
    state = snap(harness, engine, state)
    item = next(i for i in state['progress']['items'] if i['id'] == step['action_id'])
    assert item['outcome'] == 'fix' and item['hands_on']
    state = event(engine, state, 'fix_work', {'activity_id': step['action_id']})
    assert state['active_activity']['id'] == step['action_id'] and state['active_activity']['snap']
    state = event(engine, state, 'parent_check', {'result': 'checked'})  # the grown-up's look is still offered in the step
    assert harness.ctx.store.get('lesson_actions', step['id'])['status'] == 'answered'


def test_a_grown_up_cannot_pass_ordinary_answers_from_the_tracker(harness, monkeypatch):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader('Not yet', 'He fought them', feedback='Look again.'))
    state = snap(harness, engine, state)
    with pytest.raises(TutorConflict):
        event(engine, state, 'grown_up_checked', {'activity_id': question['action_id']})


@pytest.mark.parametrize('unseen', ['Unanswered', 'Unreadable'])
def test_a_question_the_photo_did_not_show_is_not_a_first_try(harness, monkeypatch, unseen):
    engine, state, question = lesson(harness, monkeypatch)
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader(unseen, '', feedback='This question is not in your photo.'))
    state = snap(harness, engine, state)
    assert state['progress']['items'][0]['outcome'] == 'fix'
    state = event(engine, state, 'fix_work', {'activity_id': question['action_id']})
    monkeypatch.setattr(harness.ctx.ai, 'generate', reader())
    state = snap(harness, engine, state, 'again.png')
    # The first answer the tutor could see was right: right on the first try, not "after another go".
    assert state['progress']['items'][0]['outcome'] == 'first_try'


def test_a_photo_check_reads_the_exercise_page_not_the_whole_lesson(harness, monkeypatch):
    """Photos go to the careful model: a keyed exercise is checked against its own page."""
    from tutoring import interactive
    engine, state, question = lesson(harness, monkeypatch)
    session = harness.ctx.store.get('tutor_sessions', state['session_id'])
    action = harness.ctx.store.get('lesson_actions', question['id'])
    doc = harness.ctx.store.get('topics', action['topic_id'])['document_id']
    monkeypatch.setattr(interactive, 'SHORT_PASSAGE', 10)  # the seeded lesson stands in for a long one
    message = {'id': 'photo-test', 'text': '', 'evidence_ids': []}
    full, _, _ = engine.tutor.interactive._prompt(session, action, message)
    lean, _, _ = engine.tutor.interactive._prompt(session, action, message, source_pages=[(doc, 3)], lean=True)
    assert 'The Mongols came from the north.' in full and 'recent_sessions' in full
    assert 'Genghis Khan united the tribes.' in lean and 'PDF page 3' in lean   # the exercise's own page
    assert 'The Mongols came from the north.' not in lean                     # not the rest of the lesson
    assert 'recent_sessions' not in lean and 'preferences' in lean
    assert len(lean) < len(full)
