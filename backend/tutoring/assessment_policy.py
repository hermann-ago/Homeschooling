"""Source-owned feedback expectations, shared by assessment and progression."""

DISCUSSION_KINDS = {'ask_question', 'tell_it_back', 'explain_thinking', 'compare_and_connect', 'apply_somewhere_new'}

PREPARATION_INSTRUCTIONS = '''Generated discussion and retelling focus on the main idea, with age-appropriate scope.
A substantially correct answer may omit incidental details: briefly supply a useful detail and continue.
Ask another question only for a central misconception or an essential unanswered part.
Required book questions keep their original scope and checked-key expectations; accept equivalent
wording unless spelling, notation or exact wording is the task. Keep feedback usually to one or two
useful sentences; longer explanations belong to requested help. Never invent a learner response.'''


def flexible_discussion(db, action):
    if action.get('origin') != 'adaptive' or action.get('activity_kind') not in DISCUSSION_KINDS:
        return False
    current, seen = action, set()
    while current:
        if current['id'] in seen:
            return False
        seen.add(current['id'])
        if current.get('origin') == 'required_book' or current.get('assignment_item_id') or current.get('assignment_id') or current.get('kind') == 'handwritten' or current.get('action_id', '').startswith('assignment-'):
            return False
        if (current.get('activity_content') or {}).get('evidence_requirement') in {'spelling', 'handwriting', 'written_steps', 'diagram'}:
            return False
        parent = current.get('parent_activity_id')
        if not parent:
            source = current.get('source_action_id')
            if not source:
                return True
            current = db.get('lesson_actions', source)
            if not current or (current['child_id'], current['subject_id']) != (action['child_id'], action['subject_id']):
                return False
            continue
        current = next((row for row in db.find('lesson_actions', session_id=action['session_id']) if row['action_id'] == parent), None)
        if current is None:
            return False
    return False


def instructions(db, action):
    if flexible_discussion(db, action):
        return PREPARATION_INSTRUCTIONS+'\n'+'''Feedback policy: FLEXIBLE GENERATED DISCUSSION.
This is an AI-created conversation/retelling task, not a keyed book exercise.
For a substantially correct answer, acknowledge the specific good idea and move on:
ready_to_continue=true, follow_up=null, activity_requests=[]. A minor omission is
not a compulsory correction. Use Correct when the main learning goal is met;
Partly correct may also be sufficient to continue. Keep the actual outcome honest.
Use Not yet and one focused follow-up for a substantive problem. Never demand that
the child repeat an answer you just supplied. A detail you supply is assistance,
not independent recall by the child. This policy also applies to follow-ups.'''
    return PREPARATION_INSTRUCTIONS+'\n'+'''Feedback policy: SOURCE-BOUND ASSESSMENT.
Do not relax required work because it looks like a discussion question.
Keep missing evidence and uncertain keys unassessed.'''


def can_continue(db, action, interaction):
    if not interaction or interaction['status'] != 'awaiting_followup' or not flexible_discussion(db, action):
        return False
    responses = db.find('activity_responses', session_id=action['session_id'], activity_id=action['action_id'])
    responses = sorted(responses, key=lambda row: (row['created_at'], row['id']))
    if not responses or responses[-1]['status'] != 'assessed':
        return False
    response = responses[-1]
    previous = db.get('activity_interactions', response['interaction_id'])
    message = db.get('lesson_dialogue', response.get('message_id'))
    return bool(previous and previous['sequence'] + 1 == interaction['sequence'] and
                ((message or {}).get('assessment') or {}).get('result') in ('Correct', 'Partly correct'))
