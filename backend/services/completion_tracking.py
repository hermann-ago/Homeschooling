from datetime import date, datetime, timezone
import uuid


def mark_topic_completed(topic: dict, completed_at: datetime | None = None, *, source='manual') -> dict:
    """Mark a topic complete and automatically record when it happened."""
    topic["completed"] = True
    topic['completion_source']=source
    if topic.get("completed_at") is None:
        topic["completed_at"] = completed_at or datetime.now(timezone.utc)
    return topic


def complete_scheduled_history(tx, topic_ids, recorded_at):
    """A finished topic ticks its daily tasks through today, however the lesson was opened.

    Future days stay as they are, so the planner can still move or drop them.
    """
    done = {c["slot_id"] for c in tx.all("completions")}
    for slot in tx.all("scheduled_slots"):
        if slot["topic_id"] in topic_ids and slot["date"] <= date.today() and slot["id"] not in done:
            tx.insert("completions", {"slot_id": slot["id"], "completed_at": recorded_at})


def mark_topic_incomplete(topic: dict) -> dict:
    """Undo topic completion and its recorded completion time."""
    topic["completed"] = False
    topic["completed_at"] = None
    topic['completion_source']=None
    return topic


def close_topic_sessions(tx,topic,recorded_at,source,session_ids=None):
    """Administrative completion preserves actual answers, drafts and unassessed work."""
    closed=[]
    for session in tx.find('tutor_sessions',topic_id=topic['id']):
        if session['status'] not in ('active','unfinished'):continue
        if session_ids is not None and session['id'] not in session_ids:continue
        actions=tx.find('lesson_actions',session_id=session['id'])
        readings=[a for a in actions if a.get('activity_kind')=='read_source']
        attempts=tx.find('attempts',session_id=session['id'])
        summary={'version':1,'lesson_status':'completed','completion_source':source,
            'reading':{'status':'reached' if readings and all(a['status']=='answered' for a in readings) else 'not_established',
                       'activity_ids':[a['action_id'] for a in readings]},
            'understanding':topic.get('understanding') or 'Not assessed','attempt_ids':[a['id'] for a in attempts],
            'pending_work':[{'activity_id':a['action_id'],'prompt':a['prompt'],'status':a['status'],'origin':a.get('origin')}
                            for a in actions if a['status'] in ('pending','skipped')]}
        tx.update('tutor_sessions',session['id'],{'status':'completed','phase':'finished','finished_at':recorded_at,
            'completion_source':source,'completion_summary':summary})
        if tx.get('lesson_playback',session['id']):
            tx.update('lesson_playback',session['id'],{'action_id':None,'on_break':False})
        for checkpoint in tx.find('checkpoints',session_id=session['id']):
            if checkpoint['status']=='open':tx.update('checkpoints',checkpoint['id'],{'status':'closed'})
        closed.append(session['id'])
    return closed


def save_topic(tx, topic: dict, *, completion_requested=True, **changes) -> dict:
    previous=tx.get('topics',topic['id'])
    row=tx.update('topics',topic['id'],{**changes,'completed':topic['completed'],'completed_at':topic['completed_at'],
        'completion_source':topic.get('completion_source')})
    closed=[]
    if completion_requested and row['completed'] and row.get('completion_source')=='manual':
        closed=close_topic_sessions(tx,row,datetime.now(timezone.utc),'manual')
    if previous['completed']!=row['completed'] or previous.get('completion_source')!=row.get('completion_source') or closed:
        subject=tx.get('subjects',row['subject_id'])
        tx.insert('topic_completion_events',{'id':'completion-'+uuid.uuid4().hex,'topic_id':row['id'],
            'subject_id':row['subject_id'],'child_id':subject['child_id'],'completed':row['completed'],
            'source':'manual','recorded_at':datetime.now(timezone.utc),'closed_session_ids':closed})
    return row


def reconcile_completed_topics(db):
    """Idempotently close legacy sessions whose chapter was already marked done.

    The old record proves chapter completion, but not who recorded it. Preserve
    that unknown provenance instead of labeling historical completion as manual.
    """
    done={t['id']:t for t in db.all('topics') if t['completed']}
    pending=[s for s in db.all('tutor_sessions') if s['status'] in ('active','unfinished') and s.get('session_type')!='repeat' and s['topic_id'] in done
             and (not done[s['topic_id']].get('completed_at') or not s.get('started_at') or s['started_at']<=done[s['topic_id']]['completed_at'])]
    if pending:
        with db.transaction(kind='completion.reconcile.v1') as tx:
            for tid in {s['topic_id'] for s in pending}:
                close_topic_sessions(tx,done[tid],datetime.now(timezone.utc),'topic_completion',
                                     {s['id'] for s in pending if s['topic_id']==tid})
