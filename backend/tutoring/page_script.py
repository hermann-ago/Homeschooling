"""Direct teaching from selected original pages, without an exercise inventory."""
import copy
import json
import re
from typing import Literal, Union
from pydantic import Field, model_validator
from .activities import Content
from .teaching_script import Say, Ask, Response, _response
from . import book_questions, extra_questions

# 3: one composed prompt (lesson_prompt.py) and sentence references in PDF
# lessons; 2: stacked policy blocks, transcribed readings only.
VERSION = 'original-pages-3'
# A compiled reading segment holds at most 12,000 characters (guide.GuideSegment).
READING_CHUNK = 11000


def referenced_reading(sentences, first, last):
    """Exact text of sentences first..last with their paragraph breaks, in
    chunks short enough for one reading segment each."""
    chunks, text, start, paragraph = [], '', first, None
    for i in range(first, last + 1):
        sentence = sentences[i]
        new_paragraph = sentence.get('paragraphIndex', 0) != paragraph
        if text and new_paragraph and len(text) + len(sentence['text']) > READING_CHUNK:
            chunks.append((start, i - 1, text))
            text, start = '', i
        text += ('\n\n' if new_paragraph else ' ') + sentence['text'] if text else sentence['text']
        paragraph = sentence.get('paragraphIndex', 0)
    chunks.append((start, last, text))
    return chunks


BOOK_TEACHING_POLICY = 'book-explanations-2'


class Read(Content):
    type: Literal['read']
    text: str | None = Field(None, min_length=1, max_length=60000)
    document_id: int | None = Field(None, ge=1)
    page_start: int | None = Field(None, ge=1)
    page_end: int | None = Field(None, ge=1)
    # Or a reference to numbered sentences of the PDF text layer (inclusive),
    # so clean prose is not re-typed by the writer.
    first: int | None = Field(None, ge=0)
    last: int | None = Field(None, ge=0)


class BookWork(Content):
    type: Literal['book_work']
    document_id: int = Field(ge=1)
    page: int = Field(ge=1)
    prompt: str = Field(min_length=1, max_length=8000)
    # The printed item labels this turn covers ("10", "B3"), checked against
    # the lesson's exercise assignment when its pages are shared.
    items: list[str] = Field(default_factory=list, max_length=30)
    response: Response = Field(default_factory=Response)
    # Teacher-only: the answer key's answer for this exercise and the key page
    # it came from. Frozen with the raw script; never compiled into child content.
    answer: str | None = Field(None, min_length=1, max_length=4000)
    answer_page: int | None = Field(None, ge=1)
    # Teacher-only, for blanks: the key's answer for each box, in order, so the
    # app can check simple answers itself.
    answers: list[str] = Field(default_factory=list, max_length=30)
    # Teacher-only, for blanks no key covers: the writer's expected answer per
    # box. Never used for checking until a grown-up approves it.
    proposed_answers: list[str] = Field(default_factory=list, max_length=30)
    # The turn where the book asks the child to watch its video lesson; the app plays it here.
    video: bool = False

    @model_validator(mode='after')
    def answers_match_blanks(self):
        for values in (self.answers, self.proposed_answers):
            if values and (self.response.format != 'blanks' or len(values) != len(self.response.blanks)
                           or any(not a.strip() or len(a) > 200 for a in values)):
                raise ValueError('Answers give one short key answer per blank, in order.')
        if self.answers and self.proposed_answers:
            raise ValueError('Proposed answers are only for blanks the answer key does not cover.')
        return self


class Script(Content):
    welcome: str = Field(min_length=1, max_length=1800)
    turns: list[Union[Say, Read, Ask, BookWork]] = Field(min_length=1, max_length=150)
    closing: str = Field(min_length=1, max_length=12000)

    @classmethod
    def provider_json_schema(cls):
        # One object grammar for answer controls. Nested alternative object
        # shapes stalled a real structured reply at book_work.response: the
        # provider emitted whitespace until its entire output budget ran out.
        # Keep the canonical fields and validate their combinations locally.
        return cls.model_json_schema()

    @classmethod
    def google_json_schema(cls):
        return cls.provider_json_schema()


# A teacher sentence may also open with a quotation mark or bracket.
OPENING_MARKS = "\"'“‘¿¡(["


