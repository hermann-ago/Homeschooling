import copy
import pytest
from tests.test_interactive import prepare,start
from tests.test_ai_costs import enable_voice,audio_response
from tutoring import narration_alignment


def test_feedback_follows_selected_recording_without_alignment_or_progress_changes(harness,monkeypatch):
    h=harness;seed,guide=prepare(h,monkeypatch);state=start(h,seed,guide)
    with h.ctx.store.transaction() as tx:
        tx.insert('lesson_dialogue',{'id':'teacher-reply','session_id':state['session_id'],'action_id':'action-1',
            'role':'teacher','text':'You explained the main idea clearly.','status':'saved'})
        tx.insert('audio_tracks',{'id':'lesson-google','topic_id':seed['genghis']['id'],'passage_sha256':guide['passage_sha256'],
            'provider':'google-gemini','voice':'Achird','speaking_rate':.9,'manifest_path':'not-needed-for-selection.json','status':'ready'})
    calls=[]
    enable_voice(h,lambda request:(calls.append(request) or audio_response()))
    h.config.update(tts={**h.config.get('tts'),'provider':'elevenlabs','aligned_blocks':True})
    monkeypatch.setattr(narration_alignment,'align',lambda *a,**kw:pytest.fail('Short feedback must not run lesson alignment'))
    before={t:copy.deepcopy(h.ctx.store.all(t)) for t in ('attempts','tutor_sessions','activity_responses','lesson_playback')}
    url=f"/api/tutor/sessions/{state['session_id']}/feedback-audio"
    assert h.call('POST',url,json={'message_id':'teacher-reply','track_id':'other-lesson'}).status_code==400
    body={'message_id':'teacher-reply','track_id':'lesson-google','dry_run':False}
    first=h.call('POST',url,json=body)
    assert first.status_code==200,first.text
    assert first.json()['provider']=='google-gemini' and len(calls)==1
    again=h.call('POST',url,json=body)
    assert again.json()['reused'] and len(calls)==1
    assert before=={t:h.ctx.store.all(t) for t in before}
    assert h.config.get('tts')['provider']=='elevenlabs'


def test_once_a_reply_plays_by_itself_the_next_ones_are_voiced_as_they_are_written(harness,monkeypatch):
    from tutoring import reply_voice
    monkeypatch.setattr(reply_voice,'_choices',{})  # lesson ids repeat between tests
    monkeypatch.setattr(reply_voice,'_started',set())
    h=harness;seed,guide=prepare(h,monkeypatch);state=start(h,seed,guide)
    with h.ctx.store.transaction() as tx:
        for rid,text in (('first-reply','You explained the main idea clearly.'),('second-reply','Look again at the second part.')):
            tx.insert('lesson_dialogue',{'id':rid,'session_id':state['session_id'],'action_id':'action-1',
                'role':'teacher','text':text,'status':'saved'})
        tx.insert('audio_tracks',{'id':'lesson-google','topic_id':seed['genghis']['id'],'passage_sha256':guide['passage_sha256'],
            'provider':'google-gemini','voice':'Achird','speaking_rate':.9,'manifest_path':'not-needed-for-selection.json','status':'ready'})
    calls=[]
    enable_voice(h,lambda request:(calls.append(request) or audio_response()))
    url=f"/api/tutor/sessions/{state['session_id']}/feedback-audio"
    # A reply the child tapped to hear does not voice later ones ahead.
    assert h.call('POST',url,json={'message_id':'first-reply','track_id':'lesson-google','dry_run':False}).status_code==200
    assert reply_voice.start(state['session_id'],'second-reply') is None
    assert h.call('POST',url,json={'message_id':'first-reply','track_id':'lesson-google','dry_run':False,'autoplay':True}).status_code==200
    assert len(calls)==1
    reply_voice.start(state['session_id'],'second-reply').join(10)
    assert len(calls)==2 and reply_voice.start(state['session_id'],'second-reply') is None
    # The screen's own request finds the recording ready and buys nothing.
    again=h.call('POST',url,json={'message_id':'second-reply','track_id':'lesson-google','dry_run':False,'autoplay':True})
    assert again.json()['reused'] and len(calls)==2


def test_a_graded_answer_starts_its_reply_voice(harness,monkeypatch):
    from tutoring import reply_voice
    from tests.test_closing_note import finished_lesson
    started=[]
    monkeypatch.setattr(reply_voice,'start',lambda session_id,message_id:started.append(message_id))
    finished_lesson(harness,monkeypatch,voice_on=False)
    assert started and all(m.endswith(':reply') for m in started)
