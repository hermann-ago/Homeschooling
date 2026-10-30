"""Versioned, selection-only comprehension checks for optional family reading."""
from typing import Literal

from pydantic import Field, model_validator

from .activities import Choice, Content, QuestionContent

VERSION = 'book-choice-2'

AUTHORING = '''BOOK READING QUESTION POLICY (overrides older teaching guidance)
Keep reading enjoyable and continuous. Finish a coherent story/section before its
brief comprehension check; normally use two or three questions, one at a time.
Every AI-generated ask must use purpose discussion and response format single_choice
with two to four short, distinct choices, or true_false. Yes/no questions use
single_choice with localized Yes and No labels. Include one clear answer and
plausible alternatives grounded in the assigned text; keep the answer private.
No typed explanations, retellings, matching, multi-select or extra "why?" task.
You can check reasoning by offering possible reasons as choices. Do not ask a
question inside say/welcome/closing that would need an unrepresented answer.
This selection-only rule also applies to printed discussion and brainstorming
questions. They are not mandatory writing assignments for book reading. Replace
them with a few source-grounded selection checks or omit them; keep the original
story and explanatory reading intact. Never use book_work to bypass this rule.'''

FEEDBACK = '''BOOK READING FEEDBACK POLICY (overrides older feedback guidance)
Keep feedback brief and return to reading. A selection is a complete answer;
never demand a typed explanation, retelling or a plain-text follow_up.
For a misconception, give a small clue and let the child retry the SAME choices.
Only when essential, request one ask_question with two to four choices and
response_modes ["choice"], answer_format single_choice or true_false,
evidence_requirement answer and require_reasoning false. Do not add another
question after a correct answer. A free student question gets a concise answer,
without a compulsory follow-up. Selection shows recognition, not explained mastery.'''

REVIEW = '''BOOK READING QUESTION POLICY
Generated checks use ask_question, answer_format single_choice with two to four
distinct choices or true_false, response_modes ["choice"], answer evidence and no
required reasoning. The authoring purpose discussion compiles to ask_question;
do not demand author-only purpose/response/turn fields in compiled activities.
Normally prefer two or three brief checks after a coherent reading section,
one at a time. Do not require typed explanations, retelling, matching or multi-select.
Printed brainstorming and discussion questions must not become writing tasks.
All answerable activities, including book_work, use true_false or single_choice.'''


def enabled(context):
    return (context or {}).get('book_question_policy') in ('book-choice-1', VERSION)


def validate_book_work(turn):
    if turn.response.format not in ('true_false', 'single_choice'):
        raise ValueError('Book reading uses true/false or single-choice questions, including printed discussion questions.')
    if turn.response.format == 'single_choice':
        validate_labels(turn.response.choices)


def validate_activities(activities):
    from .activity_engine import RESPONSE_KINDS
    for activity in activities:
        kind, content = activity['kind'], activity.get('content') or {}
        if kind not in RESPONSE_KINDS:
            continue
        if (kind not in ('ask_question', 'request_book_work') or content.get('answer_format') not in ('true_false', 'single_choice')
                or content.get('response_modes') != ['choice'] or content.get('require_reasoning')):
            raise ValueError('Update this book lesson to true/false or single-choice questions before preparing voice.')
        validate_labels([c['label'] for c in content.get('choices', [])])


def validate_labels(labels):
    if not 2 <= len(labels) <= 4 or len({' '.join(s.split()).casefold() for s in labels}) != len(labels):
        raise ValueError('Book reading questions need two to four distinct choices.')


def validate_ask(turn):
    if turn.purpose != 'discussion' or turn.response.format not in ('single_choice', 'true_false'):
        raise ValueError('Book reading checks must use simple selection questions without typed reasoning.')
    if turn.response.format == 'single_choice':
        validate_labels(turn.response.choices)


class ChoiceQuestion(QuestionContent):
    choices: list[Choice] = Field(default_factory=list, min_length=2, max_length=4)
    response_modes: list[Literal['choice']] = Field(default_factory=lambda: ['choice'], min_length=1, max_length=1)
    answer_format: Literal['single_choice', 'true_false'] = 'single_choice'
    evidence_requirement: Literal['answer'] = 'answer'
    require_reasoning: Literal[False] = False
    matching: None = None

    @model_validator(mode='before')
    @classmethod
    def selection_defaults(cls, value):
        if isinstance(value, dict):
            value = {'response_modes': ['choice'], **value}
        return value

    @model_validator(mode='after')
    def simple_selection(self):
        validate_labels([choice.label for choice in self.choices])
        return self


class ChoiceProposal(Content):
    kind: Literal['ask_question']
    content: ChoiceQuestion
