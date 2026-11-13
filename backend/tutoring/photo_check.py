"""Book work answered with a photo and checked in the background.

The child photographs the exercise and the lesson moves on at once
("checking"). One AI request reads the photo and assesses each exercise in it.
Results become ordinary responses, dialogue and attempts: a right answer is
"answered"; anything else is "fix", open to fix from the lesson's tracker and
never owed in a later lesson. An unsure reading is "couldn't read", not wrong.
"""
import hashlib
import json
import threading
from contextlib import nullcontext
from typing import Literal

from pydantic import BaseModel, Field

from .service import TutorConflict, TutorError

EVENTS = {'snap_work', 'retry_photo_check', 'fix_work', 'fix_later'}
RUNS_AFTER = {'snap_work', 'retry_photo_check'}
MAX_PHOTOS = 3
MAX_BYTES = 12 * 1024 * 1024
WORKING = ('queued', 'checking')
_running, _lock = set(), threading.Lock()


class CheckedWork(BaseModel):
    item_id: str
    answer: str = Field('', max_length=4000)
    uncertain: bool = False
    result: Literal['Correct', 'Partly correct', 'Not yet', 'Unanswered', 'Unreadable']
    feedback: str = Field(min_length=1, max_length=1200)


class PhotoCheckReply(BaseModel):
    items: list[CheckedWork] = Field(max_length=40)


def snappable(action):
    """A book exercise the child does on paper: its answer can arrive as a photo."""
    from .activity_engine import RESPONSE_KINDS
    return bool(action.get('origin') == 'required_book' and action.get('activity_kind') in RESPONSE_KINDS
                and not action.get('parent_activity_id') and action['status'] == 'pending')


def fixing(action):
    return bool((action.get('return_cursor') or {}).get('fix'))


def _jobs(db, session_id):
    # Saved times have one-second resolution: the photo's own number orders two quick photos.
    return sorted((j for j in db.find('activity_jobs', session_id=session_id) if j['kind'] == 'photo_check'),
                  key=lambda j: (j['input_snapshot'].get('order', 0), j['created_at'], j['id']))


def _latest(jobs, action_id):
    return next((j for j in reversed(jobs) if action_id in j['input_snapshot']['items']), None)


def overview(db, session_id):
    """Per exercise: where its latest photo check stands, for the tracker."""
    jobs = _jobs(db, session_id)
    seen = {}
    for job in jobs:
        results = {r['item_id']: r for r in (job.get('result') or {}).get('items', [])}
        for item in job['input_snapshot']['items']:
            checked = results.get(item)
            seen[item] = {'job_id': job['id'], 'status': job['status'], 'error': job.get('error'),
                **({'read': checked['answer'], 'result': checked['result'], 'feedback': checked['feedback']} if checked else {})}
    return seen


def running(db, session_id):
    return any(j['status'] in WORKING for j in _jobs(db, session_id))


def summary(db, session_id, actions):
    return {'to_practise': [a['action_id'] for a in actions if a['status'] == 'fix'],
            'unchecked': [a['action_id'] for a in actions if a['status'] == 'checking']}


def _key(engine, tx, action):
    from .page_script import answer_for
    from .source_key import resolve as source_key
    if action.get('assignment_item_id'):
        return (tx.get('assignment_items', action['assignment_item_id']) or {}).get('snapshot')
    try:
        return answer_for(engine.ctx, action) or source_key(tx, action)
    except Exception:  # A missing key never blocks the check; the task is judged on its own.
        return None


def _task(engine, tx, action):
    from .capture_policy import activity_content
    from .source_key import original_refs
    content = activity_content(engine.ctx, action)
    from .tutor_voice import earlier_lines
    # Fixing a photo answer reopens the step, and those earlier tries are exactly what counts here;
    # only "Start lesson over" begins the count again.
    playback = tx.get('lesson_playback', action['session_id']) or {}
    started = ((playback.get('navigation_state') or {}).get('fresh_start') or {}).get('dialogue') or 0
    said, attempt = earlier_lines(tx, action['session_id'], action['action_id'], after_sequence=started)
    return {'item_id': action['action_id'], 'prompt': action.get('next_prompt') or action['prompt'],
        # How many times the child has already tried this task, and what they were told: a repeated
        # miss needs a different kind of help, not the same sentence again.
        'try_number': attempt, 'earlier_replies': said[-3:] if attempt > 1 else [],
        'original_question': original_refs(action),
        'pages': sorted({r['page'] for r in action.get('source_refs') or [] if r.get('page')}),
        'answer_format': content.get('answer_format', 'text'), 'evidence': content.get('evidence_requirement', 'answer'),
        'choices': [c.get('label') for c in content.get('choices') or []],
        'blanks': [b.get('label') for b in content.get('blanks') or []],
        'teacher_key': _key(engine, tx, action)}


