"""Exercise pages shared by several lessons: each lesson teaches only its own items."""
import pytest

from tutoring import exercise_assignment as ea, lesson_prompt, page_script

PASSAGE = {'title': 'A New Way of Living', 'sentences': [{'text': 'The cities grew.', 'paragraphIndex': 0}]}
PAGES = [{'document_id': 5, 'page': 98, 'role': 'test', 'book_name': 'Tests'},
         {'document_id': 5, 'page': 99, 'role': 'test', 'book_name': 'Tests', 'printed_page': 96}]
ASSIGNMENT = {'id': 'x', 'method': 'ai', 'pages': [{'document_id': 5, 'page': 98, 'items': []},
                                                   {'document_id': 5, 'page': 99, 'items': ['10', '11']}]}


def work(page, items, prompt='Question.'):
    return {'type': 'book_work', 'document_id': 5, 'page': page, 'prompt': prompt, 'items': items,
            'response': {'format': 'text'}}


def compile_(*turns, assignment=ASSIGNMENT):
    context = {'visual_source': {'pages': PAGES}, **({'exercise_assignment': assignment} if assignment else {})}
    return page_script.compile_script({'welcome': 'Hi.', 'turns': [{'type': 'read', 'first': 0, 'last': 0}, *turns],
                                       'closing': 'Bye.'}, PASSAGE, context, 'en-US')


def test_a_script_with_exactly_its_items_compiles_with_printed_pages():
    plan = compile_(work(99, ['10.']), work(99, ['11']))
    activities = [s for s in plan['segments'] if s['type'] == 'activity']
    assert [a['content']['printed_page'] for a in activities] == ['96', '96']


@pytest.mark.parametrize('turns, message', [
    ([work(99, ['10'])], 'leaves out its assigned exercise items: 11'),
    ([work(99, ['10', '11']), work(98, ['1'])], 'belongs to another lesson'),
    ([work(99, ['10', '11', '12'])], 'belongs to another lesson'),
    ([work(99, ['10', '11']), work(99, ['10'])], 'more than once'),
    ([work(99, [])], 'must list the printed items'),
])
def test_items_of_other_lessons_or_missing_items_are_rejected(turns, message):
    with pytest.raises(ValueError, match=message):
        compile_(*turns)


def test_pages_that_are_not_shared_keep_every_item_unchecked():
    compile_(work(98, []), work(99, []), assignment=None)


def test_writer_sees_its_items_and_the_narrow_answer_rule():
    text = page_script.prompt(PASSAGE, subject='History', learner='Lucas', grade='4', language='en-US',
                              learner_context={'visual_source': {'pages': PAGES}, 'exercise_assignment': ASSIGNMENT})
    block = text.split('EXERCISES FOR THIS LESSON')[1].split('\n\n')[0]
    assert '"items": ["10", "11"]' in block and '"items": []' in block
    flat = ' '.join(text.split())
    assert 'Teaching the reading fully is not giving answers away' in flat
    assert 'shape what the child hears' not in flat
    assert text.count(lesson_prompt.NON_NEGOTIABLES) == 1
    without = page_script.prompt(PASSAGE, subject='History', learner='Lucas', grade='4', language='en-US',
                                 learner_context={'visual_source': {'pages': PAGES}})
    assert 'EXERCISES FOR THIS LESSON' not in without


def select(harness, topic_id, pages, role='test'):
    with harness.ctx.store.transaction() as tx:
        tx.insert('lesson_page_selections', {'id': str(topic_id), 'topic_id': topic_id, 'sources': [
            {'document_id': 5, 'page_start': p, 'page_end': p, 'role': role, 'document_sha256': 'abc'} for p in pages]})


@pytest.fixture
def chapter(harness):
    with harness.ctx.store.transaction() as tx:
        child = tx.insert('children', {'name': 'Lucas'})
        subject = tx.insert('subjects', {'child_id': child['id'], 'name': 'History'})
        topics = [tx.insert('topics', {'subject_id': subject['id'], 'title': title, 'page_start': start, 'page_end': start + 3})
                  for title, start in (('The Plague', 227), ('A New Way of Living', 231), ('Agincourt', 235))]
    select(harness, topics[0]['id'], [98, 99])
    select(harness, topics[1]['id'], [98, 99, 100])
    select(harness, topics[2]['id'], [102])
    return harness, topics


def test_lessons_sharing_any_exercise_page_form_one_group(chapter):
    h, (plague, living, agincourt) = chapter
    group = ea.group(h.ctx.store, living)
    assert group['topics'] == [plague['id'], living['id']]
    assert group['pages'] == [{'document_id': 5, 'document_sha256': None, 'pages': [98, 99, 100]}]
    assert ea.group(h.ctx.store, plague)['id'] == group['id']
    assert ea.group(h.ctx.store, agincourt) is None  # its own pages: every item is its own


