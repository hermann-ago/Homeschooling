"""Provider-independent teaching tools and their allowlisted presentation contracts.

The planner and live tutor use the same definitions. The engine, rather than a
model response, owns identity, evidence, transitions and rendering. Content is
plain text and structured data; no HTML, styling or executable code is accepted.
"""
from __future__ import annotations

import copy
import re
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = 1
ResponseMode = Literal["text", "device_dictation", "choice", "photo", "written_steps", "parent_review"]
AnswerFormat = Literal["text", "true_false", "single_choice", "multiple_select"]
EvidenceRequirement = Literal["answer", "reasoning", "written_steps", "spelling", "handwriting", "diagram"]
ACTIVITY_KINDS = (
    "review_progress", "prepare_lesson", "introduce", "read_source", "explain_or_observe",
    "ask_question", "request_book_work", "capture_and_confirm", "hint_or_follow_up",
    "give_feedback", "record_learning_evidence", "close_lesson", "worked_example",
    "explain_thinking", "check_prerequisite", "visual_demonstration", "take_break_and_return",
    "tell_it_back", "compare_and_connect", "predict_then_check", "find_and_fix_mistake",
    "apply_somewhere_new", "recall_later",
)


def _plain(value):
    if isinstance(value, str) and (re.search(r"</?[A-Za-z][^>]*>", value) or
                                  re.search(r"(?:javascript|vbscript)\s*:|data\s*:\s*text/html", value, re.I)):
        raise ValueError("Activities accept plain text, not HTML or executable UI content")
    if isinstance(value, dict):
        for item in value.values():
            _plain(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _plain(item)


class Content(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def plain_content(self):
        _plain(self.model_dump())
        return self


class SourceRef(Content):
    document_id: int | None = Field(None, ge=1)
    topic_id: int | None = Field(None, ge=1)
    page: int | None = Field(None, ge=1)
    sentence_index: int | None = Field(None, ge=0)
    quote: str | None = Field(None, max_length=4000)
    label: str | None = Field(None, max_length=300)
    exercise_id: str | None = Field(None, max_length=300)
    version_id: str | None = Field(None, max_length=300)


class TextContent(Content):
    text: str = Field(min_length=1, max_length=12000)
    title: str | None = Field(None, max_length=200)
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=20)
    # Hands-on book work (lines, colouring, tracing): a grown-up looks and confirms.
    parent_check: bool = False


class ReviewContent(Content):
    topic_id: int | None = Field(None, ge=1)
    concept_ids: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(10, ge=1, le=50)


class PreparationContent(Content):
    topic_id: int | None = Field(None, ge=1)
    include_reviews: bool = True
    activity_kinds: list[str] = Field(default_factory=list, max_length=23)

    @model_validator(mode="after")
    def supported_kinds(self):
        if any(kind not in ACTIVITY_KINDS for kind in self.activity_kinds):
            raise ValueError("Choose registered activities for lesson preparation")
        return self


class ReadContent(TextContent):
    text: str = Field(min_length=1, max_length=200000)
    first: int | None = Field(None, ge=0)
    last: int | None = Field(None, ge=0)
    document_id: int | None = Field(None, ge=1)
    page: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def ordered_range(self):
        if (self.first is None) != (self.last is None) or (self.first is not None and self.last < self.first):
            raise ValueError("Reading requires an ordered, complete source sentence range")
        return self


class Choice(Content):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=1000)


class MatchingContent(Content):
    items:list[Choice]=Field(min_length=2,max_length=12)
    options:list[Choice]=Field(min_length=2,max_length=12)
    allow_reuse:bool=False

    @model_validator(mode='after')
    def unique_labels(self):
        for values in (self.items,self.options):
            if len({v.id for v in values})!=len(values):raise ValueError('Matching IDs must be unique within each column')
        if not self.allow_reuse and len(self.options)<len(self.items):raise ValueError('Matching needs an option for every item')
        return self


