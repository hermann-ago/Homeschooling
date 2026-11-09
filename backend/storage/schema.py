"""Tables of the Homeschooling database (SQLite on the home server).

Every table starts with ``id``, ``revision`` and ``updated_at``. Values are held
in memory as Python types. Files (books, handwriting, audio, photos) live in the
synced Google Drive folder; tables store their paths relative to that folder.
``subjects.folder`` is the subject's Kid → Grade → Subject folder (see ``layout``).
``tab`` is the readable name used for the daily Excel copy.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

SCHEMA_VERSION = 2
SYSTEM_COLUMNS = ("id", "revision", "updated_at")


@dataclass(frozen=True)
class ForeignKey:
    column: str
    table: str
    on_delete: str = "cascade"  # cascade | set_null | restrict
    nullable: bool = False


@dataclass(frozen=True)
class Table:
    name: str
    tab: str
    columns: dict[str, str]
    id_type: str = "int"  # int ids are allocated locally; str ids come from callers
    foreign_keys: tuple[ForeignKey, ...] = ()
    required: tuple[str, ...] = ()
    teacher_only: bool = False
    unique: tuple[tuple[str, ...], ...] = ()
    defaults: dict = field(default_factory=dict)

    @property
    def header(self) -> list[str]:
        return [*SYSTEM_COLUMNS, *self.columns]


def _t(name, tab, columns, **kwargs) -> Table:
    return Table(name=name, tab=tab, columns=columns, **kwargs)


TABLES: dict[str, Table] = {t.name: t for t in [
    _t('topic_narrators', 'Lesson Narrators', {'topic_id':'int','voice':'str','voice_name':'str'}, id_type='str',
       required=('topic_id','voice'), unique=(('topic_id',),), foreign_keys=(ForeignKey('topic_id','topics'),)),
    _t('book_navigation', 'Book Chapter Maps', {
        'document_sha256':'str','data':'json','file_path':'str','created_at':'datetime',
    }, id_type='str', required=('document_sha256','data')),
    _t('lesson_page_selections', 'Lesson Source Pages', {
        'topic_id':'int','sources':'json',
    }, id_type='str', required=('topic_id','sources'), unique=(('topic_id',),),
        foreign_keys=(ForeignKey('topic_id','topics'),), teacher_only=True),
    # Which items on exercise pages shared by several lessons belong to which
    # lesson (tutoring/exercise_assignment.py); id names the page set and lessons.
    _t('exercise_assignments', 'Exercise Assignments', {
        'subject_id':'int','data':'json',
    }, id_type='str', required=('subject_id','data'), foreign_keys=(ForeignKey('subject_id','subjects'),), teacher_only=True),
    _t('source_annotations', 'Source Teaching Notes', {
        'key':'str','version':'int','document_sha256':'str','first_page':'int','last_page':'int',
        'title':'str','teaching_note':'str','assessment_note':'str','references':'json','active':'bool',
        'file_path':'str','created_at':'datetime',
    }, id_type='str', teacher_only=True, unique=(('key','version'),),
        required=('key','version','document_sha256','first_page','last_page','title','active')),
    _t('lesson_script_reviews', 'Lesson Script Reviews', {
        'guide_id':'str','input_sha256':'str','policy_version':'int','review_number':'int','status':'str','method':'str',
        'data':'json','created_at':'datetime',
    }, id_type='str', teacher_only=True, foreign_keys=(ForeignKey('guide_id','guides'),),
        required=('guide_id','input_sha256','policy_version','status','method')),
    # A grown-up's approved answers for one exercise without a book key (the
    # n-th book_work of a saved guide). Kept apart, so the guide stays frozen.
    _t('answer_approvals', 'Approved Answers', {
        'guide_id':'str','work_index':'int','answers':'json','approved_at':'datetime',
    }, id_type='str', teacher_only=True, unique=(('guide_id','work_index'),), foreign_keys=(ForeignKey('guide_id','guides'),),
        required=('guide_id','work_index','answers')),
    # A lesson's video on the publisher's player (found on the subject's video
    # pages, or set by a grown-up; 'hidden' means the lesson has none).
    _t('topic_videos', 'Lesson Videos', {
        'topic_id':'int','provider':'str','video_id':'str','key':'str','title':'str','source':'str','found_at':'datetime',
    }, id_type='str', unique=(('topic_id',),), foreign_keys=(ForeignKey('topic_id','topics'),), required=('topic_id','provider','source')),
    # ── Existing app entities ────────────────────────────────────────────────
    _t("children", "Children", {
        "name": "str", "nickname": "str", "color": "str", "grade_year": "str", "created_at": "datetime",
    }, required=("name",), defaults={"color": "#6B9E8A"}),
    _t("subjects", "Subjects", {
        "child_id": "int", "name": "str", "weight": "float", "slot_type": "str", "end_date": "date",
        "folder": "str", "grade": "str", "purpose": "str", "weekdays": "json", "extra_questions": "str", "book_work": "str", "video_pages": "json",
        "created_at": "datetime",
    }, foreign_keys=(ForeignKey("child_id", "children"),), required=("child_id", "name"),
        defaults={"weight": 1.0, "slot_type": "A"}),
    _t("library_books", "Family Book Library", {
        "title": "str", "author": "str", "year": "int", "stage": "int", "stage_title": "str",
        "position": "int", "style": "str", "estimated_pages": "int", "availability": "str",
        "source_url": "str", "source_label": "str", "store_url": "str", "source_note": "str",
        "document_id": "int", "created_at": "datetime",
    }, id_type="str", required=("title", "author", "stage", "position"),
        foreign_keys=(ForeignKey("document_id", "documents", "restrict", nullable=True),)),
    _t("library_readings", "Independent Book Reading", {
        "book_id": "str", "child_id": "int", "subject_id": "int", "created_at": "datetime",
    }, id_type="str", required=("book_id", "child_id", "subject_id"),
        unique=(("book_id", "child_id"), ("subject_id",)), foreign_keys=(
            ForeignKey("book_id", "library_books", "restrict"), ForeignKey("child_id", "children"),
            ForeignKey("subject_id", "subjects"))),
    _t("library_book_skills", "Shared Book Teaching Instructions", {
        "book_id": "str", "version": "int", "content": "str", "sha256": "str", "file_path": "str", "created_at": "datetime",
    }, id_type="str", required=("book_id", "version", "content", "sha256"), unique=(("book_id", "version"),),
        foreign_keys=(ForeignKey("book_id", "library_books", "restrict"),)),
    _t("library_materials", "Reusable Book Materials", {
        "book_id": "str", "cache_key": "str", "kind": "str", "version": "int", "data": "json",
        "file_path": "str", "sha256": "str", "created_at": "datetime",
    }, id_type="str", required=("book_id", "cache_key", "kind", "version", "data", "file_path", "sha256"),
        unique=(("cache_key", "version"),), foreign_keys=(ForeignKey("book_id", "library_books", "restrict"),), teacher_only=True),
    _t("documents", "Documents", {
        "file_path": "str", "original_filename": "str", "size_bytes": "int", "page_count": "int",
        "sha256": "str", "status": "str", "source": "str", "legacy_blob_path": "str", "created_at": "datetime",
    }, required=("original_filename", "page_count"), defaults={"status": "ready"}),
    _t('document_restorations', 'Original Book Restorations', {
        'document_id':'int','subject_id':'int','before':'json','after':'json','note':'str','created_at':'datetime',
    }, required=('document_id','subject_id','before','after','note'), teacher_only=True,
        foreign_keys=(ForeignKey('document_id','documents','restrict'),ForeignKey('subject_id','subjects','restrict'))),
    _t("topics", "Topics", {
        "subject_id": "int", "title": "str", "page_start": "int", "page_end": "int", "complexity": "int",
        "completed": "bool", "completed_at": "datetime", "completion_source":"str", "language": "str", "chapter_order": "int",
        "pdf_filename": "str", "document_id": "int", "pdf_page_offset": "int", "is_core": "bool",
        "source_key": "str", "start_at": "str", "stop_before": "str", "understanding": "str",
        "last_checked": "date", "evidence_session_id": "str", "next_step": "str", "created_at": "datetime",
        "archived": "bool",
    }, foreign_keys=(ForeignKey("subject_id", "subjects"),
                     ForeignKey("document_id", "documents", "set_null", nullable=True)),
        required=("subject_id", "title", "page_start", "page_end"),
        defaults={"complexity": 1, "completed": False, "chapter_order": 0, "pdf_page_offset": 0, "is_core": True, "archived": False}),
    _t('topic_completion_events','Chapter Completion History',{
        'topic_id':'int','subject_id':'int','child_id':'int','completed':'bool','source':'str',
        'recorded_at':'datetime','closed_session_ids':'json',
    },id_type='str',foreign_keys=(ForeignKey('topic_id','topics'),ForeignKey('subject_id','subjects'),ForeignKey('child_id','children')),
        required=('topic_id','subject_id','child_id','completed','source','recorded_at')),
    _t("time_windows", "Time Windows", {
        "child_id": "int", "weekday": "int", "start_time": "str", "end_time": "str",
    }, foreign_keys=(ForeignKey("child_id", "children"),), required=("child_id", "weekday", "start_time", "end_time")),
    _t("blocked_days", "Blocked Days", {
        "child_id": "int", "date": "date", "block_type": "str", "note": "str", "created_at": "datetime",
    }, foreign_keys=(ForeignKey("child_id", "children", nullable=True),), required=("date", "block_type")),
    _t("scheduled_slots", "Schedules", {
        "child_id": "int", "subject_id": "int", "topic_id": "int", "date": "date", "time_start": "str",
        "time_end": "str", "page_from": "int", "page_to": "int",
    }, foreign_keys=(ForeignKey("child_id", "children"), ForeignKey("subject_id", "subjects"),
                     ForeignKey("topic_id", "topics", nullable=True)),
        required=("child_id", "subject_id", "date", "time_start", "time_end")),
    _t("completions", "Completions", {
        "slot_id": "int", "completed_at": "datetime",
    }, foreign_keys=(ForeignKey("slot_id", "scheduled_slots"),), required=("slot_id",), unique=(("slot_id",),)),
    _t("canvas_inserts", "Canvas Inserts", {
        "parent_topic_id": "int", "insert_topic_id": "int", "position": "int", "created_at": "datetime",
    }, foreign_keys=(ForeignKey("parent_topic_id", "topics"), ForeignKey("insert_topic_id", "topics")),
        required=("parent_topic_id", "insert_topic_id"), defaults={"position": 0}),
    _t("enrichment", "Enrichment", {
        "topic_id": "int", "page_start": "int", "page_end": "int", "content_type": "str",
        "content_path": "str", "content_sha256": "str", "created_at": "datetime",
    }, foreign_keys=(ForeignKey("topic_id", "topics"),), required=("topic_id", "content_type"),
        unique=(("topic_id", "page_start", "page_end", "content_type"),)),
    _t("settings", "Settings", {"value": "str"}, id_type="str"),
    _t("annotations", "Annotation References", {
        "child_id": "int", "document_id": "int", "page_number": "int", "file_path": "str", "sha256": "str",
        "stroke_count": "int", "created_at": "datetime",
    }, foreign_keys=(ForeignKey("child_id", "children"), ForeignKey("document_id", "documents")),
        required=("child_id", "document_id", "page_number"), unique=(("child_id", "document_id", "page_number"),)),

    # ── Tutoring entities ────────────────────────────────────────────────────
    _t("book_collections", "Book Collections", {
        "name": "str", "active_version": "str", "created_at": "datetime",
    }, id_type="str", required=("name",), foreign_keys=(
        ForeignKey("active_version", "collection_versions", "restrict", nullable=True),)),
    _t("subject_collections", "Subject Collections", {
        "subject_id": "int", "collection_id": "str",
    }, id_type="str", required=("subject_id", "collection_id"), unique=(("subject_id",),),
        foreign_keys=(ForeignKey("subject_id", "subjects"), ForeignKey("collection_id", "book_collections", "restrict"))),
    _t("collection_books", "Collection Books", {
        "collection_id": "str", "document_id": "int", "role": "str", "edition": "str",
        "position": "int", "is_main": "bool", "companion_id": "str", "answer_for_id": "str", "answer_for_ids": "json", "archived": "bool",
    }, id_type="str", required=("collection_id", "document_id", "role", "position"),
        unique=(("collection_id", "document_id"),), defaults={"is_main": False, "archived": False, "edition": ""},
        foreign_keys=(ForeignKey("collection_id", "book_collections", "restrict"),
                      ForeignKey("document_id", "documents", "restrict"),
                      ForeignKey("companion_id", "collection_books", "restrict", nullable=True),
                      ForeignKey("answer_for_id", "collection_books", "restrict", nullable=True))),
    _t("collection_versions", "Collection Versions", {
        "collection_id": "str", "number": "int", "fingerprint": "str", "manifest": "json", "created_at": "datetime",
    }, id_type="str", required=("collection_id", "number", "fingerprint", "manifest"),
        unique=(("collection_id", "number"),), foreign_keys=(ForeignKey("collection_id", "book_collections", "restrict"),)),
    _t("collection_analysis_jobs", "Subject Analysis Jobs", {
        "collection_id": "str", "version_id": "str", "subject_id": "int", "status": "str", "stage": "str",
        "provider": "str", "model": "str", "analysis_version": "str", "max_cost_micros": "int",
        "done": "int", "total": "int", "plan": "json", "error": "str", "map_id": "str", "created_at": "datetime",
        "rehearsal_snapshot": "bool", "source_job_id": "str",
    }, id_type="str", required=("collection_id", "version_id", "subject_id", "status", "plan"),
        foreign_keys=(ForeignKey("collection_id", "book_collections", "restrict"), ForeignKey("version_id", "collection_versions", "restrict"),
                      ForeignKey("subject_id", "subjects", "restrict")), teacher_only=True),
    _t("collection_analysis_units", "Subject Analysis Checkpoints", {
        "kind": "str", "input_hash": "str", "data": "json", "created_at": "datetime",
    }, id_type="str", required=("kind", "input_hash", "data"), teacher_only=True),
    _t("subject_maps", "Saved Subject Maps", {
        "collection_id": "str", "version_id": "str", "job_id": "str", "data": "json", "created_at": "datetime",
    }, id_type="str", required=("collection_id", "version_id", "job_id", "data"), teacher_only=True,
        foreign_keys=(ForeignKey("collection_id", "book_collections", "restrict"), ForeignKey("version_id", "collection_versions", "restrict"),
                      ForeignKey("job_id", "collection_analysis_jobs", "restrict"))),
    _t("subject_map_reviews", "Parent Source Map Reviews", {
        "collection_id": "str", "map_id": "str", "review_number": "int", "kind": "str", "target_id": "str",
        "status": "str", "changes": "json", "note": "str", "original": "json", "created_at": "datetime",
    }, id_type="str", teacher_only=True,
        required=("collection_id", "map_id", "review_number", "kind", "target_id", "status", "changes", "original"),
        unique=(("collection_id", "review_number"),),
        foreign_keys=(ForeignKey("collection_id", "book_collections", "restrict"),)),
    _t("learning_snapshots", "Learning Summaries", {
        "child_id": "int", "subject_id": "int", "fingerprint": "str", "summary_version": "int", "data": "json", "created_at": "datetime",
    }, id_type="str", required=("child_id", "subject_id", "fingerprint", "summary_version", "data"),
        unique=(("child_id", "subject_id", "fingerprint"),),
        foreign_keys=(ForeignKey("child_id", "children"), ForeignKey("subject_id", "subjects")), teacher_only=True),
    _t("subject_map_selections", "Active Teaching Map History", {
        "subject_id": "int", "map_id": "str", "selection_number": "int", "review_number": "int",
        "fingerprint": "str", "data": "json", "created_at": "datetime",
    }, id_type="str", required=("subject_id", "map_id", "selection_number", "review_number", "fingerprint", "data"),
        unique=(("subject_id", "selection_number"),), foreign_keys=(ForeignKey("subject_id", "subjects"),), teacher_only=True),
    _t("learner_concept_links", "Learning Evidence Links", {
        "child_id": "int", "subject_id": "int", "evidence_kind": "str", "evidence_id": "str", "map_id": "str", "concept_id": "str",
        "link_number": "int", "status": "str", "note": "str", "created_at": "datetime",
    }, id_type="str", required=("child_id", "subject_id", "evidence_kind", "evidence_id", "link_number", "status", "note"),
        unique=(("child_id", "subject_id", "link_number"),),
        foreign_keys=(ForeignKey("child_id", "children"), ForeignKey("subject_id", "subjects")), teacher_only=True),
    _t("subject_books", "Subject Books", {
        "subject_id": "int", "document_id": "int", "role": "str", "companion_id": "str",
        "status": "str", "active_index": "str", "archived": "bool", "created_at": "datetime", "answer_for_id": "str", "answer_for_ids": "json",
    }, id_type="str", foreign_keys=(ForeignKey("subject_id", "subjects"), ForeignKey("document_id", "documents", "restrict")),
        required=("subject_id", "document_id", "role"), unique=(("subject_id", "document_id"),), defaults={"archived": False}),
    _t("book_imports", "Book Preparation", {
        "book_id": "str", "status": "str", "stage": "str", "done": "int", "total": "int",
        "source_path": "str", "destination_path": "str", "source_sha256": "str", "error": "str", "pending_ranges": "json",
        "index_id": "str", "created_at": "datetime", "mode": "str", "target_topic_id": "int",
    }, id_type="str", foreign_keys=(ForeignKey("book_id", "subject_books"),), required=("book_id", "status")),
    _t("book_units", "Book Scan Units", {
        "sha256": "str", "role": "str", "version": "str", "first_page": "int", "last_page": "int", "data": "json",
    }, id_type="str", required=("sha256", "role", "version", "data"), teacher_only=True),
    _t("book_companions", "Book Companions", {
        "document_id": "int", "sha256": "str", "role": "str", "content_sha256": "str", "data": "json",
        "file_path": "str", "file_sha256": "str", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("document_id", "documents", "restrict"),),
        required=("document_id", "sha256", "role", "content_sha256", "data"),
        unique=(("sha256", "role"),), teacher_only=True),
    _t("book_source_reviews", "Book Source Corrections", {
        "sha256": "str", "role": "str", "version": "int", "content_sha256": "str",
        "previous_sha256": "str", "data": "json", "file_path": "str", "note": "str", "created_at": "datetime",
    }, id_type="str", required=("sha256", "role", "version", "content_sha256", "data", "note"),
        unique=(("sha256", "role", "version"),), teacher_only=True),
    _t("material_skills", "Material Analysis Skills", {
        "key": "str", "version": "int", "content": "str", "sha256": "str", "file_path": "str", "created_at": "datetime",
    }, required=("key", "version", "content", "sha256"), unique=(("key", "version"),), teacher_only=True),
    _t("exercises", "Exercises", {
        "book_id": "str", "active_version": "str", "archived": "bool", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("book_id", "subject_books", "restrict"),), required=("book_id",), defaults={"archived": False}),
    _t("exercise_versions", "Exercise Versions", {
        "exercise_id": "str", "index_id": "str", "data": "json", "parent_edited": "bool", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("exercise_id", "exercises", "restrict"),),
        required=("exercise_id", "data"), teacher_only=True),
    _t("exercise_attempt_links", "Imported Exercise Attempts", {
        "exercise_id": "str", "attempt_id": "str",
    }, id_type="str", foreign_keys=(ForeignKey("exercise_id", "exercises", "restrict"), ForeignKey("attempt_id", "attempts", "restrict")),
        required=("exercise_id", "attempt_id"), unique=(("exercise_id", "attempt_id"),), teacher_only=True),
    _t("assignment_items", "Exercise Assignments", {
        "assignment_id": "str", "exercise_id": "str", "version_id": "str", "child_id": "int",
        "topic_id": "int", "status": "str", "snapshot": "json", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("assignment_id", "assignments", "restrict"),
        ForeignKey("exercise_id", "exercises", "restrict"), ForeignKey("version_id", "exercise_versions", "restrict"),
        ForeignKey("child_id", "children"), ForeignKey("topic_id", "topics", "restrict")),
        required=("assignment_id", "exercise_id", "version_id", "child_id", "topic_id", "status"), teacher_only=True),
    _t("subject_skills", "Teaching Skills", {
        "subject_id": "int", "version": "int", "content": "str", "sha256": "str",
        "file_path": "str", "created_at": "datetime",
    }, foreign_keys=(ForeignKey("subject_id", "subjects"),), required=("subject_id", "version", "content"),
        unique=(("subject_id", "version"),), teacher_only=True),
    _t("family_tutor_skills", "Family Tutoring Skill", {
        "version": "int", "content": "str", "profiles": "json", "sha256": "str", "file_path": "str", "created_at": "datetime",
    }, required=("version", "content", "profiles", "sha256"), unique=(("version",),), teacher_only=True),
    _t("lesson_dialogue", "Lesson Conversation", {
        "session_id": "str", "action_id": "str", "role": "str", "text": "str", "evidence_ids": "json",
        "status": "str", "assessment": "json", "sequence": "int", "input_revision": "int", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"),),
        required=("session_id", "role", "status"), teacher_only=True),
    _t("lesson_actions", "Student Actions", {
        "session_id": "str", "child_id": "int", "subject_id": "int", "topic_id": "int",
        "action_id": "str", "prompt": "str", "kind": "str", "status": "str", "help_given": "str",
        "next_prompt": "str", "review_id": "str", "source_action_id": "str", "created_at": "datetime",
        "assignment_item_id": "str", "concept_ids": "json", "map_selection_id": "str",
        "activity_kind": "str", "activity_content": "json", "activity_order": "int", "origin": "str",
        "source_refs": "json", "parent_activity_id": "str", "return_cursor": "json", "stage": "str",
        "start_sentence": "int", "end_sentence": "int", "resume_index": "int",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children"),
                                    ForeignKey("subject_id", "subjects"), ForeignKey("topic_id", "topics")),
        required=("session_id", "child_id", "subject_id", "topic_id", "action_id", "prompt", "status")),
    _t("lesson_playback", "Lesson Playback", {
        "session_id": "str", "guide_id": "str", "skill_id": "int", "sentence_index": "int",
        "action_id": "str", "resume_index": "int", "reading_finished": "bool", "slot_id": "int", "context_snapshot": "json", "generation_scope_id": "str",
        "activity_contract_version": "int", "on_break": "bool", "break_snapshot": "json", "narration_cursor": "json", "tutor_activity_access": "bool",
        "navigation_state": "json",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"),), required=("session_id",),
        defaults={"sentence_index": 0, "resume_index": 0, "reading_finished": False}),
    _t("activity_interactions", "Activity Interactions", {
        "session_id": "str", "child_id": "int", "activity_id": "str", "prompt": "str",
        "status": "str", "stage": "str", "sequence": "int", "created_at": "datetime",
        "replay_of": "str", "is_replay": "bool", "dialogue_start_sequence": "int",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children")),
        required=("session_id", "child_id", "activity_id", "status"), teacher_only=True),
    _t("activity_responses", "Activity Responses", {
        "session_id": "str", "child_id": "int", "activity_id": "str", "interaction_id": "str",
        "method": "str", "original": "json", "confirmed_text": "str", "evidence_ids": "json",
        "reasoning": "str", "status": "str", "message_id": "str", "created_at": "datetime",
        "proposed_text": "str", "transcription_status": "str", "parent_observation": "json", "support_snapshot": "json",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children"),
        ForeignKey("interaction_id", "activity_interactions", "restrict")),
        required=("session_id", "child_id", "activity_id", "interaction_id", "method", "status"), teacher_only=True),
    _t("activity_drafts", "Activity Drafts", {
        "session_id": "str", "child_id": "int", "activity_id": "str", "interaction_id": "str", "content": "json",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children"),
        ForeignKey("interaction_id", "activity_interactions", "restrict")),
        required=("session_id", "child_id", "activity_id", "interaction_id"), teacher_only=True),
    _t("activity_events", "Activity Events", {
        "session_id": "str", "child_id": "int", "activity_id": "str", "interaction_id": "str",
        "event_type": "str", "payload": "json", "sequence": "int", "operation_id": "str",
        "request_sha256": "str", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children")),
        required=("session_id", "child_id", "event_type", "sequence", "operation_id"),
        unique=(("session_id", "operation_id"),), teacher_only=True),
    _t("lesson_preparation_jobs", "Lesson Preparation Jobs", {
        "child_id":"int", "subject_id":"int", "topic_id":"int", "target":"str", "status":"str",
        "phase":"str", "guide_id":"str", "error":"str", "created_at":"datetime",
        "request_sha256":"str", "maximum_guide_usd":"float", "maximum_audio_usd":"float",
        "replace_invalid":"bool", "repair_audio":"bool", "error_code":"str", "recovery":"str",
        "teaching_provider":"str", "audio_provider":"str", "rewrite":"bool", "retry_uncertain":"bool",
    }, id_type="str", foreign_keys=(ForeignKey("child_id","children"),ForeignKey("subject_id","subjects"),
        ForeignKey("topic_id","topics")), required=("child_id","subject_id","topic_id","target","status"), teacher_only=True),
    _t("activity_jobs", "Activity Jobs", {
        "session_id": "str", "child_id": "int", "activity_id": "str", "interaction_id": "str",
        "response_id": "str", "kind": "str", "status": "str", "input_snapshot": "json",
        "result": "json", "error": "str", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children")),
        required=("session_id", "child_id", "activity_id", "kind", "status"), teacher_only=True),
    _t("chapters", "Chapters", {
        "subject_id": "int", "chapter": "int", "title": "str", "book_start": "int", "book_end": "int",
        "test_pdf_start": "int", "test_pdf_end": "int", "test_print_start": "int", "test_print_end": "int",
        "key_pdf_page": "int", "test_document_id": "int", "test_status": "str", "test_date": "date", "session_id": "str",
        "items_to_revisit": "str", "note": "str",
    }, id_type="str", foreign_keys=(ForeignKey("subject_id", "subjects"),
                                    ForeignKey("test_document_id", "documents", "set_null", nullable=True)),
        required=("subject_id", "chapter")),
    _t("preferences", "Preferences", {
        "child_id": "int", "key": "str", "value": "json", "confirmed_by": "str", "confirmed_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("child_id", "children"),), required=("child_id", "key")),
    _t("tutor_sessions", "Sessions", {
        "child_id": "int", "subject_id": "int", "topic_id": "int", "date": "date", "status": "str",
        "session_type": "str", "phase": "str", "reading_mode": "str", "minutes": "int",
        "learner_explained": "str", "difficulty": "str", "help_that_worked": "str", "next_action": "str",
        "parent_observation": "str", "evidence": "str", "next_topic_id": "int", "source": "str",
        "started_at": "datetime", "finished_at": "datetime",
        "completion_summary": "json", "completion_source":"str",
    }, id_type="str", foreign_keys=(ForeignKey("child_id", "children"), ForeignKey("subject_id", "subjects"),
                                    ForeignKey("topic_id", "topics", "restrict"),
                                    ForeignKey("next_topic_id", "topics", "set_null", nullable=True)),
        required=("child_id", "subject_id", "topic_id", "status")),
    _t("attempts", "Attempts", {
        "session_id": "str", "child_id": "int", "topic_id": "int", "chapter": "int", "question_ref": "str",
        "question_text": "str", "first_answer": "str", "reading_certainty": "str", "first_result": "str",
        "help_given": "str", "revised_answer": "str", "after_help_result": "str", "independence": "str",
        "recheck_date": "date", "evidence_paths": "json", "source_note": "str", "tutor_created": "bool",
        "amends_attempt_id": "str", "created_at": "datetime",
        "assignment_item_id": "str", "exercise_id": "str",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions", "restrict"),
                                    ForeignKey("child_id", "children"), ForeignKey("topic_id", "topics", "restrict")),
        required=("session_id", "child_id", "topic_id", "question_ref", "first_result")),
    _t("reviews", "Reviews", {
        "child_id": "int", "topic_id": "int", "concept": "str", "evidence": "str", "last_practice": "date",
        "interval_days": "int", "next_due": "date", "status": "str", "last_outcome": "str",
        "next_prompt": "str", "action": "str", "evidence_session_id": "str",
        "exercise_id": "str", "assignment_item_id": "str",
    }, id_type="str", foreign_keys=(ForeignKey("child_id", "children"), ForeignKey("topic_id", "topics", "restrict")),
        required=("child_id", "topic_id", "concept", "status")),
    _t("checkpoints", "Checkpoints", {
        "session_id": "str", "child_id": "int", "topic_id": "int", "phase": "str", "status": "str",
        "next_prompt": "str", "observations": "json", "basis": "str", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children"),
                                    ForeignKey("topic_id", "topics", "restrict")),
        required=("session_id", "child_id", "topic_id", "status", "next_prompt")),
    _t("assignments", "Assignments", {
        "session_id": "str", "child_id": "int", "topic_id": "int", "questions": "json", "note": "str",
        "status": "str", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions"), ForeignKey("child_id", "children"),
                                    ForeignKey("topic_id", "topics", "restrict")),
        required=("session_id", "child_id", "topic_id", "questions", "status")),
    _t("passages", "Passages", {
        "topic_id": "int", "document_id": "int", "document_sha256": "str", "pdf_start": "int", "pdf_end": "int",
        "start_at": "str", "stop_before": "str", "extraction_version": "str", "status": "str",
        "passage_path": "str", "passage_sha256": "str", "sentence_count": "int", "character_count": "int",
        "review_notes": "str", "reviewed_at": "datetime", "source": "str",
    }, id_type="str", foreign_keys=(ForeignKey("topic_id", "topics"), ForeignKey("document_id", "documents")),
        required=("topic_id", "document_id", "status")),
    _t("audio_tracks", "Audio", {
        "topic_id": "int", "passage_sha256": "str", "provider": "str", "voice": "str", "speaking_rate": "float",
        "manifest_path": "str", "status": "str", "characters": "int", "sentence_count": "int",
        "timing": "str", "note": "str", "created_at": "datetime",
    }, id_type="str", foreign_keys=(ForeignKey("topic_id", "topics"),), required=("topic_id", "provider", "status")),
    _t("guides", "Guided Lessons", {
        "topic_id": "int", "source_sha256": "str", "guide_sha256": "str", "guide_path": "str",
        "guide_file_sha256": "str", "mode": "str", "model": "str", "language": "str", "sentence_count": "int",
        "character_count": "int", "created_at": "datetime", "skill_sha256": "str", "skill_id": "int",
        "context_snapshot": "json", "source_snapshot": "json",
    }, id_type="str", foreign_keys=(ForeignKey("topic_id", "topics"),),
        required=("topic_id", "source_sha256", "guide_sha256", "guide_path")),
    _t("question_maps", "Question Map", {
        "subject_id": "int", "chapter": "int", "question": "int", "topic_id": "int", "anchor": "str",
        "evidence": "str", "note": "str",
    }, id_type="str", teacher_only=True, foreign_keys=(ForeignKey("subject_id", "subjects"), ForeignKey("topic_id", "topics")),
        required=("subject_id", "chapter", "question", "topic_id")),
    _t("teacher_keys", "Teacher Keys", {
        "subject_id": "int", "chapter": "int", "question_start": "int", "question_end": "int", "answer": "str",
        "key_pdf_page": "int", "key_printed_page": "int", "exception": "str", "source_reference": "str",
    }, id_type="str", teacher_only=True, foreign_keys=(ForeignKey("subject_id", "subjects"),),
        required=("subject_id", "chapter", "question_start", "question_end")),
    _t("answer_entries", "Imported Answer Keys", {
        "book_id": "str", "source_sha256": "str", "reference": "str", "chapter": "int", "section": "str",
        "pages": "json", "answer": "str", "evidence": "str", "issue": "str", "created_at": "datetime", "evidence_element_ids": "json", "evidence_quotes": "json",
    }, id_type="str", teacher_only=True, foreign_keys=(ForeignKey("book_id", "subject_books", "restrict"),),
        required=("book_id", "source_sha256", "reference", "pages", "answer")),
    _t("evidence_files", "Student Work", {
        "child_id": "int", "session_id": "str", "file_path": "str", "sha256": "str", "filename": "str",
        "mime_type": "str", "note": "str", "created_at": "datetime", "action_id": "str", "size_bytes": "int",
    }, id_type="str", foreign_keys=(ForeignKey("child_id", "children"), ForeignKey("session_id", "tutor_sessions", nullable=True)),
        required=("child_id", "file_path")),
    _t("operation_receipts", "Operation Receipts", {
        "payload_sha256": "str", "kind": "str", "device": "str", "summary": "str", "created_at": "datetime",
    }, id_type="str"),
]}



# ── Value conversion ─────────────────────────────────────────────────────────

def _parse_datetime(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def coerce(kind: str, value, from_cell: bool = False):
    """Convert caller input (or, with ``from_cell``, sheet text) to the in-memory type for ``kind``."""
    if value is None or value == "":
        return None
    if kind == "int":
        if isinstance(value, bool):
            raise ValueError("Expected an integer")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("Expected an integer")
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().upper()
        if text in {"TRUE", "1", "YES"}:
            return True
        if text in {"FALSE", "0", "NO"}:
            return False
        raise ValueError(f"Expected TRUE or FALSE, got {value!r}")
    if kind == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])
    if kind == "datetime":
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        return _parse_datetime(str(value))
    if kind == "json":
        if from_cell:
            return json.loads(value)
        json.dumps(value)  # validate serialisable
        return value
    return str(value)


def to_cell(kind: str, value) -> str:
    """Serialise one in-memory value as exact sheet text."""
    if value is None:
        return ""
    if kind == "bool":
        return "TRUE" if value else "FALSE"
    if kind == "datetime":
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if kind == "date":
        return value.isoformat()
    if kind == "json":
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if kind == "float":
        return repr(float(value))
    return str(value)


def column_kind(table: Table, column: str) -> str:
    if column == "id":
        return table.id_type
    if column == "revision":
        return "int"
    if column == "updated_at":
        return "datetime"
    return table.columns[column]


def normalise(table: Table, values: dict, partial: bool = False) -> dict:
    """Validate caller input against the tab definition."""
    unknown = set(values) - set(table.header)
    if unknown:
        raise ValueError(f"Unknown {table.name} fields: {', '.join(sorted(unknown))}")
    result = {}
    for column, value in values.items():
        if column in ("revision", "updated_at"):
            continue
        result[column] = coerce(column_kind(table, column), value)
    if not partial:
        for column, default in table.defaults.items():
            if result.get(column) is None:
                result[column] = default
    return result