def check_complete_text(script):
    """Teacher text must not be a cut-off fragment (": cost, choice…"); the
    reply is malformed and can be replaced, not approved and narrated."""
    from .guide import GuideError
    spoken = [('welcome', script.welcome), ('closing', script.closing)]
    spoken += [(f'teaching step {i + 1}', t.text) for i, t in enumerate(script.turns) if isinstance(t, Say)]
    spoken += [(f'question {i + 1}', t.prompt) for i, t in enumerate(script.turns) if isinstance(t, Ask)]
    for name, text in spoken:
        start = (text or '').strip()[:1]
        if not start or not (start.isalnum() or start in OPENING_MARKS):
            raise GuideError(f'The {name} looks cut off ("{(text or "").strip()[:40]}"). Replace this reply.', invalid_response=True)


def compile_script(value, passage, context, language):
    from .guide import GuidePlan
    script = Script.model_validate(value)
    check_complete_text(script)
    if book_questions.read_along(context):
        last_read = max((i for i, t in enumerate(script.turns) if isinstance(t, Read)), default=-1)
        quiz = book_questions.end_quiz(context)
        if any(isinstance(t, BookWork) or (isinstance(t, Ask) and (not quiz or i < last_read))
               for i, t in enumerate(script.turns)):
            raise ValueError('Extra reading books read the whole chapter, printed questions included, before any quiz; '
                             'only a short choice quiz may follow the last reading.' if quiz else
                             'Extra reading books read printed reflection questions aloud without requiring answers or adding a quiz.')
    pages = {(p['document_id'], p['page']): p for p in (context.get('visual_source') or {}).get('pages', [])}
    segments = [{'type': 'intro', 'text': script.welcome}]
    referenced = -1
    if sum(isinstance(t, BookWork) and t.video for t in script.turns) > 1:
        raise ValueError('Only one book_work turn plays the video lesson: the one where the book asks to watch it.')
    for turn in script.turns:
        if isinstance(turn, Say):
            segments.append({'type': 'explain', 'text': turn.text})
        elif isinstance(turn, Read):
            if turn.text:
                if (turn.document_id is None or turn.page_start is None or turn.page_end is None
                        or turn.page_end < turn.page_start or turn.page_end-turn.page_start > 39
                        or any((turn.document_id, p) not in pages or pages[(turn.document_id, p)].get('role') == 'answer_key'
                               for p in range(turn.page_start, turn.page_end+1))):
                    raise ValueError('A source reading must identify its attached original student pages.')
                segments.append({'type': 'read', 'text': turn.text,
                    'source_refs': [{'document_id': turn.document_id, 'page': p} for p in range(turn.page_start,turn.page_end+1)]})
            else:
                if turn.first is None or turn.last is None:
                    raise ValueError('A reading needs either its text with pages, or first and last numbered sentences.')
                if not 0 <= turn.first <= turn.last < len(passage['sentences']):
                    raise ValueError('The reading range is outside the assigned original text.')
                if turn.first <= referenced:
                    raise ValueError('Numbered readings must move forward without repeating sentences.')
                referenced = turn.last
                for first, last, text in referenced_reading(passage['sentences'], turn.first, turn.last):
                    segments.append({'type': 'read', 'from': first, 'to': last, 'text': text})
        elif isinstance(turn, Ask):
            if book_questions.enabled(context):
                book_questions.validate_ask(turn)
            elif extra_questions.enabled(context):
                extra_questions.validate_ask(turn)
            kind = {'discussion': 'ask_question', 'retelling': 'tell_it_back', 'reasoning': 'explain_thinking'}[turn.purpose]
            if turn.response.format == 'observe':
                kind, content = 'explain_or_observe', {'text': turn.prompt}
            else:
                content = {'prompt': turn.prompt, **_response(turn.response, language)}
                if book_questions.enabled(context) or extra_questions.enabled(context):
                    content['response_modes'] = ['choice']
            segments.append({'type': 'activity', 'activity_kind': kind, 'content': content, 'origin': 'adaptive'})
        else:
            if book_questions.enabled(context):
                book_questions.validate_book_work(turn)
            reveals_answer(turn, segments[-1])
            page = pages.get((turn.document_id, turn.page))
            if not page or page.get('role') == 'answer_key':
                raise ValueError('Book work must refer to an attached student page.')
            observation = turn.response.format in ('observe', 'parent_check')
            content = ({'text': turn.prompt, **({'parent_check': True} if turn.response.format == 'parent_check' else {})}
                       if observation else {'prompt': turn.prompt, **_response(turn.response, language)})
            if book_questions.enabled(context):
                content['response_modes'] = ['choice']
            if not observation:
                content['printed_page'] = str(page.get('printed_page') or turn.page)
            # Book and page labels are server-bound; answers stay private.
            if not observation:
                content['book_name'] = page.get('book_name') or 'Your book'
            if turn.video and context.get('lesson_video'):
                content['video_here'] = True
            segments.append({'type': 'activity', 'activity_kind': 'explain_or_observe' if observation else 'request_book_work',
                'content': content, 'origin': 'required_book',
                'source_refs': [{'document_id': turn.document_id, 'page': turn.page}]})
    check_assigned_items(script, context.get('exercise_assignment'))
    segments.append({'type': 'recap', 'text': script.closing})
    return GuidePlan.model_validate({'mode': 'tidy', 'segments': segments}).model_dump(by_alias=True, exclude_none=True)


