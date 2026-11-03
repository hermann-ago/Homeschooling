"""A subject can keep the tutor's own added questions to simple selections.

The family sets ``subjects.extra_questions`` to ``"choice"``. The policy is frozen
into each new preparation's context, so running lessons and saved guides keep
the rules they were prepared with. The book's own exercises are unaffected.
"""
from .book_questions import validate_labels

POLICY = 'choice-1'


def context_for(subject):
    return {'extra_question_policy': POLICY} if (subject or {}).get('extra_questions') == 'choice' else {}


def enabled(context):
    return (context or {}).get('extra_question_policy') == POLICY


AUTHORING = '''EXTRA QUESTION POLICY (the family's choice for this subject)
Your own questions (ask turns) are quick checks: purpose discussion with true_false,
or single_choice with two to four distinct choices. Do not add typed explanations,
retellings or reasoning questions of your own. Book work keeps the book's own task
and the response format that task needs.'''

FEEDBACK = '''EXTRA QUESTION POLICY (the family's choice for this subject; overrides older feedback guidance)
Keep feedback brief. Never use a plain-text follow_up or ask for a typed explanation.
For a mistake, give a small clue and let the child retry the same task. Only when
essential, request one ask_question with two to four choices, response_modes ["choice"],
answer_format single_choice or true_false, evidence_requirement answer and
require_reasoning false. Do not add a question after a correct answer.'''

HINT = '\nKeep this support brief. Do not add a new question or request a typed explanation.'


def validate_ask(turn):
    if turn.purpose != 'discussion' or turn.response.format not in ('single_choice', 'true_false'):
        raise ValueError("This subject keeps the tutor's own questions to true/false or single choice.")
    if turn.response.format == 'single_choice':
        validate_labels(turn.response.choices)
