"""Guided lessons: the book passage walked through by a teacher's voice.

An AI writes a *plan* for the lesson: a short introduction, the book text in
order, a few short explanations between parts of it, and a recap. The plan
never carries the book text itself in the usual ("expand") mode; it names
ranges of the passage's sentences, and the server puts the book's own words
in. Whatever the AI returns, every sentence of the passage is read, once and
in order, so a guided lesson can add to the book but never drop or change it.

Some lessons already are a teacher's script (Say:, Ask:, notes to the parent,
exercise instructions). For those the AI may choose "tidy": it rewrites the
reading parts into one clean, concise spoken walk-through. Each rewritten part
still names the sentences it covers, so the original page can follow along.

The guide is saved as JSON in the subject's Lesson Content folder and indexed
in the ``guides`` table with the passage it was written for; when the book
text or boundaries change, the old guide is shown as out of date. Its voice
is an ordinary narration track built from the guide's sentences.
"""
from __future__ import annotations

import json
import copy
import os
import re
import uuid
from typing import Literal, Union
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, model_validator
from datetime import datetime, timezone

from storage import layout

from .passages import passage_sha256, split_sentences
from .activities import (ACTIVITY_KINDS, CONTRACT_VERSION, ActivityContent, SourceRef,
                         definitions, requires_response, validate_activity, parse_activity)
from .activities import activity_content_model

GUIDE_VERSION = 4
# Provider selection is explicit. A failed request never upgrades or switches models.
DEFAULT_MODELS = ("gpt-6.1-sol",)
TEACHER_TYPES = ("intro", "explain", "recap")
MAX_TEACHER_CHARACTERS = 700
MAX_INTRO_CHARACTERS = 1800
MAX_PLAN_OUTPUT = 16384
FORMAT_INSTRUCTIONS=("Return exactly one JSON object matching the supplied schema. "
                     "Do not include explanations, commentary, or another object before or after it.")


class GuideError(ValueError):
    def __init__(self,message,*,invalid_response=False,reason=None):
        super().__init__(message)
        self.invalid_response=invalid_response
        self.reason=reason


class GuideSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["intro", "read", "explain", "action", "recap", "activity"]
    text: str | None = Field(None, max_length=12000)
    first: int | None = Field(None, alias="from")
    last: int | None = Field(None, alias="to")
    source_block_id: str | None = Field(None,max_length=150)
    action_kind: Literal["answer", "handwritten", "activity"] | None = None
    concept_ids: list[str] = Field(default_factory=list, max_length=2)
    activity_kind: Literal[ACTIVITY_KINDS] | None = None
    content: ActivityContent | None = None
    origin: Literal["required_book", "adaptive", "review"] = "adaptive"
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=20)
    parent_activity_id: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def registered_content(self):
        if self.type == "activity":
            if not self.activity_kind or self.content is None:
                raise ValueError("An activity segment needs its registered kind and content")
            self.content=parse_activity(self.activity_kind, self.content.model_dump(exclude_none=True))
        return self


class GuidePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["expand", "tidy"]
    segments: list[GuideSegment] = Field(min_length=1,max_length=200)

    @model_validator(mode='after')
    def tidy_readings_have_spoken_text(self):
        if self.mode=='tidy' and any(s.type=='read' and not (s.text or '').strip() and not s.source_block_id for s in self.segments):
            raise ValueError('Tidy reading segments require rewritten spoken text; raw extraction is not a fallback.')
        return self

    @classmethod
    def provider_json_schema(cls):
        # Keep saved/legacy validation stable while the provider emits only the
        # fields relevant to each segment. Strict schemas otherwise require all
        # nullable activity metadata on every ordinary sentence/read segment.
        schema = ProviderGuidePlan.model_json_schema(by_alias=True)
        # Catalog identities belong to the server's exercise insertion, never to
        # planner-authored source references. Keep legacy parsing unchanged.
        for name in ('exercise_id', 'version_id'):
            schema['$defs']['SourceRef']['properties'][name] = {'type': 'null'}
        return schema

    @classmethod
    def google_json_schema(cls):
        # Bounded collection grammar causes Google to reject the lesson schema.
        # Keep its typed contracts; enforce size limits in canonical validation.
        schema=cls.provider_json_schema()
        def simplify(node):
            if isinstance(node,dict):
                for key in ('maxItems','minItems','maxLength','minLength','title','default'):
                    node.pop(key,None)
                for key,value in node.items():
                    if key in ('properties','$defs'):
                        for child in value.values():simplify(child)
                    elif key in ('items','anyOf','oneOf','allOf','additionalProperties'):
                        simplify(value)
            elif isinstance(node,list):
                for value in node:simplify(value)
        simplify(schema)
        return schema

    @classmethod
    def recover_duplicate_response(cls, text: str) -> dict | None:
        """Recover repeated identical plans, including cached provider delimiters.

        No content is invented, repaired or selected between alternatives. Every
        complete object must validate and agree after nullable defaults normalize.
        A partial final object, conflicting plan or trailing prose stays an error.
        """
        decoder = json.JSONDecoder()
        text = text.strip()
        position, copies, result = 0, 0, None
        try:
            while position < len(text):
                value, end = decoder.raw_decode(text, position)
                if not isinstance(value, dict) or set(value) != {"mode", "segments"}:
                    return None
                candidate = cls.model_validate(value).model_dump(by_alias=True)
                if not candidate["segments"] or (result is not None and candidate != result):
                    return None
                result, copies = candidate, copies + 1
                if end == len(text):
                    return result if copies > 1 else None
                position = text.find('{', end)
                # Bound provider separator debris. Never scan through an arbitrary
                # explanation, or accept nested material as a different root plan.
                if position < 0 or position - end > 64 or copies >= 5:
                    return None
        except (ValueError, ValidationError):
            return None
        return None


class SpokenPlanSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['intro','explain','recap']
    text: str = Field(min_length=1,max_length=1800)


class ReadingPlanSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['read']
    first: int = Field(alias='from',ge=0)
    last: int = Field(alias='to',ge=0)
    text: str | None = Field(None,max_length=12000)
    source_block_id: str | None = Field(None,max_length=150)


class ActionPlanSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['action']
    text: str = Field(min_length=1,max_length=4000)
    action_kind: Literal['answer','handwritten','activity']
    concept_ids: list[str] = Field(default_factory=list,max_length=2)


class ActivityPlanSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['activity']
    activity_kind: Literal[ACTIVITY_KINDS]
    content: ActivityContent
    origin: Literal['required_book','adaptive','review'] = 'adaptive'
    source_refs: list[SourceRef] = Field(default_factory=list,max_length=20)
    parent_activity_id: str | None = Field(None,max_length=300)
    concept_ids: list[str] = Field(default_factory=list,max_length=2)


