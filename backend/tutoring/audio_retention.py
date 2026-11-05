"""Keep the family's storage slim: narration for recent lessons only.

A finished lesson keeps its narration while it is one of its subject's
KEEP_FINISHED most recently completed lessons, so a child can go back without
paying again. Older finished lessons lose their audio files (their scripts and
every learner record stay); a lesson can be narrated again later, and the
released purchase records allow that without the duplicate-send guard
refusing it. Lessons not yet completed keep the audio of their newest script
and of any script an open session still uses.

The AI-usage ledger also keeps a raw copy of each purchased recording until it
is saved as a lesson file; once a narration is published, that copy is dropped.
Nothing here depends on a subject or a book.
"""
import json
import logging

logger = logging.getLogger(__name__)
KEEP_FINISHED = 5
OPEN = ('active', 'unfinished')


def _guide_shas_in_use(db, topic):
    """Passage identities whose narration this lesson still needs."""
    rows = sorted((r for r in db.find('guides', topic_id=topic['id']) if r['mode'] != 'practice'),
                  key=lambda r: (r['created_at'], r['id']))
    needed = {rows[-1]['guide_sha256']} if rows else set()
    for session in db.find('tutor_sessions', topic_id=topic['id']):
        if session['status'] in OPEN:
            playback = db.get('lesson_playback', session['id'])
            guide = db.get('guides', playback['guide_id']) if playback else None
            if guide:
                needed.add(guide['guide_sha256'])
    return needed


def plan(db):
    """Audio track ids to remove, per the rules above."""
    remove = []
    tracks = [t for t in db.all('audio_tracks') if not (t.get('note') or '').startswith('feedback:')]
    by_topic = {}
    for track in tracks:
        by_topic.setdefault(track['topic_id'], []).append(track)
    topics = {t['id']: t for t in db.all('topics') if t['id'] in by_topic}
    by_subject = {}
    for topic in topics.values():
        by_subject.setdefault(topic['subject_id'], []).append(topic)
    for subject_topics in by_subject.values():
        finished = sorted((t for t in subject_topics if t.get('completed')),
                          key=lambda t: (str(t.get('completed_at') or ''), t['id']), reverse=True)
        recent = {t['id'] for t in finished[:KEEP_FINISHED]}
        for topic in subject_topics:
            if topic.get('completed') and topic['id'] not in recent and not any(
                    s['status'] in OPEN for s in db.find('tutor_sessions', topic_id=topic['id'])):
                remove += [t['id'] for t in by_topic[topic['id']]]
                continue
            needed = _guide_shas_in_use(db, topic)
            remove += [t['id'] for t in by_topic[topic['id']] if needed and t['passage_sha256'] not in needed]
    return remove


def _track_files(ctx, track):
    files = {track['manifest_path']} if track.get('manifest_path') else set()
    try:
        manifest = json.loads(ctx.file_bytes(track['manifest_path'], None)) if track.get('manifest_path') else {}
    except Exception:  # an unreadable manifest only means nothing more to find
        manifest = {}
    files |= {part['path'] for part in manifest.get('tracks', []) if part.get('path')}
    return files


def prune(ctx):
    """Remove old narration files and their ledger records; returns a summary."""
    db, ledger = ctx.store, ctx.ai.ledger
    doomed = set(plan(db))
    if not doomed:
        return {'tracks': 0, 'files': 0}
    kept = [t for t in db.all('audio_tracks') if t['id'] not in doomed]
    in_use = set().union(*(_track_files(ctx, t) for t in kept)) if kept else set()
    jobs = {j['id']: j for j in ledger.jobs()}
    kept_parts = {rid for t in kept for rid in (jobs.get(t['id']) or {}).get('request_ids', [])}
    files, parts = set(), set()
    for track_id in doomed:
        track = db.get('audio_tracks', track_id)
        files |= _track_files(ctx, track)
        for rid in (jobs.get(track_id) or {}).get('request_ids', []):
            if rid in kept_parts:
                continue
            part = ledger.part(rid)
            if part and part.get('path'):
                files.add(part['path'])
            parts.add(rid)
    files -= in_use
    with db.transaction(kind='audio.retention', summary=f'Removed narration for {len(doomed)} older lesson recordings') as tx:
        for track_id in doomed:
            tx.delete('audio_tracks', track_id)
    ledger.release_parts(sorted(parts), [t for t in doomed if t in jobs])
    removed = 0
    for path in files:
        try:
            db.files.remove(path)
            removed += 1
        except Exception:  # a file already gone or unavailable stays harmless
            logger.warning('Could not remove narration file %s', path)
    return {'tracks': len(doomed), 'files': removed}


def slim_ledger(ctx):
    """Drop raw recording copies once their narration is published as lesson files."""
    ledger = ctx.ai.ledger
    published = [rid for job in ledger.jobs() if job.get('status') == 'ready'
                 for rid in job.get('request_ids', []) if ledger.part(rid)]
    return ledger.drop_results(published)


def run(ctx):
    try:
        summary = prune(ctx)
        summary['ledger_copies'] = slim_ledger(ctx)
        if summary['ledger_copies'] or summary['tracks']:
            ctx.ai.ledger.compact()
        return summary
    except Exception:  # storage housekeeping never blocks the app
        logger.exception('Narration housekeeping failed; nothing was lost')
        return None
