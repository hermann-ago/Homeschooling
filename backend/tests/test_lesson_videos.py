"""A book's video lessons: found on the publisher's pages, shown as a lesson step."""
import pytest

from tutoring import videos
from tutoring.activity_engine import VIDEO_STEP, service
from tests.test_activity_engine import event
from tests.test_interactive import prepare, start

PAGE = '''<summary>Lesson 1 | Welcome</summary><iframe src="https://player.vimeo.com/video/111111?h=aa11bb22&amp;app_id=1"></iframe>
<summary>Lesson 2 | Review Games (No Video)</summary>
<summary>Lesson 3 | Fractions</summary><iframe src="https://player.vimeo.com/video/333333?h=cc33dd44"></iframe>
<iframe src="https://www.youtube.com/embed/abcdefghijk"></iframe>'''
TITLES = {'111111': 'Lesson 1 | Simply Math', '333333': 'Lesson 13 | Simply Math', 'abcdefghijk': 'A song about numbers'}


class Reply:
    def __init__(self, status=200, text='', data=None):
        self.status_code, self.text, self._data = status, text, data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeWeb:
    def get(self, url, params=None, **kwargs):
        if 'oembed' in url:
            target = params['url']
            key = next(k for k in TITLES if k in target)
            return Reply(data={'title': TITLES[key]})
        return Reply(text=PAGE)


@pytest.fixture
def public_pages(monkeypatch):
    monkeypatch.setattr(videos, '_public_https', lambda url: None)


def topics(db, subject_id, *titles):
    with db.transaction() as tx:
        return [tx.insert('topics', {'subject_id': subject_id, 'title': t, 'page_start': 1, 'page_end': 2})['id'] for t in titles]


def test_links_become_players_that_keep_their_private_key():
    video = videos.parse('https://player.vimeo.com/video/579391169?h=681f47c29c')
    assert video == {'provider': 'vimeo', 'video_id': '579391169', 'key': '681f47c29c'}
    assert videos.player(video)['embed_url'].startswith('https://player.vimeo.com/video/579391169?h=681f47c29c&dnt=1')
    assert videos.player(video)['open_url'] == 'https://vimeo.com/579391169/681f47c29c'
    assert videos.parse('https://youtu.be/abcdefghijk')['video_id'] == 'abcdefghijk'
    assert videos.parse('https://example.com/lesson') is None


def test_found_videos_match_lessons_by_their_number_and_keep_a_grown_ups_choice(harness, public_pages):
    db = harness.ctx.store
    with db.transaction() as tx:
        child = tx.insert('children', {'name': 'Test'})['id']
        subject = tx.insert('subjects', {'child_id': child, 'name': 'Math'})['id']
    first, thirteen, three = topics(db, subject, 'Lesson 1: Welcome', 'Lesson 13: Fractions', 'Lesson 3: Shapes')
    videos.set_for_topic(db, three, hidden=True, http=FakeWeb())
    found = videos.find(db, subject, ['https://books.example/unit-1'], http=FakeWeb())
    assert found['videos'] == 3 and found['matched'] == 2
    assert found['unmatched'] == ['A song about numbers']
    assert videos.for_topic(db, first)['open_url'] == 'https://vimeo.com/111111/aa11bb22'
    assert videos.for_topic(db, thirteen)['title'] == 'Lesson 13 | Simply Math'
    assert videos.for_topic(db, three) is None  # hidden by a grown-up stays hidden
    assert db.get('subjects', subject)['video_pages'] == ['https://books.example/unit-1']


def test_video_pages_must_be_public_https():
    with pytest.raises(Exception, match='https'):
        videos._public_https('http://books.example/unit-1')
    with pytest.raises(Exception, match='public web'):
        videos._public_https('https://127.0.0.1/videos')


def test_a_lesson_with_a_video_shows_it_after_the_welcome_and_records_watching(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    videos.set_for_topic(harness.ctx.store, seeded['genghis']['id'], 'https://vimeo.com/579391169/681f47c29c', http=FakeWebNoTitle())
    legacy = start(harness, seeded, guide)
    engine = service(harness.ctx)
    state = engine.state(legacy['session_id'])
    order = [a['id'] for a in state['activities'] if a['kind'] != 'close_lesson'][:3]
    assert order[1] == VIDEO_STEP and state['active_activity']['kind'] == 'introduce'
    state = event(engine, state, 'continue')
    active = state['active_activity']
    assert active['id'] == VIDEO_STEP and active['content']['video']['embed_url'].startswith('https://player.vimeo.com/video/579391169')
    state = event(engine, state, 'video_watched')
    state = event(engine, state, 'continue')
    assert state['active_activity']['kind'] == 'read_source' and state['active_activity']['review_after_video']
    state = event(engine, state, 'reading_done')
    for _ in range(10):
        if state['active_activity']['kind'] == 'close_lesson':
            break
        pending_question = state['active_activity']['kind'] == 'ask_question' and state['active_activity']['status'] == 'pending'
        state = event(engine, state, 'skip' if pending_question else 'continue')
    state = event(engine, state, 'finish')
    summary = harness.ctx.store.get('tutor_sessions', state['session_id'])['completion_summary']
    assert summary['video'] == {'watched': True}


def test_a_lesson_without_a_video_has_no_video_step(harness, monkeypatch):
    seeded, guide = prepare(harness, monkeypatch)
    legacy = start(harness, seeded, guide)
    state = service(harness.ctx).state(legacy['session_id'])
    assert all(a['id'] != VIDEO_STEP for a in state['activities'])
    assert 'video' not in str(state['active_activity']['content'])


class FakeWebNoTitle:
    def get(self, url, params=None, **kwargs):
        return Reply(status=404)


def test_the_writer_hears_about_a_video_only_when_the_lesson_has_one(harness):
    db = harness.ctx.store
    with db.transaction() as tx:
        child = tx.insert('children', {'name': 'Test'})['id']
        subject = tx.insert('subjects', {'child_id': child, 'name': 'Math'})['id']
    with_video, without = topics(db, subject, 'Lesson 18: Elapsed Time', 'Lesson 19: Rounding')
    videos.set_for_topic(db, with_video, 'https://vimeo.com/579391393', http=FakeWebNoTitle())
    assert videos.context_for(db, with_video) == {'lesson_video': {'title': None}}
    assert videos.context_for(db, without) == {}
    from tutoring.lesson_prompt import writer_prompt
    passage = {'title': 'Lesson 18', 'sentences': []}
    told = writer_prompt(passage, subject='Math', learner='Lucas', grade='4', language='en-US', learner_context=videos.context_for(db, with_video))
    plain = writer_prompt(passage, subject='Math', learner='Lucas', grade='4', language='en-US', learner_context={})
    assert 'VIDEO LESSON' in told and 'VIDEO LESSON' not in plain
