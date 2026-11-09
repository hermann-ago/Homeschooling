"""Paced lessons: one optional check of the book pages at the end.

In a paced subject the child does each exercise in the book and moves on
("in_book"). At the closing step a grown-up can photograph the pages; one AI
request reads the child's answers and says which ones to look at again. The
result is a note for the family, not an assessed attempt: it never grades the
child, reopens work or carries anything to a later lesson.
"""
import hashlib
import json
from contextlib import nullcontext
from typing import Literal

from pydantic import BaseModel, Field

from .service import TutorConflict, TutorError

EVENTS = {'submit_book_check', 'retry_book_check'}
MAX_PHOTOS = 8
MAX_BYTES = 20 * 1024 * 1024
WORKING = ('queued', 'checking')


class CheckedItem(BaseModel):
    item_id: str
    answer: str = Field('', max_length=2000)
    result: Literal['looks_right', 'check_again', 'not_found', 'unclear']
    note: str = Field('', max_length=500)


class BookCheckReply(BaseModel):
    items: list[CheckedItem] = Field(max_length=80)
    summary: str = Field('', max_length=800)


INSTRUCTIONS = ('Read only the work visible in the photos. Never invent an answer. '
    'Do not give the correct answer in a note; say what to look at again.')


def _jobs(db, session_id):
    return sorted((j for j in db.find('activity_jobs', session_id=session_id) if j['kind'] == 'book_check'),
                  key=lambda j: (j['created_at'], j['id']))


def _in_book(actions):
    return sorted((a for a in actions if a['status'] == 'in_book' and not a.get('parent_activity_id')),
                  key=lambda a: (a.get('activity_order') or 0, a['id']))


def public(engine, session, actions):
    items = _in_book(actions)
    job = (_jobs(engine.db, session['id']) or [None])[-1]
    view = {'count': len(items), 'status': job['status'] if job else None}
    if job:
        prompts = {t['item_id']: t['prompt'] for t in job['input_snapshot']['tasks']}
        result = job.get('result') or {}
        view.update(error=job.get('error'), summary=result.get('summary'), photos=len(job['input_snapshot']['evidence_ids']),
            items=[{**{k: r.get(k) for k in ('item_id', 'answer', 'result', 'note')}, 'prompt': prompts.get(r['item_id'], '')}
                   for r in result.get('items', [])])
    return view


def summary(db, session_id, actions):
    """For the completion summary: what was done in the book, and the latest check."""
    job = next((j for j in reversed(_jobs(db, session_id)) if j['status'] == 'completed'), None)
    return {'mode': 'paced', 'in_book': [a['action_id'] for a in _in_book(actions)],
        'check': {'job_id': job['id'], 'summary': job['result'].get('summary'),
                  'check_again': [r['item_id'] for r in job['result']['items'] if r['result'] in ('check_again', 'unclear')]}
                 if job else None}


def _key(engine, tx, action, answer_for, source_key):
    try:
        return answer_for(engine.ctx, action) or source_key(tx, action)
    except Exception:  # A missing key never blocks the check; the task is judged on its own.
        return None


