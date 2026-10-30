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