def test_saved_assignment_is_validated_and_split_per_lesson(chapter):
    h, (plague, living, _) = chapter
    group = ea.group(h.ctx.store, living)
    items = [{'label': '9', 'document_id': 5, 'page': 99, 'topic_id': plague['id']},
             {'label': '10', 'document_id': 5, 'page': 99, 'topic_id': living['id']},
             {'label': '19', 'document_id': 5, 'page': 100, 'topic_id': living['id']}]
    for bad in ([*items, {**items[0], 'topic_id': living['id']}],
                [{**items[0], 'page': 101}], [{**items[0], 'topic_id': 999}]):
        with pytest.raises(ValueError), h.ctx.store.transaction() as tx:
            ea.persist(tx, group, bad, 'family')
    with h.ctx.store.transaction() as tx:
        ea.persist(tx, group, items, 'family')
    mine = ea.for_topic(ea.saved(h.ctx.store, group), living['id'])
    assert mine['pages'] == [{'document_id': 5, 'page': 98, 'items': []}, {'document_id': 5, 'page': 99, 'items': ['10']},
                             {'document_id': 5, 'page': 100, 'items': ['19']}]


def test_family_can_view_and_replace_the_assignment(chapter):
    h, (plague, living, _) = chapter
    view = h.call('GET', f"/api/topics/{living['id']}/exercise-assignment").json()
    assert view['shared'] and view['assignment'] is None and [l['title'] for l in view['lessons']] == ['The Plague', 'A New Way of Living']
    items = [{'label': '10', 'document_id': 5, 'page': 99, 'topic_id': living['id']}]
    saved = h.call('PUT', f"/api/topics/{living['id']}/exercise-assignment", json={'items': items, 'expected_revision': 0})
    assert saved.status_code == 200, saved.text
    assert saved.json()['assignment'] == {'items': items, 'method': 'family'}
    stale = h.call('PUT', f"/api/topics/{living['id']}/exercise-assignment", json={'items': items, 'expected_revision': 0})
    assert stale.status_code == 400


def test_labels_compare_as_printed():
    assert ea.label_key(' 10. ') == ea.label_key('10') == ea.label_key('10)')
    assert ea.label_key('B3') != ea.label_key('3')


def test_one_ai_call_per_shared_page_set_sees_every_reading(harness, monkeypatch):
    from tests.pdf_fixture import make_pdf
    from tutoring import passages
    h = harness
    path = h.add_file(make_pdf([['Chapter test', '9. What happened to farms?', '1'],
                                ['10. Why did people move to cities?', '2']]), 'Tests.pdf')
    with h.ctx.store.transaction() as tx:
        child = tx.insert('children', {'name': 'Lucas'})
        subject = tx.insert('subjects', {'child_id': child['id'], 'name': 'History'})
        job = h.ctx.books.begin(tx, subject['id'], path, 'test')
        doc = tx.get('documents', tx.get('subject_books', job['book_id'])['document_id'])
        topics = [tx.insert('topics', {'subject_id': subject['id'], 'title': t, 'page_start': 1, 'page_end': 1})
                  for t in ('The Plague', 'A New Way of Living')]
        for topic in topics:
            tx.insert('lesson_page_selections', {'id': str(topic['id']), 'topic_id': topic['id'], 'sources': [
                {'document_id': doc['id'], 'page_start': 1, 'page_end': 2, 'role': 'test', 'document_sha256': doc['sha256']}]})
    monkeypatch.setattr(passages, 'load', lambda ctx, topic: {'sentences': [{'text': 'Reading of ' + topic['title']}]})
    calls = []
    def generate(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {'items': [{'label': '9', 'document_id': doc['id'], 'page': 1, 'topic_id': topics[0]['id']},
                          {'label': '10', 'document_id': doc['id'], 'page': 2, 'topic_id': topics[1]['id']}]}
    monkeypatch.setattr(h.ctx.ai, 'generate', generate)
    group = ea.group(h.ctx.store, topics[1])
    first = ea.assign(h.ctx, group)
    assert ea.assign(h.ctx, ea.group(h.ctx.store, topics[0]))['id'] == first['id'] and len(calls) == 1
    prompt, kwargs = calls[0]
    assert 'Reading of The Plague' in prompt and 'Reading of A New Way of Living' in prompt
    assert '"printed_page": 2' in prompt and kwargs['schema'] is ea.Assignment and kwargs['pdf']
    assert first['data']['method'] == 'ai'
    assert ea.for_topic(first, topics[1]['id'])['pages'][1] == {'document_id': doc['id'], 'page': 2, 'items': ['10']}