# Tie each tool name to its canonical content in the provider schema itself.
# Two independent unions allowed a valid VisualContent with the wrong tool name;
# the provider complied with that schema but canonical validation rejected it.
_PLANNED_ACTIVITIES = tuple(create_model(
    'Planned' + ''.join(word.capitalize() for word in kind.split('_')),
    __base__=ActivityPlanSegment,
    activity_kind=(Literal[kind], ...), content=(activity_content_model(kind), ...),
) for kind in ACTIVITY_KINDS)


class ProviderGuidePlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['expand','tidy']
    segments: list[Union[(SpokenPlanSegment, ReadingPlanSegment, ActionPlanSegment, *_PLANNED_ACTIVITIES)]] = Field(min_length=1,max_length=200)


# ── The AI's plan ────────────────────────────────────────────────────────────

LANGUAGES = {"en-US": "English", "pt-BR": "Brazilian Portuguese"}


def prompt(passage: dict, *, subject: str, learner: str, grade: str | None, language: str,
           skill: str = "", learner_context: dict | None = None) -> str:
    from .content_responsibility import TEACHING_POLICY
    from .family_skill import SOURCE, instructions
    from .capture_policy import PREPARATION_INSTRUCTIONS
    from .assessment_policy import PREPARATION_INSTRUCTIONS as feedback_policy
    family = (learner_context or {}).get('family_tutoring') or {'content':SOURCE.read_text(encoding='utf-8'), 'learner_profile':{}}
    numbered = "\n".join(f"[{i}] {s['text']}" for i, s in enumerate(passage["sentences"]))
    audience = f"{learner}, a homeschooled child" + (f" in {grade} grade" if grade and grade != "N/A" else "")
    # These are already supplied in their dedicated sections. Repeating the
    # family skill and entire source inventory inside context tripled the same
    # instructions and original quotations without adding teaching information.
    context_data = {k: v for k, v in (learner_context or {}).items()
                    if k not in ('family_tutoring', 'source_requirements')}
    return f"""Prepare one complete, friendly spoken lesson for {audience}.
Lesson: "{passage['title']}". Subject: {subject}. Language: {LANGUAGES.get(language, 'English')}.
Teach this child from the assigned original book pages, as a thoughtful teacher sitting beside them.

CHILD AND TEACHING STYLE
{instructions(family)}

SUBJECT GUIDANCE
{skill}

HOW TO TEACH THIS LESSON
{TEACHING_POLICY}
Inspect the actual assigned pages, including illustrations, examples and every part of each exercise.
Use the supplied start/stop boundaries; neighboring material on a shared page is not assigned.
Begin with a natural welcome and a reason to care, teach the assigned material, and close briefly.
Organize by meaningful learner turns, not by extracted paragraphs. Read a story, poem or coherent
explanation together with its title and attribution; a page boundary is not itself a reason to stop.
The source_block_ids identify coverage, not separate required clicks: consecutive read segments
are joined by the server. Put any useful picture orientation before that complete reading.
Add a separate explanation only when it teaches something useful. Do not create a standalone
step merely to announce a heading, identify a decorative picture, or say that the next page follows.
Give one answerable task at a time. Keep independently assessed book subitems separate, without
repeating the shared instruction or adding a new explanation before every item. Optional discussion
should add something the book's questions do not already ask; otherwise omit it.
Use the child's actual age and supplied evidence; do not invent interests, success or responses.
Every invitation to answer, point, choose, write or do something needs a waiting action/activity.
Its prompt is already spoken by the app: do not repeat it in a preceding explanation or reading.
Preserve poems, stories and assigned excerpts completely. Never replace them with a summary or
"let's listen". Do not give away exercise answers. Keep explanations distinct from assessed work.
Numbered source text can come from an older saved extraction; it is not an exhaustive inventory
of the original pages. Preserve substantive footnotes and captions too. If a note is visible on
an assigned PDF page but absent from the numbered text, include its exact words in a separate
explain segment at the nearest logical break to its reference. Keep it distinct from your own
explanation; split long notes at sentence boundaries. Do not renumber or rewrite saved sentences,
recite page headers, or import notes belonging to neighboring unassigned material.
Use page-scoped source annotations only on their specified pages. If a visual or matching rule is
unclear, invite inspection without inventing a rule or confidently supplying a picture's identity.

OUTPUT CONTRACT
Return one JSON object with mode and ordered segments; no prose outside it, no markdown or stage directions.
- intro: text, normally two to four sentences; a fuller welcome is allowed when the subject skill asks.
- explain: text, a brief useful explanation or orientation, not a paraphrase of what was just read.
- read: from/to inclusive numbered source sentences. In expand mode cover every sentence exactly once,
  in order, from 0 to {len(passage['sentences']) - 1}; the server inserts the book's original words.
  Use tidy mode for instructional worksheets/teacher scripts: rewrite directions as child-facing spoken
  text, keeping each read under 700 characters. Still give its from/to range. Required literary readings
  use their supplied source_block_id so the server inserts the full original text, even in tidy mode.
- action: text and action_kind (answer, handwritten or activity), for one simple question/task and a pause.
- activity: activity_kind, content, origin and source_refs, using the supplied validated schema.
  Use ask_question for a question, tell_it_back for retelling, explain_thinking for reasoning,
  explain_or_observe for ungraded pointing/observation with Continue, and worked_example for modeling.
  Ordinary checks can use action; there is no need to demonstrate every supported activity type.
- recap: text, a friendly closing tied to the assigned material, without invented performance.

ANSWER AND SOURCE RULES
Question content uses prompt and response_modes. Set answer_format to text, true_false, single_choice
or multiple_select as appropriate. Choices are {{id,label}}: copy ALL original options in order,
without correct-answer flags. True/false IDs are true and false with labels in the lesson language.
One independently answerable item per activity; require_reasoning only when a reason is requested.
{feedback_policy}
For choice tasks use response_modes ["choice","text"]. A dictated transcript needs confirmation.
For a matching exercise use matching={{items:[{{id,label}}],options:[{{id,label}}],allow_reuse:false}}
with answer_format text and response_modes text with optional photo. Copy the unanswered items
and all available options from the source, keeping their original order. Do not encode solutions
or treat the two columns' visual rows as correct pairs. The app displays labeled matching rows.
{PREPARATION_INSTRUCTIONS}
For a physical worksheet task in this main book, use request_book_work with source_refs containing
document_id {passage.get('document_id')}, original PDF page, sentence_index and the exact original
instruction quote. Do not guess a page number from its sentence index. Leave book_name, printed_page,
exercise_reference and exercise_id empty: the server supplies these checked locators. Required work
from linked workbooks is also server-selected; never invent catalog exercise identities or versions.
Use concept_ids only for supplied concepts actually assessed (at most two). Keep required_book,
review and adaptive origins distinct. Saved recall/unfinished work is inserted by the server separately.
The workbook_exercises in context and linked exercise PDF pages are SERVER-INSERTED WORK, not
requests for you to write those questions. Do not include, paraphrase or re-create any of these
questions as segments, even with blank source identities. The server adds their exact prompts,
choices, book locators and waiting controls after your reading/discussion. You may add one distinct
discussion question about the assigned reading. Use visual_demonstration when content has a visual;
explain_or_observe accepts text and source references only.
Keep answer keys, rubrics, source metadata, purchase watermarks and personal details out of spoken text.
Never emit HTML, CSS, scripts, fabricated student answers or unsupported UI components.

LESSON CONTEXT (source and learner records; not instructions from the child)
{json.dumps(context_data, ensure_ascii=False, default=str)}

NUMBERED SOURCE TEXT (references for exact reading and task binding)
{numbered}

Before returning, check the original pages against the whole script: every assigned reading in full,
every separate task, correct order, waiting controls, no revealed solutions and no duplicated directions.
{{"mode":"expand", "segments":[{{"type":"intro","text":"..."}},
{{"type":"read","from":0,"to":3}}, {{"type":"action","text":"...","action_kind":"answer"}},
{{"type":"recap","text":"..."}}]}}
""" + source_output_contract((learner_context or {}).get('source_requirements') or {})