def check_assigned_items(script, assignment):
    """On shared exercise pages, the script covers exactly this lesson's items."""
    if not assignment:
        return
    from .exercise_assignment import label_key
    expected = {(p['document_id'], p['page']): {label_key(i): i for i in p['items']} for p in assignment['pages']}
    covered = set()
    for turn in script.turns:
        if not isinstance(turn, BookWork) or (turn.document_id, turn.page) not in expected:
            continue
        if not turn.items:
            raise ValueError(f'Book work on PDF page {turn.page} must list the printed items it covers.')
        for label in turn.items:
            key = (turn.document_id, label_key(label))
            # An item continued from an earlier shared page keeps that page's label.
            pages = [page for (doc, page), labels in expected.items() if doc == turn.document_id and label_key(label) in labels]
            if not pages:
                raise ValueError(f'Item {label} on PDF page {turn.page} belongs to another lesson.')
            if key in covered:
                raise ValueError(f'Item {label} appears more than once.')
            covered.add(key)
    missing = [label for (doc, _), labels in expected.items() for key, label in labels.items() if (doc, key) not in covered]
    if missing:
        raise ValueError('The lesson leaves out its assigned exercise items: ' + ', '.join(missing) + '.')


BINARY_ANSWERS = {'true', 'false', 'verdadeiro', 'falso', 'yes', 'no', 'sim', 'não'}
CHOICE_FORMATS = {'true_false', 'single_choice', 'multiple_select', 'matching'}


def _words(text):
    return ' '.join(re.findall(r"[\w']+", (text or '').casefold()))


def reveals_answer(turn, before):
    """A key answer must not be spoken just before, or written into, its own question."""
    answer = _words(turn.answer)
    if len(answer) < 4 or answer in BINARY_ANSWERS:
        return  # Letters, numbers and true/false cannot be checked by wording.
    spoken = before.get('text') if before.get('type') in ('explain', 'intro') else ''
    # Choice questions print their options, the right one included.
    prompt = '' if turn.response.format in CHOICE_FORMATS else turn.prompt
    if f' {answer} ' in f' {_words(spoken)} ' or f' {answer} ' in f' {_words(prompt)} ':
        raise ValueError('An exercise prompt or the explanation just before it reveals its answer-key answer.')


def teaching_summary(script, passage):
    """Structural review aid; semantic quality still needs source-aware review."""
    turns = script.get('turns', [])
    reading_words = 0
    for turn in turns:
        if turn.get('type') != 'read': continue
        text = turn.get('text')
        if not text and isinstance(turn.get('first'), int) and isinstance(turn.get('last'), int):
            text = ' '.join(s['text'] for s in passage['sentences'][turn['first']:turn['last'] + 1])
        reading_words += len((text or '').split())
    explanations = [(i, turn['text']) for i, turn in enumerate(turns) if turn.get('type') == 'say']
    return {'reading_words': reading_words, 'explanations': len(explanations),
        'explanation_words': sum(len(text.split()) for _, text in explanations),
        'between_readings': sum(any(t.get('type') == 'read' for t in turns[:i])
            and any(t.get('type') == 'read' for t in turns[i + 1:]) for i, _ in explanations)}


