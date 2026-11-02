"""Read-along policy for extra reading; legacy selection lessons stay readable."""
from typing import Literal

from pydantic import Field, model_validator

from .activities import Choice, Content, QuestionContent

VERSION = 'book-read-along-3'

AUTHORING = '''BOOK READING QUESTION POLICY (overrides older teaching guidance)
Extra reading books are read-along lessons, not workbook assignments. Read the
assigned source completely and in order, including its printed reflection,
brainstorming and discussion questions. Keep these questions in read turns as
the author's words: they offer context or food for thought, not a request for
the reader to submit an answer. Do not convert them to ask/book_work, replace
them with choice checks, or silently drop them. Do not add an automatic quiz,
retelling, written/cursive task or an answer request hidden in teacher narration.
Use only read and say turns. The normal reading/Continue controls can advance
the lesson without assessing listening as mastery. Respond to actual learner
questions when asked; do not invent responses or require a follow-up answer.
Understand the passage's purpose before explaining: its central idea, argument,
theme or what a story illustrates. Teach that meaning, with relevant causal
links or comparisons, rather than incidental plot trivia or generic vocabulary.
Adapt to any genre and subject; do not force every book into a moral or argument.
Let explanations and their placement follow the material, without a target
number, spacing or word count. Preserve continuity when an interruption would
weaken understanding. No question or explanation is required at each break.'''

FEEDBACK = '''BOOK READING FEEDBACK POLICY (overrides older feedback guidance)
Keep feedback brief and return to reading. A selection is a complete answer;
never demand a typed explanation, retelling or a plain-text follow_up.
For a misconception, give a small clue and let the child retry the SAME choices.
Only when essential, request one ask_question with two to four choices and
response_modes ["choice"], answer_format single_choice or true_false,
evidence_requirement answer and require_reasoning false. Do not add another
question after a correct answer. A free student question gets a concise answer,
without a compulsory follow-up. Selection shows recognition, not explained mastery.'''

LEGACY_REVIEW = '''BOOK READING QUESTION POLICY
Generated checks use ask_question, answer_format single_choice with two to four
distinct choices or true_false, response_modes ["choice"], answer evidence and no
required reasoning. The authoring purpose discussion compiles to ask_question;
do not demand author-only purpose/response/turn fields in compiled activities.
Normally prefer two or three brief checks after a coherent reading section,
one at a time. Do not require typed explanations, retelling, matching or multi-select.
Printed brainstorming and discussion questions must not become writing tasks.
All answerable activities, including book_work, use true_false or single_choice.'''

REVIEW = '''BOOK READING QUESTION POLICY
For extra reading, preserve printed reflection/brainstorming/discussion questions
as narrated source text, not answerable activities. Do not demand a quiz, choice
conversion, typed response or retelling. Flag any required answer as a task error.
Check the explanations against the passage's actual purpose and central meaning,
not incidental plot details. Adapt to its genre and subject; do not impose a
particular theme, number of pauses, spacing or minimum explanation length.
Printed questions in read_source are not missing response stops. Distinguish
the author's rhetorical questions from teacher-added requests for an answer.'''


def enabled(context):
    return (context or {}).get('book_question_policy') in ('book-choice-1', 'book-choice-2', VERSION)


def read_along(context):
    return (context or {}).get('book_question_policy') == VERSION


def validate_book_work(turn):
    if turn.response.format not in ('true_false', 'single_choice'):
        raise ValueError('Book reading uses true/false or single-choice questions, including printed discussion questions.')
    if turn.response.format == 'single_choice':
        validate_labels(turn.response.choices)


def validate_activities(activities, context=None):
    from .activity_engine import RESPONSE_KINDS
    for activity in activities:
        kind, content = activity['kind'], activity.get('content') or {}
        if kind not in RESPONSE_KINDS:
            continue
        if read_along(context):
            raise ValueError('Extra reading books read printed reflection questions aloud without requiring answers or adding a quiz.')
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