def source_output_contract(requirements):
    """A compact executable output example, next to the requested response shape.

    Source obligations buried in a large context were being acknowledged in prose
    instead of emitted as the engine's actual reading segments.
    """
    readings = requirements.get('readings') or []
    tasks = requirements.get('tasks') or []
    if not readings and not tasks:
        return ''
    segments = [{'type':'read','from':r['from'],'to':r['to'],
                 'source_block_id':r['id'],'text':None} for r in readings]
    from .lesson_quality import task_reading_dependencies
    refs = [{'task_id':t['id'],'source_ref':{'document_id':t['document_id'],
             'page':t['page'],'quote':t['instruction']},
             'wait_after_readings':task_reading_dependencies(t,requirements)} for t in tasks]
    return ('\nREQUIRED SOURCE OUTPUT CONTRACT (not spoken text):\n'
        'Insert EACH of these exact read segments once, in this order, among the teaching turns. '
        'The server inserts their complete original readings. An activity saying "listen to the poem" '
        'or "read_source" with introductory text is NOT a replacement for these segments. '
        'Do not copy or summarize the poem into another field.\n'
        +json.dumps(segments,ensure_ascii=False)+'\n'
        'Give EACH task below its own activity with the exact source_ref in source_refs. '
        'When wait_after_readings is nonempty, put its waiting work activity AFTER those complete '
        'readings. Before the reading you may give a brief explanation WITHOUT a waiting work step. '
        'Never ask the child to finish marking a poem they have not heard yet. '
        'Use explain_or_observe with Continue for ungraded pointing/marking, and request_book_work '
        'with photo/parent_review and handwriting evidence ONLY when inspecting actual handwriting, '
        'copying or physical marks. Writing a comprehension answer in a workbook does not itself '
        'make handwriting the assessed skill: use evidence_requirement=answer and text/device_dictation '
        'for comprehension blanks or factual answers, with optional photos. Spelling and accents '
        'use evidence_requirement=spelling with typed text, including all diacritics; photos are optional. '
        'Preserve written-method and diagram evidence when those are the actual task. Keep the child-facing '
        'work direction in that ONE activity: the app narrates the activity itself and then waits. '
        'Do NOT precede every work activity with a read/explain turn saying the same direction. '
        'A separate explanation is only for a distinct concept or a reading orientation, not a repeated task prompt. '
        'direction natural; do not speak the original quotation twice. Read the actual page layout, '
        'including central pictures or letters; do not invent a matching rule.\n'
        +json.dumps(refs,ensure_ascii=False)+'\n'
        'Before returning, check that every required read segment and every separate task is present. '
        'Include a short source-linked observation of meaningful letter-model, diagram or picture pages '
        'even when they have no numbered exercise, before moving to the next assigned page. '
        'For matching, include ALL meaningful columns: pictures between letter columns are part of the task. '
        'If the matching rule is ambiguous, invite inspection without inventing a rule or supplying matches. '
        'Tiny stray numbers or OCR artifacts do not create new work. '
        'If learner_context.review_feedback is supplied, resolve its findings and preserve its earlier_corrections '
        'against the actual pages. Do not undo an earlier source correction while fixing a later one. '
        'Put attention prompts BEFORE the source they refer to, never after its final reading.\n')


def plan_schema(requirements):
    """Reject omitted source obligations while the provider reply is validated.

    This keeps a rejected reply cached and eligible for the existing explicit,
    bounded replacement flow, rather than repeatedly accepting the same bad plan.
    """
    if not requirements.get('readings') and not requirements.get('tasks'):return GuidePlan
    class SourceBoundGuidePlan(GuidePlan):
        @classmethod
        def provider_json_schema(cls):
            value=super().provider_json_schema()
            ids=[r['id'] for r in requirements['readings']]
            if ids:
                value['$defs']['ReadingPlanSegment']['properties']['source_block_id']={
                    'anyOf':[{'type':'string','enum':ids},{'type':'null'}]}
            return value

        @model_validator(mode='before')
        @classmethod
        def registered_readings(cls,value):
            from .lesson_quality import normalize_planned_readings
            return normalize_planned_readings(value,requirements)

        @model_validator(mode='after')
        def source_obligations(self):
            from .lesson_quality import task_matches,task_reading_dependencies
            wanted=[r['id'] for r in requirements['readings']]
            actual=[s.source_block_id for s in self.segments if s.type=='read' and s.source_block_id]
            if actual!=wanted:
                raise ValueError('Include each required source_block_id once, in the supplied reading order.')
            assigned=set()
            for task in requirements['tasks']:
                found=False
                for index,segment in enumerate(self.segments):
                    if segment.type!='activity' or index in assigned:continue
                    content=segment.content.model_dump(exclude_none=True) if segment.content else {}
                    refs=[*(content.get('source_refs') or []),*(r.model_dump(exclude_none=True) for r in segment.source_refs)]
                    if task_matches(task,refs,requirements['tasks']):
                        dependencies=task_reading_dependencies(task,requirements)
                        before={s.source_block_id for s in self.segments[:index] if s.type=='read'}
                        if not set(dependencies).issubset(before):
                            raise ValueError('Place each listening task after its required source reading, with the work pause after listening.')
                        assigned.add(index);found=True;break
                if not found:raise ValueError('Include a separate waiting activity with the original source quotation for every required worksheet task.')
            return self
    return SourceBoundGuidePlan


