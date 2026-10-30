import hashlib
import io
import json
import wave

import pytest

from tests.test_tutoring import seed_history
from tutoring import audio, guide, imported_audio, narration_alignment


def prepared(harness, monkeypatch):
    seeded = seed_history(harness)
    topic = seeded['genghis']
    sentences = [{'text':'Read the first sentence.'}, {'text':'What changed?'}]
    package = {'guide_id':'synthetic-guide', 'passage_sha256':guide.guide_sha(sentences),
               'sentences':sentences, 'activities':[{'start_sentence':0}, {'start_sentence':1}]}
    text = ' '.join(s['text'] for s in sentences)
    parts = [{'start_sentence':0, 'sentence_count':2,
              'script_sha256':hashlib.sha256(text.encode()).hexdigest()}]
    output = io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'))
        wav.writeframes(b'\0\0'*24000)
    calls = []
    def align(ctx, data, rows, language):
        assert not ctx.store._lock._is_owned()
        calls.append(True)
        return {'sentenceStarts':[0.,.5], 'duration':1.,
                'alignment':{'version':narration_alignment.VERSION}}
    monkeypatch.setattr(narration_alignment,'align',align)
    return topic, package, parts, [output.getvalue()], calls


def test_import_keeps_engine_clips_and_reuses_without_provider_or_learner_changes(harness,monkeypatch):
    topic,package,parts,recordings,calls = prepared(harness,monkeypatch)
    before={t:harness.ctx.store.all(t) for t in ['attempts','tutor_sessions','lesson_playback']}
    settings=dict(harness.config.values)
    result=imported_audio.install(harness.ctx,topic,package,parts,recordings,voice='Clive',language='en-US')
    again=imported_audio.install(harness.ctx,topic,package,parts,recordings,voice='Clive',language='en-US')
    assert result['track_id']==again['track_id'] and again['reused'] and len(calls)==1
    row=harness.ctx.store.get('audio_tracks',result['track_id'])
    manifest=json.loads(harness.ctx.file_bytes(row['manifest_path']))
    assert manifest['provider']=='inworld' and manifest['cost_usd'] is None
    assert [t['startSentence'] for t in manifest['tracks']]==[0,1]
    assert audio.validate_manifest(manifest,package['passage_sha256'],2)[0]
    assert row['note']==imported_audio.PREFERRED
    tracks=harness.ctx.tutor.audio_tracks(topic,package,only=package['passage_sha256'])
    assert tracks[0]['preferred'] and tracks[0]['synchronized']
    assert not harness.ctx.ai.ledger.requests()
    assert settings==harness.config.values
    assert before=={t:harness.ctx.store.all(t) for t in before}


def test_native_portuguese_male_narrator_keeps_locale_validation(harness,monkeypatch):
    topic,package,parts,recordings,calls=prepared(harness,monkeypatch)
    with pytest.raises(ValueError):imported_audio.install(harness.ctx,topic,package,parts,recordings,voice='Heitor',language='en-US')
    assert not calls
    result=imported_audio.install(harness.ctx,topic,package,parts,recordings,voice='Heitor',language='pt-BR')
    row=harness.ctx.store.get('audio_tracks',result['track_id'])
    manifest=json.loads(harness.ctx.file_bytes(row['manifest_path']))
    assert manifest['voice']=='Heitor' and manifest['language']=='pt-BR'


@pytest.mark.parametrize('problem',['hash','gap','missing','format','voice','rate'])
def test_bad_or_incomplete_import_is_rejected_before_publication(harness,monkeypatch,problem):
    topic,package,parts,recordings,calls=prepared(harness,monkeypatch)
    voice,rate='Clive',.9
    if problem=='hash':parts[0]['script_sha256']='0'*64
    if problem=='gap':parts[0]['start_sentence']=1
    if problem=='missing':
        parts[0]['sentence_count']=1
        parts[0]['script_sha256']=hashlib.sha256(package['sentences'][0]['text'].encode()).hexdigest()
    if problem=='format':recordings=[b'not audio']
    if problem=='voice':voice='Maitê'
    if problem=='rate':rate=float('nan')
    with pytest.raises(ValueError):
        imported_audio.install(harness.ctx,topic,package,parts,recordings,voice=voice,language='en-US',rate=rate)
    assert not calls and not harness.ctx.store.all('audio_tracks')


def test_acoustic_mismatch_keeps_raw_audio_but_never_publishes_a_ready_track(harness,monkeypatch):
    topic,package,parts,recordings,calls=prepared(harness,monkeypatch)
    def fail(*args):raise narration_alignment.AlignmentError('Synthetic missing speech')
    monkeypatch.setattr(narration_alignment,'align',fail)
    with pytest.raises(ValueError,match='missing speech'):
        imported_audio.install(harness.ctx,topic,package,parts,recordings,voice='Clive',language='en-US')
    assert not harness.ctx.store.all('audio_tracks')
    assert harness.ctx.ai.ledger.jobs()[0]['status']=='paused'


def test_import_api_checks_session_ownership_and_tutor_permissions(harness):
    seeded=seed_history(harness)
    data={'learner':seeded['lucas']['id'],'topic':seeded['genghis']['id'],
          'guide_id':'not-owned','passage_sha256':'0'*64,'session':'not-owned','voice':'Clive','parts':'[]'}
    files={'recordings':('synthetic.wav',b'not audio','audio/wav')}
    assert harness.call('POST','/api/tutor/reader/narration/import',data=data,files=files).status_code==400
    assert harness.call('POST','/api/tutor/reader/narration/import',role='tutor',data=data,files=files).status_code==403


def test_preparation_import_needs_no_student_session_but_requires_current_guide(harness, monkeypatch):
    from tests.test_interactive import prepare
    h = harness
    seeded, package = prepare(h, monkeypatch)
    data = {'learner': seeded['lucas']['id'], 'topic': seeded['genghis']['id'],
        'guide_id': package['guide_id'], 'passage_sha256': package['passage_sha256'],
        'voice': 'Clive', 'parts': '[]'}
    files = {'recordings': ('synthetic.wav', b'synthetic recording', 'audio/wav')}
    calls = []
    def install(ctx, topic, selected, parts, recordings, **options):
        calls.append(selected['guide_id'])
        return {'track_id': 'synthetic-prepared-audio', 'job_status': 'ready'}
    monkeypatch.setattr(imported_audio, 'install', install)
    before = {t: h.ctx.store.all(t) for t in ('tutor_sessions','lesson_playback','attempts')}
    route = '/api/tutor/reader/narration/import'
    assert h.call('POST', route, data=data, files=files).status_code == 200
    assert calls == [package['guide_id']]
    assert before == {t: h.ctx.store.all(t) for t in before}
    for extra, status in (({'guide_id':'unrelated-guide'},409),
                          ({'passage_sha256':'0'*64},409), ({'session':'not-owned'},400)):
        assert h.call('POST', route, data={**data, **extra}, files=files).status_code == status
    assert calls == [package['guide_id']]