class QuestionContent(Content):
    prompt: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(None, max_length=200)
    response_modes: list[ResponseMode] = Field(default_factory=lambda: ["text"], min_length=1, max_length=6)
    choices: list[Choice] = Field(default_factory=list, max_length=12)
    answer_format: AnswerFormat = "text"
    evidence_requirement: EvidenceRequirement = "answer"
    require_reasoning: bool = False
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=20)
    matching:MatchingContent | None=None
    # One typed answer box per printed problem (labels only; keys stay private).
    blanks: list[Choice] | None = Field(None, min_length=1, max_length=30)

    @model_validator(mode="before")
    @classmethod
    def answer_controls(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        if "answer_format" not in value and value.get("choices"):
            value["answer_format"] = "single_choice"
        if value.get("answer_format") == "true_false" and not value.get("choices"):
            value["choices"] = [{"id": "true", "label": "True"}, {"id": "false", "label": "False"}]
        if value.get("answer_format", "text") != "text" and "response_modes" not in value:
            value["response_modes"] = ["choice", "text"]
        return value

    @field_validator("response_modes", mode="before")
    @classmethod
    def legacy_dictation_mode(cls, value):
        return ["device_dictation" if mode == "audio" else mode for mode in value] if isinstance(value, list) else value

    @model_validator(mode="after")
    def valid_choices(self):
        if self.matching and (self.answer_format!='text' or 'text' not in self.response_modes):
            raise ValueError('Matching uses structured typed answers and a text response mode')
        if self.blanks is not None:
            if self.matching or self.answer_format != 'text' or 'text' not in self.response_modes:
                raise ValueError('Blanks use structured typed answers and a text response mode')
            if len({b.id for b in self.blanks}) != len(self.blanks):
                raise ValueError('Blank IDs must be unique')
        if len(set(self.response_modes)) != len(self.response_modes):
            raise ValueError("Response modes must be unique")
        if len({c.id for c in self.choices}) != len(self.choices):
            raise ValueError("Choice IDs must be unique")
        if "choice" in self.response_modes and len(self.choices) < 2:
            raise ValueError("A matching on-screen choice needs at least two choices")
        if self.choices and "choice" not in self.response_modes:
            raise ValueError("Choices require the choice response mode")
        if self.answer_format != "text" and "choice" not in self.response_modes:
            raise ValueError("A choice answer format requires the choice response mode")
        if self.answer_format == "text" and self.choices:
            raise ValueError("Text answers cannot define choice controls")
        if self.answer_format == "true_false" and {c.id for c in self.choices} != {"true", "false"}:
            raise ValueError("True/false uses exactly the true and false choice IDs")
        return self


class BookWorkContent(QuestionContent):
    book_name: str | None = Field(None, max_length=300)
    printed_page: str | None = Field(None, max_length=80)
    exercise_reference: str | None = Field(None, max_length=300)
    exercise_id: str | None = Field(None, max_length=300)
    work_location: Literal["physical_book"] = "physical_book"


class CaptureContent(QuestionContent):
    confirmation_required: Literal[True] = True


class HintContent(TextContent):
    level: Literal["second_look", "small_clue", "source_pointer", "explanation", "follow_up"] = "small_clue"
    follow_up_prompt: str | None = Field(None, max_length=4000)


class FeedbackContent(TextContent):
    assessment_status: Literal["unassessed", "assessed", "parent_review"] = "unassessed"
    result: Literal["Correct", "Partly correct", "Not yet", "With help"] | None = None


class EvidenceContent(Content):
    submission_id: str = Field(min_length=1, max_length=300)
    note: str | None = Field(None, max_length=2000)


class CloseContent(TextContent):
    unfinished: list[str] = Field(default_factory=list, max_length=30)


class ExampleStep(Content):
    text: str = Field(min_length=1, max_length=4000)
    label: str | None = Field(None, max_length=120)


class WorkedExampleContent(TextContent):
    steps: list[ExampleStep] = Field(min_length=1, max_length=20)
    practice_prompt: str | None = Field(None, max_length=4000)
    support_level: Literal["modeled", "guided", "faded"] = "modeled"
    response_modes: list[ResponseMode] = Field(default_factory=lambda: ["text"], min_length=1, max_length=6)
    choices: list[Choice] = Field(default_factory=list, max_length=12)
    answer_format: AnswerFormat = "text"
    evidence_requirement: EvidenceRequirement = "reasoning"

    @model_validator(mode="before")
    @classmethod
    def answer_controls(cls, value):
        return QuestionContent.answer_controls(value)

    @model_validator(mode="after")
    def practice_choices(self):
        question = QuestionContent(prompt=self.practice_prompt or "Continue", response_modes=self.response_modes,
                        choices=self.choices, answer_format=self.answer_format,
                        evidence_requirement=self.evidence_requirement)
        self.answer_format = question.answer_format
        return self


class ExplainThinkingContent(QuestionContent):
    evidence_requirement: EvidenceRequirement = "reasoning"
    require_reasoning: bool = True


class PrerequisiteContent(QuestionContent):
    prerequisite: str = Field(min_length=1, max_length=500)


class NumberPoint(Content):
    value: float = Field(ge=-1_000_000_000, le=1_000_000_000)
    label: str = Field(min_length=1, max_length=200)


class TimelineEvent(Content):
    label: str = Field(min_length=1, max_length=500)
    date: str | None = Field(None, max_length=120)


class DiagramNode(Content):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=500)