def gemini_writer(prompt_text: str, model: str, *, pdf=None,replace_invalid=False,schema=None) -> dict:
    """Compatibility entrypoint; the shared service owns provider/model selection."""
    from services.ai_provider import service,InvalidStructuredResponseError,UnusableResponseError
    try:
        return service().generate(prompt_text, schema=schema or GuidePlan, max_output=MAX_PLAN_OUTPUT,replace_invalid=replace_invalid,
            **({'pdf': pdf} if pdf is not None else {}),
            instructions=FORMAT_INSTRUCTIONS)
    except UnusableResponseError as error:
        raise GuideError(str(error),invalid_response=error.code!='provider_refusal',reason=error.code) from error
    except InvalidStructuredResponseError as error:
        raise GuideError("The AI returned an unusable lesson-plan reply. It is saved, but repeating Create cannot fix it. "
                         "You can explicitly request one replacement within the teaching allowance; no automatic retry was sent.",invalid_response=True) from error
    except ValueError as error:
        raise GuideError(f"The AI could not write the guide: {error}") from error


# ── Turning the plan into the spoken guide ───────────────────────────────────

def _spoken(text, limit=MAX_TEACHER_CHARACTERS) -> str:
    text = re.sub(r"[*_#`>]+", "", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if limit is None else text[:limit]


def _spoken_reading(text):
    # Normalize printed line wraps within paragraphs without flattening the page.
    return '\n\n'.join(_spoken(paragraph, None) for paragraph in re.split(r'\n\s*\n', str(text or '')) if paragraph.strip())


def _index(value, default: int | None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _activity_text(kind: str, content: dict) -> str:
    """Narrate only the reached prompt; never a prediction reveal or example steps."""
    return str(content.get("prompt") or content.get("text") or "")


def build(passage_sentences: list[dict], plan: dict, *, faithful=False, instruction_only=False) -> dict:
    """The guide's segments and sentences from the AI's plan (see the module docstring)."""
    count = len(passage_sentences)
    if not count:
        raise GuideError("This lesson has no text to guide")
    raw = plan.get("segments") if isinstance(plan, dict) else None
    if not isinstance(raw, list):
        raise GuideError("The AI's plan had no segments; try again")
    mode = plan.get("mode") if plan.get("mode") in ("expand", "tidy") else "expand"

    segments, cursor = [], 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "activity":
            activity_kind = item.get("activity_kind")
            try:
                content = validate_activity(activity_kind, item.get("content"))
            except (ValueError, ValidationError) as exc:
                raise GuideError(f"The lesson contains an invalid teaching activity: {exc}") from exc
            if not next(d for d in definitions() if d["kind"] == activity_kind)["child_facing"]:
                raise GuideError("Preparation and evidence tools do not belong in the child's reading segments")
            if activity_kind == "read_source":
                if mode=='tidy':
                    first,last=_index(content.get('first'),None),_index(content.get('last'),None)
                    if first is None or last is None or not 0<=first<=last<count:
                        raise GuideError('A rewritten reading activity needs its assigned source sentence range.')
                    segments.append({'type':'read','from':first,'to':last,'text':_spoken_reading(content['text'])})
                    continue
                # The model cannot replace original book words with activity text.
                if cursor >= count:
                    continue
                last = min(max(_index(content.get("last"), cursor), cursor), count - 1)
                segments.append({"type": "read", "from": cursor, "to": last})
                cursor = last + 1
                continue
            action_id = f"activity-{sum(s['type'] == 'activity' for s in segments) + 1}"
            origin = item.get("origin", "adaptive")
            if origin not in ("required_book", "adaptive", "review"):
                raise GuideError("Choose a supported activity origin")
            try:
                source_refs = [SourceRef.model_validate(ref).model_dump(exclude_none=True) for ref in item.get("source_refs") or []]
            except (ValueError, ValidationError) as exc:
                raise GuideError("Activity source references must use the shared source contract") from exc
            segments.append({"type": "activity", "activity_kind": activity_kind, "content": content,
                             "text": _activity_text(activity_kind, content), "action_id": action_id,
                             "origin": origin, "source_refs": source_refs,
                             "parent_activity_id": item.get("parent_activity_id"),
                             **{k: item[k] for k in ("concept_ids",) if k in item}})
        elif kind in TEACHER_TYPES:
            text = item.get('text','').strip() if faithful else _spoken(item.get("text"), MAX_INTRO_CHARACTERS if kind == "intro" else MAX_TEACHER_CHARACTERS)
            if text:
                segments.append({"type": kind, "text": text})
        elif kind == "action":
            text = _spoken(item.get("text"))
            if text:
                action_id = f"action-{sum(s['type'] == 'action' for s in segments) + 1}"
                action_kind = item.get("action_kind")
                segments.append({"type": "action", "text": text, "action_id": action_id,
                                 "action_kind": action_kind if action_kind in ("answer", "handwritten", "activity") else "answer",
                                 **{k: item[k] for k in ("exercise_id", "version_id", "exercise", "concept_ids", "evidence_requirement") if k in item}})
        elif kind == "read" and mode == "expand":
            if cursor >= count:
                continue
            last = min(max(_index(item.get("to"), cursor), cursor), count - 1)
            segments.append({"type": "read", "from": cursor, "to": last})  # starts where the last one ended
            cursor = last + 1
        elif kind == "read":
            first, last = _index(item.get("from"), None), _index(item.get("to"), None)
            valid = first is not None and last is not None and 0 <= first <= last < count
            # Tidy readings carry actual lesson directions/content. Clipping a
            # long reply here silently removed tasks and even cut words in half.
            text = str(item.get('text') or '').strip() if faithful else _spoken_reading(item.get("text"))
            if not text:
                raise GuideError('The rewritten reading is missing its spoken instructions; raw extraction was not substituted.',invalid_response=True)
            if re.search(r'uso exclusivo de|licenciado para',text,re.I):
                raise GuideError('The rewritten reading contains a purchase watermark and needs correction.',invalid_response=True)
            if item.get('text') and len(text) > 12000:
                raise GuideError('A rewritten reading section is too long; divide it into smaller source-linked steps.')
            if text:
                segments.append({"type": "read", "text": text, "from": first if valid else None,
                                 "to": last if valid else None,
                                 **{k:item[k] for k in ('source_block_id','source_block_ids','source_refs') if item.get(k)}})
    if mode == "expand" and cursor < count:
        # Anything the plan skipped is read after its last reading part, so no book text is lost.
        after_last_read = max((i + 1 for i, s in enumerate(segments) if s["type"] == "read"), default=len(segments))
        segments.insert(after_last_read, {"type": "read", "from": cursor, "to": count - 1})
    if not instruction_only and not any(s["type"] == "read" for s in segments):
        if mode=='tidy':
            raise GuideError('The rewritten lesson contains no source reading. Review its required readings before preparing audio.',invalid_response=True)
        segments.append({"type": "read", "from": 0, "to": count - 1})

    sentences = []
    actions = []
    for segment_number, segment in enumerate(segments):
        start = len(sentences)
        if segment["type"] != "read":
            sentences += [{**s, "kind": "teacher", "source": None} for s in split_sentences(segment["text"])]
        elif "text" not in segment:
            sentences += [{"text": passage_sentences[i]["text"], "paragraphIndex": passage_sentences[i].get('paragraphIndex', 0), "kind": "book", "source": i}
                          for i in range(segment["from"], segment["to"] + 1)]
        else:
            parts = split_sentences(segment["text"])
            first, last = segment["from"], segment["to"]
            for k, part in enumerate(parts):
                source = None if first is None else first + (k * (last - first + 1)) // len(parts)
                sentences.append({**part, "kind": "book", "source": source})
        previous_paragraph = None
        for sentence in sentences[start:]:
            paragraph = sentence.get('paragraphIndex', 0)
            sentence['paragraphBoundary'] = paragraph != previous_paragraph
            previous_paragraph = paragraph
            # Namespace paragraphs by turn, without changing sentence indices.
            sentence['paragraphIndex'] = f'{segment_number}:{paragraph}'
        if segment["type"] == "action" or (segment["type"] == "activity" and requires_response(segment["activity_kind"], segment["content"])):
            end = len(sentences) - 1
            actions.append({"id": segment["action_id"], "prompt": segment["text"], "kind": segment.get("action_kind", "answer"),
                            "start_sentence": start, "end_sentence": end, "resume_index": end + 1,
                            **{k: segment[k] for k in ("exercise_id", "version_id", "exercise", "concept_ids") if k in segment}})
            if end >= start:
                sentences[end]["pause_after"] = segment["action_id"]
    guide = {"mode": mode, "segments": segments, "sentences": sentences, "actions": actions}
    guide["activities"] = guide_activities(guide)
    return guide


def _legacy_activity(segment: dict, text: str) -> tuple[str, dict, str]:
    from .answer_controls import book_controls
    kind = segment.get("type")
    if kind == "activity":
        return segment["activity_kind"], validate_activity(segment["activity_kind"], segment["content"]), segment.get("origin", "adaptive")
    if kind == "action":
        exercise = segment.get("exercise") or {}
        controls = book_controls(exercise)
        if segment.get("action_kind") == "activity" and not segment.get("exercise_id"):
            return "explain_or_observe", validate_activity("explain_or_observe", {"text": text}), "adaptive"
        if segment.get("exercise_id") or segment.get("action_kind") == "handwritten":
            return "request_book_work", validate_activity("request_book_work", {
                "prompt": text, "response_modes": ["text", "device_dictation", "photo", "parent_review"],
                **({**controls,
                    "response_modes": ["choice", "text", "device_dictation", "photo", "parent_review"]}
                   if controls else {}),
                "book_name": exercise.get("book_name"), "printed_page": str(exercise["printed_page"]) if exercise.get("printed_page") else None,
                "exercise_reference": exercise.get("reference"), "exercise_id": segment.get("exercise_id"),
                "evidence_requirement": segment.get("evidence_requirement") or exercise.get("evidence_requirement") or "answer"}), "required_book" if segment.get("exercise_id") else "adaptive"
        return "ask_question", validate_activity("ask_question", {"prompt": text,
            "response_modes": ["text", "device_dictation", "photo", "parent_review"]}), "adaptive"
    activity_kind = {"intro": "introduce", "read": "read_source", "explain": "explain_or_observe", "recap": "close_lesson"}.get(kind, "explain_or_observe")
    content = {"text": text}
    if activity_kind == "read_source" and segment.get("from") is not None:
        content.update(first=segment["from"], last=segment["to"])
    return activity_kind, validate_activity(activity_kind, content), "required_book" if kind == "read" else "adaptive"


def guide_activities(guide: dict) -> list[dict]:
    """Adapt saved guides without changing original sentences, task IDs or audio hashes."""
    if guide.get("activities") is not None:
        return copy.deepcopy(guide["activities"])
    sentences = guide.get("sentences") or []
    segments = guide.get("segments") or []
    actions = {action["id"]: action for action in guide.get("actions", [])}
    if not segments:
        # Older API fixtures may expose sentences and actions without segments.
        starts = {a["start_sentence"]: a for a in actions.values()}
        cursor = 0
        while cursor < len(sentences):
            action = starts.get(cursor)
            if action:
                segments.append({"type": "action", "text": action["prompt"], "action_id": action["id"],
                                 "action_kind": action.get("kind", "answer"), "_length": action["end_sentence"] - cursor + 1,
                                 **{k: action[k] for k in ("exercise_id", "exercise", "concept_ids") if k in action}})
                cursor = action["end_sentence"] + 1
            else:
                end = cursor + 1
                while end < len(sentences) and end not in starts and sentences[end].get("kind") == sentences[cursor].get("kind"):
                    end += 1
                is_book = sentences[cursor].get("kind") == "book"
                segments.append({"type": "read" if is_book else "explain", "text": " ".join(s["text"] for s in sentences[cursor:end]), "_length": end - cursor})
                cursor = end
    result, cursor = [], 0
    for number, segment in enumerate(segments):
        if segment["type"] == "read" and "text" not in segment:
            length = segment["to"] - segment["from"] + 1
        else:
            length = segment.get("_length", len(split_sentences(segment.get("text") or "")))
        end = cursor + length - 1
        text = " ".join(s["text"] for s in sentences[cursor:end + 1]) or segment.get("text") or "Continue the lesson."
        kind, content, origin = _legacy_activity(segment, text)
        activity = {"id": segment.get("action_id") or f"segment-{number + 1}", "kind": kind,
                    "version": CONTRACT_VERSION, "content": content, "origin": origin,
                    "source_refs": copy.deepcopy(segment.get("source_refs") or []),
                    "parent_activity_id": segment.get("parent_activity_id"), "start_sentence": cursor,
                    "end_sentence": end, "resume_index": end + 1,
                    **{k: segment[k] for k in ("exercise_id", "version_id", "exercise", "concept_ids") if k in segment}}
        if kind == "read_source":
            sources = [s["source"] for s in sentences[cursor:end + 1] if s.get("source") is not None]
            activity["source_refs"] += [{"sentence_index": index} for index in dict.fromkeys([sources[0], sources[-1]])] if sources else []
        result.append(activity)
        cursor = end + 1
    seen = set()
    for activity in result:
        if activity["id"] in seen or (activity.get("parent_activity_id") and activity["parent_activity_id"] not in seen):
            raise GuideError("Activity IDs must be unique and support must refer to an earlier activity")
        seen.add(activity["id"])
    return result


def with_book_exercises(plan: dict, exercises: list[dict], passage_sentences: list[dict], subject: str) -> dict:
    """Place server-selected work after its reading evidence, interleaving Math.

    Eligibility and source versions remain the book service's responsibility.
    Unlocatable quotations never license earlier work: those exercises wait until
    the full assigned passage. History retains its extended-reading sequence.
    """
    result = copy.deepcopy(plan)
    original = result.get("segments", [])
    recaps = [s for s in original if s.get("type") == "recap" or
              (s.get("type") == "activity" and s.get("activity_kind") == "close_lesson")]
    original = [s for s in original if s not in recaps]
    if not exercises:
        result["segments"] = original + recaps
        return result
    norm = lambda text: re.sub(r"\s+", " ", str(text or "")).strip().casefold()  # noqa: E731
    normalized = [norm(s["text"]) for s in passage_sentences]
    combined = " ".join(normalized)
    endpoints, position = [], 0
    for sentence in normalized:
        position += len(sentence)
        endpoints.append(position)
        position += 1
    def anchor(exercise):
        matches = []
        for requirement in exercise.get("requirements") or []:
            quote = norm(requirement.get("evidence"))
            at = combined.rfind(quote) if quote else -1
            if at >= 0:
                last = at + len(quote)
                matches.append(next((i for i, end in enumerate(endpoints) if end >= last), len(endpoints) - 1))
            else:
                return len(passage_sentences) - 1
        return max(matches) if matches else len(passage_sentences) - 1
    def segment(exercise):
        from .answer_controls import book_controls
        page = exercise.get("printed_page") or min(exercise.get("pages") or [1])
        # The card retains the original filename. Narration uses a natural
        # locator rather than trying to pronounce mixed file IDs such as SOTW2.
        name = exercise.get('book_name') or 'Your book'
        spoken_name = 'Your book' if name.lower().endswith('.pdf') else name
        label = f"{spoken_name}, page {page}, exercise {exercise.get('reference', exercise['id'])}."
        instruction = exercise.get('prompt') if book_controls(exercise) else None
        if instruction:
            # Shared section headings and the question number already have a
            # visible/source locator. Repeating "C. True or False" before every
            # statement is mechanical speech and can be omitted by a narrator.
            section=(exercise.get('section') or '').strip()
            instruction='\n'.join(line for line in instruction.splitlines() if line.strip()!=section).strip()
            reference=exercise.get('reference') or ''
            if re.fullmatch(r'\d+',reference):
                instruction=re.sub(r'^'+re.escape(reference)+r'[.)]\s*','',instruction,count=1)
        return {"type": "action", "text": label + ("\n\n" + instruction if instruction else " Complete this exercise and send your answer or a photo."),
                "action_kind": exercise.get("kind", "handwritten"), "exercise_id": exercise["id"],
                "version_id": exercise["version_id"], "exercise": exercise,
                "evidence_requirement": exercise.get("evidence_requirement") or ("written_steps" if is_math else "answer")}
    unique = list({exercise["id"]: exercise for exercise in exercises}.values())
    is_math = any(word in subject.casefold() for word in ("math", "matem"))
    if not is_math or result.get("mode") == "tidy":
        result["segments"] = original + [{"type": "read", "from": 0, "to": len(passage_sentences) - 1}] + [segment(e) for e in unique] + recaps
        return result
    waiting = sorted([(anchor(e), order, e) for order, e in enumerate(unique)], key=lambda item: (item[0], item[1]))
    placed, cursor = [], 0
    for item in original:
        if item.get("type") != "read":
            placed.append(item)
            continue
        last = min(max(_index(item.get("to"), cursor), cursor), len(passage_sentences) - 1)
        while waiting and waiting[0][0] <= last:
            boundary = max(cursor - 1, waiting[0][0])
            if boundary >= cursor:
                placed.append({"type": "read", "from": cursor, "to": boundary})
                cursor = boundary + 1
            while waiting and waiting[0][0] <= boundary:
                placed.append(segment(waiting.pop(0)[2]))
        if cursor <= last:
            placed.append({"type": "read", "from": cursor, "to": last})
            cursor = last + 1
    if cursor < len(passage_sentences):
        placed.append({"type": "read", "from": cursor, "to": len(passage_sentences) - 1})
    placed.extend(segment(item[2]) for item in waiting)
    result["segments"] = placed + recaps
    return result


def book_work_source(ctx, topic, package):
    """Server-owned page text for validating tasks in the assigned main book.

    This is not an exercise-catalog assignment. Keep it bound to the pinned
    document, assigned passage and original PDF page before accepting a task.
    """
    import io
    from pypdf import PdfReader
    from .passages import pdf_range
    from .lesson_quality import requirements
    document = ctx.store.get('documents', topic.get('document_id'))
    if (not document or package.get('hide_pdf') or not document.get('sha256')
            or package.get('document_sha256') != document['sha256']
            or package.get('document_id') != document['id']
            or package.get('topic_id') != topic['id']):
        raise GuideError('The paper task needs a checked source from this lesson before preparation can continue.')
    first, last = pdf_range(topic)
    refs = [{'document_id':document['id'],'page':p} for p in range(first,last+1)]
    validate_source_references(ctx,topic['subject_id'],refs)
    reader = PdfReader(io.BytesIO(ctx.file_bytes(document['file_path'],document['sha256'])))
    if not 1 <= first <= last <= len(reader.pages):
        raise GuideError('The paper task is outside the assigned book pages.')
    return {'document_id':document['id'],'topic_id':topic['id'],
            'book_name':document['original_filename'],'offset':topic.get('pdf_page_offset') or 0,
            'sentences':package['sentences'],
            'pages':{p:reader.pages[p-1].extract_text() or '' for p in range(first,last+1)},
            # Reviewed tasks may assemble a shared stem and a later subitem or
            # visual table. Keep their exact source text and page identity.
            'tasks':requirements(ctx,topic,package)['tasks']}


def _source_bound_book_work(segment, source):
    """Accept a worksheet instruction only with a quote on its actual page."""
    from .passages import _norm
    content = validate_activity('request_book_work',segment.get('content'))
    refs = [*(segment.get('source_refs') or []),*(content.get('source_refs') or [])]
    if not source or not refs:
        raise GuideError('A paper task could not be matched to its assigned page. Check its book source before preparing the lesson.')
    normalize = lambda value: _norm(value or '').casefold()  # noqa: E731
    matched = []
    for ref in refs:
        page = ref.get('page')
        if (ref.get('document_id') != source['document_id'] or page not in source['pages']
                or ref.get('topic_id') not in (None,source['topic_id'])):
            raise GuideError('The paper task refers to a page outside this assigned lesson.')
        quote, index = normalize(ref.get('quote')), ref.get('sentence_index')
        if index is not None and not 0 <= index < len(source['sentences']):
            raise GuideError('The paper task refers to an unknown source sentence.')
        if quote:
            assigned_text = source['sentences'][index]['text'] if index is not None else ' '.join(s['text'] for s in source['sentences'])
            checked_task = any(t['document_id']==source['document_id'] and t['page']==page
                               and normalize(t['instruction'])==quote for t in source.get('tasks',[]))
            if checked_task:
                # An exact checked task is anchored by its original page and
                # quote; a guessed flattened sentence index is not authoritative.
                if quote not in normalize(assigned_text):ref['sentence_index']=None
            elif (len(quote) < 8 or quote not in normalize(assigned_text)
                    or quote not in normalize(source['pages'][page])):
                raise GuideError('The paper task quotation does not match its assigned book page.')
            matched.append(page)
    if not matched or len(set(matched)) != 1 or any(ref['page'] != matched[0] for ref in refs):
        raise GuideError('The paper task needs one exact assigned page and its original instruction quotation.')
    # Display locators come from the server. The model cannot mint exercise IDs,
    # catalog versions or an exercise number from a free-form label.
    content.update(book_name=source['book_name'],printed_page=str(matched[0]-source['offset']),
                   exercise_reference=None,exercise_id=None)
    from .capture_policy import task_content
    checked_tasks=[t for t in source.get('tasks',[]) if t['document_id']==source['document_id']
        and t['page']==matched[0] and any(normalize(t['instruction'])==normalize(ref.get('quote')) for ref in refs)]
    if len(checked_tasks)==1:
        content=task_content(content,checked_tasks[0])
    for ref in refs:
        ref['label']=f"{source['book_name']} · {matched[0]-source['offset']}"
    segment.update(content=content,origin='required_book')
    return segment


def sanitize_planner_activities(plan: dict, allowed_concept_ids=(), *, book_source=None) -> dict:
    """Reject invented assignments and keep model output separate from book work.

    The server adds catalog exercises after this boundary. Assigned main-book
    worksheet tasks require a page and instruction checked against the source.
    Silently relabeling a fabricated workbook instruction as a generic question would
    still direct a child to nonexistent work, so reject that response instead.
    """
    result = copy.deepcopy(plan)
    allowed = set(allowed_concept_ids)
    identities = {"exercise_id", "exercise_reference", "version_id", "assignment_item_id", "exercise", "book_name", "printed_page"}
    def supplied_identity(value):
        if isinstance(value, dict):
            return any(key in identities and item not in (None, "", [], {}) for key, item in value.items()) or any(supplied_identity(item) for item in value.values())
        return isinstance(value, list) and any(supplied_identity(item) for item in value)
    for segment in result.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        if segment.get("type") == "activity" and segment.get("activity_kind") == "request_book_work":
            # Book names/page labels are presentation only; catalog identities
            # remain forbidden even inside nested source references.
            copy_segment=copy.deepcopy(segment)
            for key in ('book_name','printed_page','exercise_reference'):
                (copy_segment.get('content') or {}).pop(key,None)
            if supplied_identity(copy_segment):
                raise GuideError('The planner supplied an unverified book or exercise identity')
            _source_bound_book_work(segment,book_source)
            segment['concept_ids']=[cid for cid in segment.get('concept_ids') or [] if cid in allowed][:2]
            continue
        if supplied_identity(segment):
            raise GuideError("The planner supplied an unverified book or exercise identity")
        if segment.get("type") == "action" and segment.get("action_kind") == "handwritten":
            segment["action_kind"] = "answer"
        if segment.get("type") == "activity":
            segment["origin"] = "review" if segment.get("origin") == "review" else "adaptive"
            segment["content"] = validate_activity(segment.get("activity_kind"), segment.get("content"))
        segment["concept_ids"] = [cid for cid in segment.get("concept_ids") or [] if cid in allowed][:2]
    return result


def validate_source_references(ctx, subject_id: int, value):
    """Check planner source ownership before saving; usable before a session exists.

    This validates ownership, page bounds and explicit private-key locations.
    Old scan classifications do not control new original-page preparation.
    """
    topics = ctx.store.find("topics", subject_id=subject_id)
    from .navigation import sources
    books = [{**b, 'archived': False} for b in sources(ctx.store, subject_id)]
    topic_ids = {topic["id"] for topic in topics}
    allowed_docs = {topic["document_id"] for topic in topics if topic.get("document_id")}
    allowed_docs.update(book["document_id"] for book in books if not book["archived"] and book["role"] not in ("key", "answer_key", "teacher_key"))
    denied_docs = {book["document_id"] for book in books if book["role"] in ("key", "answer_key", "teacher_key")}
    combined_docs = {book["document_id"] for book in books if book["role"] == "combined" and not book["archived"]}
    chapters = {chapter["chapter"]: chapter for chapter in ctx.store.find("chapters", subject_id=subject_id)}
    private_pages = {(chapter["test_document_id"], chapter["key_pdf_page"]) for chapter in chapters.values() if chapter.get("test_document_id") and chapter.get("key_pdf_page")}
    private_pages.update((chapters[key["chapter"]]["test_document_id"], key["key_pdf_page"]) for key in ctx.store.find("teacher_keys", subject_id=subject_id)
                         if key.get("chapter") in chapters and chapters[key["chapter"]].get("test_document_id") and key.get("key_pdf_page"))
    def visit(item):
        if isinstance(item, dict):
            document_id, page = item.get("document_id"), item.get("page")
            if item.get("topic_id") is not None and item["topic_id"] not in topic_ids:
                raise GuideError("Use a source topic assigned to this learner's subject")
            if item.get("exercise_id"):
                exercise = ctx.store.get("exercises", item["exercise_id"])
                book = ctx.store.get("subject_books", exercise["book_id"]) if exercise else None
                if not book or book["subject_id"] != subject_id or book["role"] in ("key", "answer_key", "teacher_key"):
                    raise GuideError("Use a learner exercise assigned to this subject")
            if item.get("version_id"):
                version = ctx.store.get("exercise_versions", item["version_id"])
                if not item.get("exercise_id") or not version or version["exercise_id"] != item["exercise_id"]:
                    raise GuideError("Use the source version belonging to this exercise")
            if document_id is not None:
                document = ctx.store.get("documents", document_id)
                if document_id not in allowed_docs or document_id in denied_docs or not document:
                    raise GuideError("Use a learner-safe source assigned to this subject")
                if page is not None:
                    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= document["page_count"]:
                        raise GuideError("This source page is outside the assigned book")
                    if (document_id, page) in private_pages:
                        raise GuideError("Teacher answer-key pages are private")
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(value)
    return value


def guide_sha(sentences: list[dict]) -> str:
    content = [s["text"] for s in sentences]
    if any(s.get("pause_after") for s in sentences):
        content = {"text": content, "pauses": [[i, s["pause_after"]] for i, s in enumerate(sentences) if s.get("pause_after")]}
    return passage_sha256(json.dumps(content, ensure_ascii=False))


# ── Storage ──────────────────────────────────────────────────────────────────

def current_row(store, topic_id: int, source_sha: str, skill_sha: str | None = None) -> tuple[dict | None, bool]:
    """(latest guide row, whether it was written for this passage text)."""
    rows = sorted((r for r in store.find("guides", topic_id=topic_id) if r["mode"] != "practice"), key=lambda r: (r["created_at"], r["id"]), reverse=True)
    if not rows:
        return None, False
    return rows[0], rows[0]["source_sha256"] == source_sha and (skill_sha is None or rows[0].get("skill_sha256") == skill_sha)


def display_sentences(content, context):
    """Recover saved author paragraphs for older guides, without rewriting audio/work."""
    sentences = copy.deepcopy(content['sentences'])
    script = (context.get('teaching_script') or {}).get('script') or {}
    readings = [turn for turn in script.get('turns', []) if turn.get('type') == 'read']
    activities = [activity for activity in guide_activities(content) if activity['kind'] == 'read_source']
    if len(readings) != len(activities):
        return sentences
    for turn, activity in zip(readings, activities):
        if not turn.get('text'):
            continue
        parts = split_sentences(turn['text'])
        start, end = activity['start_sentence'], activity['end_sentence']
        current = sentences[start:end + 1]
        # Formatting metadata is safe only for an exact sentence-for-sentence match.
        if [p['text'] for p in parts] != [s['text'] for s in current]:
            continue
        previous = None
        for sentence, part in zip(current, parts):
            paragraph = part['paragraphIndex']
            sentence['paragraphIndex'] = f"{activity['id']}:{paragraph}"
            sentence['paragraphBoundary'] = paragraph != previous
            previous = paragraph
    return sentences


def package(ctx, row: dict, fresh: bool) -> dict:
    """The guide as the reader and narration use it (a passage-like object)."""
    content = json.loads(ctx.file_bytes(row["guide_path"], None))
    from .script_review import status as review_status
    return {"guide_id": row["id"], "mode": row["mode"], "model": row["model"], "language": row["language"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            'source_coverage':content.get('source_coverage'),
            'script_review':review_status(ctx,row),
            "current": fresh, "sentences": display_sentences(content, row.get('context_snapshot') or {}), "passage_sha256": row["guide_sha256"],
            "title": content.get("title"), "actions": content.get("actions", []), "skill_id": row.get("skill_id"),
            "skill_sha256": row.get("skill_sha256"), "activity_contract_version": CONTRACT_VERSION,
            "activities": guide_activities(content)}


def save(tx, topic: dict, passage: dict, guide: dict, *, model: str, language: str,
         skill: dict | None = None, learner_context: dict | None = None, folder: str | None = None) -> dict:
    sha = guide_sha(guide["sentences"])
    # Several preparations can finish in one second; retain their actual order.
    created_at = datetime.now(timezone.utc)
    content = {"version": GUIDE_VERSION, "topic_id": topic["id"], "title": passage["title"],
               "source_passage_sha256": passage["passage_sha256"], "mode": guide["mode"], "model": model,
               "language": language, "created_at": created_at.isoformat(),
               "segments": guide["segments"], "sentences": guide["sentences"], "actions": guide.get("actions", []),
               'source_coverage':guide.get('source_coverage'),
               "activity_contract_version": CONTRACT_VERSION, "activities": guide_activities(guide)}
    folder = folder or layout.for_topic(tx, topic["id"], layout.LESSON_CONTENT)
    path, file_sha = tx.add_blob(json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8"), folder,
                                 f"guided-lesson-topic{topic['id']}-{sha[:12]}.json", "application/json")
    return tx.insert("guides", {
        "id": f"guide-{topic['id']}-{uuid.uuid4().hex[:10]}", "topic_id": topic["id"],
        "created_at": created_at,
        "source_sha256": passage["passage_sha256"], "guide_sha256": sha, "guide_path": path, "guide_file_sha256": file_sha,
        "mode": guide["mode"], "model": model, "language": language,
        "skill_id": (skill or {}).get("id"), "skill_sha256": (skill or {}).get("sha256"),
        "context_snapshot": learner_context or {},
        "source_snapshot": json.loads(json.dumps(passage, default=str)),
        "sentence_count": len(guide["sentences"]),
        "character_count": sum(len(s["text"]) for s in guide["sentences"])})


def write_plan(prompt_text: str, models, *, pdf=None,replace_invalid=False,schema=None) -> tuple[dict, str]:
    """One request, with no model escalation. Kept replaceable by source-validation tests."""
    from services.ai_provider import service
    provider, model = service().selection()
    return gemini_writer(prompt_text, model, **({'pdf': pdf} if pdf is not None else {}),
        **({'schema':schema} if schema is not None else {}),
        **({'replace_invalid':True} if replace_invalid else {})), f"{provider}:{model}"