TASKS = 'Tasks (teacher_key is private):\n'


def _prompt(engine, job):
    """The lesson's ordinary grading context (family style, subject notes, source, assessment
    policy), then what is particular to a photo: copy first, never guess, one entry per task."""
    snapshot = job['input_snapshot']
    session = engine._session(job['session_id'])
    action = engine._action(engine.db, session['id'], snapshot['items'][0])
    context, _, _ = engine.tutor.interactive._prompt(session, action,
        {'id': 'photo-' + job['id'], 'text': '', 'evidence_ids': snapshot['evidence_ids']})
    return (context + '\nThe child did this book work on paper and photographed it. Assess each task below separately. '
        'For each task: answer = the child\'s visible answer copied exactly as written, mistakes included (empty when '
        'none is visible); uncertain = true when you cannot read it with confidence. result: Correct; Partly correct; '
        'Not yet; Unanswered (nothing written for this task); Unreadable (cannot read it). feedback: one or two warm '
        'sentences to the child; when it is not Correct, help without giving the answer, by its try_number: '
        'first try, say what to look at again; second, give a more concrete clue; third or later, change approach '
        'and walk into the first small step with the child (for example ask what one digit or word is). Never repeat '
        'the wording of earlier_replies. '
        'Keep feedback brief and do not request new activities. Return every item_id exactly once. '
        + TASKS + json.dumps(snapshot['tasks'], ensure_ascii=False, default=str))