def schema(passage, context, language):
    class AssignedScript(Script):
        @classmethod
        def provider_json_schema(cls):
            value = super().provider_json_schema()
            if book_questions.enabled(context) or extra_questions.enabled(context):
                # The tutor's own questions are selections; for extra reading, printed ones too.
                value['$defs']['BookChoiceResponse'] = {
                    'type': 'object', 'properties': {
                        'format': {'type': 'string', 'enum': ['true_false', 'single_choice']},
                        'choices': {'type': 'array', 'maxItems': 4,
                                    'items': {'type': 'string', 'minLength': 1, 'maxLength': 1000}}},
                    'required': ['format', 'choices'], 'additionalProperties': False}
                ask = value['$defs']['Ask']['properties']
                ask['purpose'] = {'type': 'string', 'enum': ['discussion']}
                ask['response'] = {'$ref': '#/$defs/BookChoiceResponse'}
                if book_questions.enabled(context):
                    value['$defs']['BookWork']['properties']['response'] = {'$ref': '#/$defs/BookChoiceResponse'}
            visual, numbered = bool(context.get('visual_source')), bool(passage.get('sentences'))
            names = (('type','text','document_id','page_start','page_end') + (('first','last') if numbered else ())
                     if visual else ('type','first','last'))
            # With both shapes on offer, unused fields are null (strict schemas require every field).
            either = visual and numbered
            kind = lambda t: [t, 'null'] if either else t
            props = value['$defs']['Read']['properties']
            props['text'] = {'type':kind('string'),'minLength':1,'maxLength':60000}
            for name in ('document_id','page_start','page_end'):
                props[name] = {'type':kind('integer'),'minimum':1}
            for name in ('first','last'):
                props[name] = {'type':kind('integer'),'minimum':0}
            value['$defs']['Read'] = {'type':'object','properties':{k:props[k] for k in names},
                                     'required':list(names),'additionalProperties':False}
            if book_questions.read_along(context):
                value['properties']['turns']['items'] = {'anyOf': [
                    {'$ref': '#/$defs/Say'}, {'$ref': '#/$defs/Read'},
                    *([{'$ref': '#/$defs/Ask'}] if book_questions.end_quiz(context) else [])]}
            return value
        @model_validator(mode='after')
        def locators(self):
            compile_script(self.model_dump(), passage, context, language)
            return self
    return AssignedScript


def prompt(passage, *, subject, learner, grade, language, skill='', learner_context=None):
    from .lesson_prompt import writer_prompt
    return writer_prompt(passage, subject=subject, learner=learner, grade=grade, language=language,
                         skill=skill, learner_context=learner_context, policy=VERSION)


def answer_key(snapshot, approvals=()):
    """Each book exercise with its recorded key answer, any proposed answers for
    boxes no key covers, and a grown-up's approval, for the family's review."""
    turns = (((snapshot or {}).get('teaching_script') or {}).get('script') or {}).get('turns', [])
    approved = {a['work_index']: a['answers'] for a in approvals}
    work = [t for t in turns if t.get('type') == 'book_work']
    return [{'index': i, 'prompt': t['prompt'], 'answer': t.get('answer'), 'answer_page': t.get('answer_page'),
             'blanks': (t.get('response') or {}).get('blanks') or [],
             'proposed_answers': t.get('proposed_answers') or [], 'approved_answers': approved.get(i)}
            for i, t in enumerate(work)]


def approvals(ctx, guide_id):
    return ctx.store.find('answer_approvals', guide_id=guide_id)


def answer_for(ctx, action):
    """The pinned guide's key answer for a book-work activity, for grading only.

    compile_script emits one required-book activity per book_work turn, in
    order, so the running lesson's frozen raw script lines up with its guide.
    A grown-up's approved answers stand in for a key the book does not have.
    """
    playback = ctx.store.get('lesson_playback', action['session_id'])
    prepared = ((playback or {}).get('context_snapshot') or {}).get('prepared_guide') or {}
    turns = [t for t in ((prepared.get('teaching_script') or {}).get('script') or {}).get('turns', [])
             if t.get('type') == 'book_work']
    approved = lambda: {a['work_index']: a['answers'] for a in approvals(ctx, playback['guide_id'])} if playback else {}
    if not any(t.get('answer') for t in turns) and not approved():
        return None
    row = ctx.store.get('guides', playback['guide_id'])
    guide = json.loads(ctx.file_bytes(row['guide_path'], row.get('guide_file_sha256')))
    work = [a['id'] for a in guide.get('activities', [])
            if a.get('origin') == 'required_book' and a['kind'] in ('request_book_work', 'explain_or_observe')]
    if len(work) != len(turns) or action['action_id'] not in work:
        return None
    index = work.index(action['action_id'])
    turn = turns[index]
    granted = {} if turn.get('answer') else approved()
    if index in granted:
        return {'answer_key': '; '.join(granted[index]), 'answer_items': granted[index],
                'note': 'Approved by a grown-up for this lesson (the book has no key). Judge against the question '
                        'and the assigned reading too; equivalent wording is correct unless exact wording is the task.'}
    if not turn.get('answer'):
        return None
    return {'answer_key': turn['answer'], 'answer_key_page': turn.get('answer_page'),
            **({'answer_items': turn['answers']} if turn.get('answers') else {}),
            'note': 'Copied from the answer key by the lesson writer. Judge against the question and the '
                    'assigned reading too; equivalent wording is correct unless exact wording is the task.'}
