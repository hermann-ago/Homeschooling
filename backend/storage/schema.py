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

SCHEMA_VERSION = 1
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
    # ── Existing app entities ────────────────────────────────────────────────
    _t("children", "Children", {
        "name": "str", "nickname": "str", "color": "str", "grade_year": "str", "created_at": "datetime",
    }, required=("name",), defaults={"color": "#6B9E8A"}),
    _t("subjects", "Subjects", {
        "child_id": "int", "name": "str", "weight": "float", "slot_type": "str", "end_date": "date",
        "folder": "str", "grade": "str", "created_at": "datetime",
    }, foreign_keys=(ForeignKey("child_id", "children"),), required=("child_id", "name"),
        defaults={"weight": 1.0, "slot_type": "A"}),
    _t("documents", "Documents", {
        "file_path": "str", "original_filename": "str", "size_bytes": "int", "page_count": "int",
        "sha256": "str", "status": "str", "source": "str", "legacy_blob_path": "str", "created_at": "datetime",
    }, required=("original_filename", "page_count"), defaults={"status": "ready"}),
    _t("topics", "Topics", {
        "subject_id": "int", "title": "str", "page_start": "int", "page_end": "int", "complexity": "int",
        "completed": "bool", "completed_at": "datetime", "language": "str", "chapter_order": "int",
        "pdf_filename": "str", "document_id": "int", "pdf_page_offset": "int", "is_core": "bool",
        "source_key": "str", "start_at": "str", "stop_before": "str", "understanding": "str",
        "last_checked": "date", "evidence_session_id": "str", "next_step": "str", "created_at": "datetime",
    }, foreign_keys=(ForeignKey("subject_id", "subjects"),
                     ForeignKey("document_id", "documents", "set_null", nullable=True)),
        required=("subject_id", "title", "page_start", "page_end"),
        defaults={"complexity": 1, "completed": False, "chapter_order": 0, "pdf_page_offset": 0, "is_core": True}),
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
    }, id_type="str", foreign_keys=(ForeignKey("session_id", "tutor_sessions", "restrict"),
                                    ForeignKey("child_id", "children"), ForeignKey("topic_id", "topics", "restrict")),
        required=("session_id", "child_id", "topic_id", "question_ref", "first_result")),
    _t("reviews", "Reviews", {
        "child_id": "int", "topic_id": "int", "concept": "str", "evidence": "str", "last_practice": "date",
        "interval_days": "int", "next_due": "date", "status": "str", "last_outcome": "str",
        "next_prompt": "str", "action": "str", "evidence_session_id": "str",
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
        "character_count": "int", "created_at": "datetime",
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
    _t("evidence_files", "Student Work", {
        "child_id": "int", "session_id": "str", "file_path": "str", "sha256": "str", "filename": "str",
        "mime_type": "str", "note": "str", "created_at": "datetime",
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