def apply(engine, tx, session, action, interaction, event, payload, operation_id):
    from .activity_engine import _paced
    playback = tx.get('lesson_playback', session['id'])
    if event == 'snap_work':
        if _paced(playback) or not snappable(action):
            raise TutorError('This step does not take a photo of book work')
        if interaction['status'] not in ('awaiting_work', 'awaiting_input', 'awaiting_followup'):
            raise TutorConflict('Finish the answer already being checked first')
        ids = payload.get('evidence_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_PHOTOS or len(set(ids)) != len(ids):
            raise TutorError(f'Attach between one and {MAX_PHOTOS} photos of this work')
        images = []
        for eid in ids:
            e = tx.get('evidence_files', eid)
            if not e or (e['session_id'], e['child_id'], e['action_id']) != (session['id'], session['child_id'], action['action_id']):
                raise TutorError('Use photos taken for this exercise')
            if e['mime_type'] not in ('image/jpeg', 'image/png', 'image/webp'):
                raise TutorError('Use JPEG, PNG or WebP photos')
            images.append({k: e[k] for k in ('file_path', 'sha256', 'mime_type', 'size_bytes')})
        if sum(i['size_bytes'] or 0 for i in images) > MAX_BYTES:
            raise TutorError('Use smaller photos, up to 12 MB together')
        group = engine._section_group(tx, session, action)
        tasks = [_task(engine, tx, a) for a in group]
        with engine.ctx.ai.reading_handwriting():
            provider, model = engine.ctx.ai.selection()
        identity = 'photo-check-' + hashlib.sha256(json.dumps([session['id'], operation_id]).encode()).hexdigest()[:32]
        interactions = {}
        for item in group:
            current = engine._interaction(tx, session['id'], item['action_id']) or engine._new_interaction(tx, session, item)
            interactions[item['action_id']] = current['id']
            tx.update('activity_interactions', current['id'], {'status': 'completed'})
            tx.update('lesson_actions', item['id'], {'status': 'checking'})
        tx.insert('activity_jobs', {'id': identity, 'session_id': session['id'], 'child_id': session['child_id'],
            'activity_id': action['action_id'], 'interaction_id': interaction['id'], 'kind': 'photo_check', 'status': 'queued',
            'input_snapshot': json.loads(json.dumps({'order': len(_jobs(tx, session['id'])) + 1,
                'items': [a['action_id'] for a in group], 'interactions': interactions,
                'evidence_ids': ids, 'images': images, 'tasks': tasks, 'provider': provider, 'model': model}, default=str))})
        engine._continue(tx, session, engine._action(tx, session['id'], action['action_id']),
                         tx.get('activity_interactions', interaction['id']))
        return
    if event == 'fix_later':
        back = action.get('return_cursor') or {}
        if not back.get('fix'):
            raise TutorConflict('This step is not an answer being fixed')
        tx.update('lesson_actions', action['id'], {'status': back.get('was') or 'fix'})
        tx.update('activity_interactions', interaction['id'], {'status': 'completed'})
        engine._continue(tx, session, engine._action(tx, session['id'], action['action_id']),
                         tx.get('activity_interactions', interaction['id']))
        return
    target = engine._action(tx, session['id'], payload.get('activity_id'))
    latest = _latest(_jobs(tx, session['id']), target['action_id'])
    if event == 'retry_photo_check':
        if target['status'] != 'checking' or not latest or latest['status'] != 'failed':
            raise TutorConflict('There is no failed photo check to try again')
        tx.update('activity_jobs', latest['id'], {'status': 'queued', 'error': None})
        return
    # fix_work: open a checked exercise again, then return to this place.
    if fixing(action):
        raise TutorConflict('Finish the answer you are fixing first')
    if target['id'] == action['id'] or not (target['status'] == 'fix' or target['status'] == 'checking'
                                            and latest and latest['status'] == 'failed'):
        raise TutorConflict('Choose a checked exercise that needs another look')
    was = target['status']
    engine._restart_activity(tx, session, target)
    tx.update('lesson_actions', target['id'], {'return_cursor': {'action_id': action['action_id'],
        'sentence_index': playback['sentence_index'], 'resume_index': playback['resume_index'],
        'narration_cursor': playback.get('narration_cursor'), 'fix': True, 'was': was}})
    tx.update('lesson_playback', session['id'], {'action_id': target['action_id'], 'narration_cursor': None})


def start(engine, session_id):
    """Run waiting checks: on a thread while a lesson is live, inline when asked (tests, replays)."""
    for job in _jobs(engine.db, session_id):
        if job['status'] not in WORKING:
            continue
        if not getattr(engine, 'background_checks', True):
            run(engine, job['id'])
            continue
        with _lock:
            if job['id'] in _running:
                continue
            _running.add(job['id'])
        threading.Thread(target=_threaded, args=(engine, job['id']), name='photo-check-' + job['id'][-8:], daemon=True).start()


def _threaded(engine, job_id):
    try:
        run(engine, job_id)
    finally:
        with _lock:
            _running.discard(job_id)


def run(engine, job_id):
    """Provider work stays outside transactions and the lesson lock; a retry reuses the request identity."""
    from .interactive import SERVER_TUTOR_RULES
    from .page_work import exact_schema
    job = engine.db.get('activity_jobs', job_id)
    if not job or job['kind'] != 'photo_check' or job['status'] not in WORKING:
        return
    snapshot, session_id = job['input_snapshot'], job['session_id']
    try:
        if not snapshot.get('prompt'):  # Frozen once, so a retry sends the identical request.
            snapshot = {**snapshot, 'prompt': _prompt(engine, job)}
        with engine.db.transaction(kind='activity.photo_check_claim') as tx:
            tx.update('activity_jobs', job_id, {'status': 'checking', 'input_snapshot': snapshot})
        job = {**job, 'input_snapshot': snapshot}
        images = [(engine.ctx.file_bytes(i['file_path'], i['sha256']), i['mime_type']) for i in snapshot['images']]
        playback = engine.db.get('lesson_playback', session_id)
        scope = engine.ctx.ai.scoped(playback['generation_scope_id']) if playback.get('generation_scope_id') else nullcontext()
        with scope, engine.ctx.ai.identified(job_id), engine.ctx.ai.reading_handwriting():
            if tuple(engine.ctx.ai.selection()) != (snapshot['provider'], snapshot['model']):
                raise TutorConflict('The photo reader changed; take the photo again')
            reply = engine.ctx.ai.generate(snapshot['prompt'], images=images,
                schema=exact_schema(PhotoCheckReply, snapshot['items']), instructions=SERVER_TUTOR_RULES, max_output=12000)
        with engine.lock(session_id):
            with engine.db.transaction(kind='activity.photo_check_result') as tx:
                _save(engine, tx, job, [_settle(snapshot, item) for item in reply['items']])
    except Exception:
        with engine.db.transaction(kind='activity.photo_check_failed') as tx:
            tx.update('activity_jobs', job_id, {'status': 'failed',
                'error': 'The photo is saved but could not be checked yet. Nothing was marked wrong.'})
            tx.touch('tutor_sessions', session_id)


def _settle(snapshot, item):
    """An unsure reading is never a wrong answer; a reviewed true/false key decides a clear one."""
    from .keyed_assessment import checked_binary_assessment
    item = dict(item)
    if item['uncertain'] and item['result'] in ('Partly correct', 'Not yet'):
        item['result'] = 'Unreadable'
    key = next((t.get('teacher_key') for t in snapshot['tasks'] if t['item_id'] == item['item_id']), None)
    verdict = checked_binary_assessment(key, item['answer']) if isinstance(key, dict) and item['answer'] and not item['uncertain'] else None
    if verdict and verdict['result'] != item['result']:
        item.update(result=verdict['result'], feedback=verdict['feedback'])
    return item


def _save(engine, tx, job, items):
    from .activity_engine import _hash
    from .service import OPEN_SESSION
    snapshot, session_id = job['input_snapshot'], job['session_id']
    session = tx.get('tutor_sessions', session_id)
    jobs = _jobs(tx, session_id)
    for item in items:
        action = engine._action(tx, session_id, item['item_id'])
        # A later photo, a restart or a finished lesson supersedes this result: it stays on the job only.
        if session['status'] not in OPEN_SESSION or action['status'] != 'checking' or _latest(jobs, action['action_id'])['id'] != job['id']:
            continue
        rid = 'photo-answer-' + _hash([job['id'], item['item_id']])[:32]
        message_id = 'response-' + _hash([session_id, rid])[:32]
        sequence = max((m['sequence'] or 0 for m in tx.find('lesson_dialogue', session_id=session_id)), default=0)
        tx.insert('activity_responses', {'id': rid, 'session_id': session_id, 'child_id': action['child_id'],
            'activity_id': action['action_id'], 'interaction_id': snapshot['interactions'][item['item_id']], 'method': 'photo',
            'original': {'text': '', 'reasoning': '', 'choice_ids': [], 'evidence_ids': snapshot['evidence_ids'], 'photo_check_id': job['id']},
            'support_snapshot': {'this': action.get('help_given'), 'other': [], 'dialogue_sequence': sequence},
            'proposed_text': item['answer'], 'confirmed_text': item['answer'], 'evidence_ids': snapshot['evidence_ids'],
            'reasoning': '', 'status': 'assessed', 'transcription_status': 'confirmed', 'message_id': message_id})
        message = tx.insert('lesson_dialogue', {'id': message_id, 'session_id': session_id, 'action_id': action['action_id'],
            'role': 'student', 'text': item['answer'], 'evidence_ids': snapshot['evidence_ids'], 'status': 'pending',
            'input_revision': session['revision'], 'sequence': sequence + 1})
        right = item['result'] == 'Correct'
        engine.tutor.interactive._apply(tx, session, action, message, {'feedback': item['feedback'], 'result': item['result'],
            'transcription': item['answer'], 'help': None, 'assistance_used': False, 'follow_up': None,
            'ready_to_continue': right, 'concept': None, 'activity_requests': []}, session['revision'])
        tx.update('lesson_actions', action['id'], {'status': 'answered' if right else 'fix', 'next_prompt': action['prompt']})
        if action.get('assignment_item_id') and item['result'] in ('Correct', 'Partly correct', 'Not yet'):
            tx.update('assignment_items', action['assignment_item_id'], {'status': 'reviewed'})
        session = tx.get('tutor_sessions', session_id)
    tx.update('activity_jobs', job['id'], {'status': 'completed', 'result': {'items': items}, 'error': None})
    tx.touch('tutor_sessions', session_id)