class DiagramEdge(Content):
    from_id: str = Field(min_length=1, max_length=100)
    to_id: str = Field(min_length=1, max_length=100)
    label: str | None = Field(None, max_length=200)


class VisualAid(Content):
    type: Literal["book_illustration", "number_line", "timeline", "diagram"]
    caption: str | None = Field(None, max_length=1000)
    document_id: int | None = Field(None, ge=1)
    page: int | None = Field(None, ge=1)
    minimum: float | None = Field(None, ge=-1_000_000_000, le=1_000_000_000)
    maximum: float | None = Field(None, ge=-1_000_000_000, le=1_000_000_000)
    step: float | None = Field(None, gt=0)
    points: list[NumberPoint] = Field(default_factory=list, max_length=30)
    events: list[TimelineEvent] = Field(default_factory=list, max_length=30)
    nodes: list[DiagramNode] = Field(default_factory=list, max_length=30)
    edges: list[DiagramEdge] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid_visual(self):
        if self.type == "book_illustration" and not (self.document_id and self.page):
            raise ValueError("A book illustration needs its document and page")
        if self.type == "number_line":
            if self.minimum is None or self.maximum is None or self.maximum <= self.minimum:
                raise ValueError("A number line needs increasing minimum and maximum values")
            if any(not self.minimum <= point.value <= self.maximum for point in self.points):
                raise ValueError("Number-line points must be inside the displayed range")
            if self.step is None:
                self.step = (self.maximum - self.minimum) / 10
            if self.step and (self.maximum - self.minimum) / self.step > 200:
                raise ValueError("A number line may show at most 200 intervals")
        if self.type == "timeline" and not self.events:
            raise ValueError("A timeline needs at least one event")
        if self.type == "diagram":
            ids = {node.id for node in self.nodes}
            if not ids or len(ids) != len(self.nodes) or any(edge.from_id not in ids or edge.to_id not in ids for edge in self.edges):
                raise ValueError("A diagram needs unique nodes and edges referring to those nodes")
        return self


class VisualContent(TextContent):
    visual: VisualAid


class BreakContent(TextContent):
    return_message: str | None = Field(None, max_length=1000)
    suggested_minutes: int | None = Field(None, ge=1, le=60)


class ComparisonItem(Content):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=10)


class CompareContent(QuestionContent):
    items: list[ComparisonItem] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def distinct_items(self):
        if self.items[0].id == self.items[1].id:
            raise ValueError("Comparison items need distinct IDs")
        return self


class RevealContent(TextContent):
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=10)


class PredictionContent(QuestionContent):
    reveal: RevealContent
    reflection_prompt: str = Field(min_length=1, max_length=4000)


class MistakeContent(QuestionContent):
    puzzle_label: Literal["Find the mistake puzzle"] = "Find the mistake puzzle"
    example: str = Field(min_length=1, max_length=4000)
    require_reasoning: Literal[True] = True


class ApplyContent(QuestionContent):
    scenario: str = Field(min_length=1, max_length=4000)


class ActivityResult(Content):
    activity_id: str | None = None
    interaction_id: str | None = None
    status: str
    revision: int
    event_cursor: int
    receipt_id: str
    waiting_for: str | None = None
    submission_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    next_activity_id: str | None = None
    error: str | None = None


