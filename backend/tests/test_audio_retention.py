"""Narration is kept for recent lessons only; scripts and learner records stay."""
import datetime
import json

from tutoring import audio_retention


def add_topic(tx, subject, n, completed=None):
    return tx.insert('topics', {'subject_id': subject['id'], 'title': f'Lesson {n}', 'page_start': n, 'page_end': n,
                                'completed': completed is not None, 'completed_at': completed})


def add_track(h, tx, topic, sha, name):
    from storage import layout
    folder = layout.for_topic(tx, topic['id'], layout.AUDIO)
    part = tx.add_blob(b'RIFF' + name.encode(), folder, f'{name}-part.wav', 'audio/wav')[0]
    manifest = tx.add_blob(json.dumps({'tracks': [{'path': part}]}).encode(), folder, f'{name}-manifest.json', 'application/json')[0]
    row = tx.insert('audio_tracks', {'id': name, 'topic_id': topic['id'], 'passage_sha256': sha, 'provider': 'inworld',
                                     'voice': 'Brian', 'speaking_rate': 0.9, 'manifest_path': manifest, 'status': 'ready'})
    return row, part, manifest


def add_guide(tx, topic, sha, minutes=0):
    return tx.insert('guides', {'id': f'guide-{topic["id"]}-{sha}', 'topic_id': topic['id'], 'source_sha256': 's', 'guide_sha256': sha,
                                'guide_path': 'g.json', 'mode': 'tidy', 'model': 'm', 'language': 'en-US',
                                'created_at': datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(minutes=minutes)})


def test_only_the_five_most_recent_finished_lessons_keep_their_narration(harness):
    h = harness
    with h.ctx.store.transaction() as tx:
        child = tx.insert('children', {'name': 'Lucas'})
        subject = tx.insert('subjects', {'child_id': child['id'], 'name': 'History'})
        finished = [add_topic(tx, subject, n, f'2026-10-{n + 1:02d}T10:00:00Z') for n in range(7)]
        upcoming = add_topic(tx, subject, 9)
        files = {}
        for topic in finished:
            add_guide(tx, topic, f'sha{topic["id"]}')
            _, part, manifest = add_track(h, tx, topic, f'sha{topic["id"]}', f'track-{topic["id"]}')
            files[topic['id']] = (part, manifest)
        add_guide(tx, upcoming, 'old', 0)
        add_guide(tx, upcoming, 'new', 5)
        add_track(h, tx, upcoming, 'old', 'upcoming-old')
        add_track(h, tx, upcoming, 'new', 'upcoming-new')
    h.ctx.ai.ledger.save_job('track-' + str(finished[0]['id']), {'topic_id': finished[0]['id'], 'status': 'ready', 'request_ids': ['voice:rid-old']})
    h.ctx.ai.ledger.save_part('voice:rid-old', {'path': files[finished[0]['id']][0], 'sha256': 'x'})

    removed = set(audio_retention.plan(h.ctx.store))
    oldest = {f'track-{t["id"]}' for t in finished[:2]}
    assert removed == oldest | {'upcoming-old'}
    summary = audio_retention.prune(h.ctx)
    assert summary['tracks'] == 3
    remaining = {t['id'] for t in h.ctx.store.all('audio_tracks')}
    assert remaining == {f'track-{t["id"]}' for t in finished[2:]} | {'upcoming-new'}
    for topic in finished[:2]:
        assert not any(h.ctx.store.files.resolve(p).exists() for p in files[topic['id']])
    assert all(h.ctx.store.files.resolve(p).exists() for p in files[finished[-1]['id']])
    # Scripts stay; the released purchase can be bought again later.
    assert len(h.ctx.store.all('guides')) == 9
    assert h.ctx.ai.ledger.part('voice:rid-old') is None and h.ctx.ai.ledger.request_state('voice:rid-old') is None


def test_published_recordings_drop_their_raw_ledger_copy(harness):
    ledger = harness.ctx.ai.ledger
    ledger.save_result('voice:published', '{"audio": "x"}')
    ledger.save_part('voice:published', {'path': 'Audio/p.wav'})
    ledger.save_result('voice:in-progress', '{"audio": "y"}')
    ledger.save_job('job-ready', {'status': 'ready', 'request_ids': ['voice:published']})
    ledger.save_job('job-running', {'status': 'running', 'request_ids': ['voice:in-progress']})
    assert audio_retention.slim_ledger(harness.ctx) == 1
    assert ledger.result('voice:published') is None and ledger.result('voice:in-progress') is not None