def apply(engine, tx, session, action, event_type, payload, operation_id):
    from .source_key import original_refs, resolve as source_key
    from .page_script import answer_for
    if action['activity_kind'] != 'close_lesson':
        raise TutorError('Check the book pages from the end of the lesson')
    jobs = _jobs(tx, session['id'])
    if any(j['status'] in WORKING for j in jobs):
        raise TutorConflict('The photos are already being checked')
    if event_type == 'retry_book_check':
        failed = jobs[-1] if jobs and jobs[-1]['status'] == 'failed' else None
        if not failed:
            raise TutorConflict('There is no failed photo check to try again')
        tx.update('activity_jobs', failed['id'], {'status': 'queued', 'error': None})
        return
    items = _in_book(tx.find('lesson_actions', session_id=session['id']))
    if not items:
        raise TutorConflict('No exercises were done in the book in this lesson')
    ids = payload.get('evidence_ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_PHOTOS or len(set(ids)) != len(ids):
        raise TutorError(f'Attach between one and {MAX_PHOTOS} photos of the pages')
    images = []
    for eid in ids:
        e = tx.get('evidence_files', eid)
        if not e or (e['session_id'], e['child_id'], e['action_id']) != (session['id'], session['child_id'], action['action_id']):
            raise TutorError('Use photos taken at the end of this lesson')
        if e['mime_type'] not in ('image/jpeg', 'image/png', 'image/webp'):
            raise TutorError('Use JPEG, PNG or WebP photos')
        images.append({k: e[k] for k in ('file_path', 'sha256', 'mime_type', 'size_bytes')})
    if sum(i['size_bytes'] or 0 for i in images) > MAX_BYTES:
        raise TutorError('Use smaller photos, up to 20 MB together')
    tasks = []
    for a in items:
        key = (tx.get('assignment_items', a['assignment_item_id']) or {}).get('snapshot') if a.get('assignment_item_id') else None
        tasks.append({'item_id': a['action_id'], 'prompt': a['prompt'], 'original_question': original_refs(a),
            'pages': sorted({r['page'] for r in a.get('source_refs') or [] if r.get('page')}),
            'teacher_key': key or _key(engine, tx, a, answer_for, source_key)})
    topic = tx.get('topics', session['topic_id']) or {}
    with engine.ctx.ai.reading_handwriting():
        provider, model = engine.ctx.ai.selection()
    prompt = ('A child did these book exercises on paper during a lesson; a grown-up photographed the pages. '
        'For each task, copy the child\'s visible answer (empty when none is visible), then compare it with the '
        'teacher-only key when one is given, otherwise judge it from the task itself. result: looks_right; '
        'check_again (wrong, incomplete or misspelled); not_found (no answer visible for this task); unclear '
        '(cannot read it). note: for check_again or unclear, one short sentence for the child saying what to '
        'look at again, without the correct answer; empty otherwise. summary: one or two sentences for the parent. '
        f'Write notes and the summary in the lesson language ({topic.get("language") or "en-US"}). '
        'Return every item_id exactly once. Tasks (teacher_key is private):\n'
        + json.dumps(tasks, ensure_ascii=False, default=str))
    identity = 'book-check-' + hashlib.sha256(json.dumps([session['id'], operation_id]).encode()).hexdigest()[:32]
    tx.insert('activity_jobs', {'id': identity, 'session_id': session['id'], 'child_id': session['child_id'],
        'activity_id': action['action_id'], 'interaction_id': engine._interaction(tx, session['id'], action['action_id'])['id'],
        'kind': 'book_check', 'status': 'queued',
        'input_snapshot': json.loads(json.dumps({'evidence_ids': ids, 'images': images, 'tasks': tasks,
            'prompt': prompt, 'provider': provider, 'model': model}, default=str))})


def run(engine, session_id):
    """Provider work stays outside transactions; a retry reuses the same request identity."""
    from .page_work import exact_schema
    job = next((j for j in reversed(_jobs(engine.db, session_id)) if j['status'] in WORKING), None)
    if not job:
        return engine.state(session_id)
    snapshot = job['input_snapshot']
    try:
        with engine.db.transaction(kind='activity.book_check_claim') as tx:
            tx.update('activity_jobs', job['id'], {'status': 'checking'})
        images = [(engine.ctx.file_bytes(i['file_path'], i['sha256']), i['mime_type']) for i in snapshot['images']]
        playback = engine.db.get('lesson_playback', session_id)
        scope = engine.ctx.ai.scoped(playback['generation_scope_id']) if playback.get('generation_scope_id') else nullcontext()
        with scope, engine.ctx.ai.identified(job['id']), engine.ctx.ai.reading_handwriting():
            if tuple(engine.ctx.ai.selection()) != (snapshot['provider'], snapshot['model']):
                raise TutorConflict('The photo reader changed; send the photos again')
            reply = engine.ctx.ai.generate(snapshot['prompt'], images=images,
                schema=exact_schema(BookCheckReply, [t['item_id'] for t in snapshot['tasks']]),
                instructions=INSTRUCTIONS, max_output=12000)
        with engine.db.transaction(kind='activity.book_check_result') as tx:
            tx.update('activity_jobs', job['id'], {'status': 'completed', 'result': reply, 'error': None})
            tx.touch('tutor_sessions', session_id)
    except Exception:
        with engine.db.transaction(kind='activity.book_check_failed') as tx:
            tx.update('activity_jobs', job['id'], {'status': 'failed',
                'error': 'The photos are saved but could not be checked. Try again; nothing was marked wrong.'})
            tx.touch('tutor_sessions', session_id)
    return engine.state(session_id)