# kind, content model, reusable renderer, completion rule, child-facing
_REGISTRY = (
    ("review_progress", ReviewContent, None, "structured_result", False),
    ("prepare_lesson", PreparationContent, None, "structured_result", False),
    ("introduce", TextContent, "introduction", "acknowledge", True),
    ("read_source", ReadContent, "source_reading", "continue_after_narration", True),
    ("explain_or_observe", TextContent, "explanation", "acknowledge", True),
    ("ask_question", QuestionContent, "question", "confirmed_response", True),
    ("request_book_work", BookWorkContent, "book_work", "paper_then_confirmed_response", True),
    ("capture_and_confirm", CaptureContent, "response_capture", "confirmed_response", True),
    ("hint_or_follow_up", HintContent, "hint", "return_to_origin", True),
    ("give_feedback", FeedbackContent, "feedback", "acknowledge", True),
    ("record_learning_evidence", EvidenceContent, None, "structured_result", False),
    ("close_lesson", CloseContent, "lesson_close", "explicit_finish", True),
    ("worked_example", WorkedExampleContent, "worked_example", "stages_then_optional_practice", True),
    ("explain_thinking", ExplainThinkingContent, "question", "confirmed_response", True),
    ("check_prerequisite", PrerequisiteContent, "question", "confirmed_response", True),
    ("visual_demonstration", VisualContent, "visual_aid", "acknowledge", True),
    ("take_break_and_return", BreakContent, "break", "explicit_return", True),
    ("tell_it_back", QuestionContent, "response_card", "confirmed_response", True),
    ("compare_and_connect", CompareContent, "comparison", "confirmed_response", True),
    ("predict_then_check", PredictionContent, "prediction", "predict_reveal_reflect", True),
    ("find_and_fix_mistake", MistakeContent, "editable_example", "confirmed_response", True),
    ("apply_somewhere_new", ApplyContent, "question", "confirmed_response", True),
    ("recall_later", QuestionContent, "question", "independent_response_before_help", True),
)
_MODELS = {kind: model for kind, model, *_ in _REGISTRY}
# A real union keeps provider JSON schemas closed; a generic dict would lose the
# allowlist when a provider converts objects to additionalProperties: false.
ActivityContent = Union[tuple(dict.fromkeys(_MODELS.values()))]


def activity_content_model(kind: str) -> type[Content]:
    """Canonical content type for schema consumers as well as validation."""
    if kind not in _MODELS:
        raise ValueError(f"Unsupported teaching activity: {kind}")
    return _MODELS[kind]


def parse_activity(kind: str, content: dict) -> Content:
    """Resolve a provider union to the concrete registered activity model."""
    model = activity_content_model(kind)
    if not isinstance(content, dict):
        raise ValueError("Activity content must be a structured object")
    return model.model_validate(content)


def validate_activity(kind: str, content: dict) -> dict:
    """Validate one registered tool's content and normalize nullable defaults."""
    return parse_activity(kind,content).model_dump(mode="json", exclude_none=True)


def definitions() -> list[dict]:
    """JSON-serializable shared planner/live-tutor tool and renderer catalog."""
    return [{"type": kind, "kind": kind, "title": kind.replace("_", " ").capitalize(),
             "version": CONTRACT_VERSION, "renderer": renderer, "child_facing": visible,
             "input_schema": model.model_json_schema(), "result_schema": ActivityResult.model_json_schema(),
             "completion": completion, "waiting": completion != "structured_result",
             "narration": "pause_before_response" if issubclass(model, QuestionContent) else "controlled_by_engine",
             "capture": "confirmed_submission" if issubclass(model, QuestionContent) else "none",
             "evidence": "observed_response_only", "persistence": "session_activity_and_append_only_events"}
            for kind, model, renderer, completion, visible in _REGISTRY]


def activity_definition(kind: str) -> dict:
    try:
        return copy.deepcopy(next(item for item in definitions() if item["kind"] == kind))
    except StopIteration as exc:
        raise ValueError(f"Unsupported teaching activity: {kind}") from exc


def requires_response(kind: str, content: dict) -> bool:
    if kind == "worked_example":
        return bool(content.get("practice_prompt"))
    if kind == "hint_or_follow_up":
        return bool(content.get("follow_up_prompt"))
    return kind in _MODELS and issubclass(_MODELS[kind], QuestionContent)


class ActivityProposal(Content):
    """The live tutor can request the same structured tools as the planner."""
    kind: Literal[ACTIVITY_KINDS]
    content: ActivityContent

    @model_validator(mode="after")
    def valid_tool_content(self):
        self.content=parse_activity(self.kind, self.content.model_dump(exclude_none=True))
        if self.kind in ("review_progress", "prepare_lesson", "record_learning_evidence", "close_lesson", "introduce"):
            raise ValueError("The live tutor may add teaching support; the engine owns preparation and lesson closure")
        return self
