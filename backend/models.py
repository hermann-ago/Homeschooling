from sqlalchemy import (
    Column, Integer, String, Float, Date, Time, DateTime, ForeignKey, Text, Boolean,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class Child(Base):
    __tablename__ = "children"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    nickname = Column(String(50), nullable=True)
    color = Column(String(7), nullable=False, default="#6B9E8A")  # hex color
    grade_year = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subjects = relationship("Subject", back_populates="child", cascade="all, delete-orphan")
    time_windows = relationship("TimeWindow", back_populates="child", cascade="all, delete-orphan")
    blocked_days = relationship("BlockedDay", back_populates="child", cascade="all, delete-orphan")
    scheduled_slots = relationship("ScheduledSlot", back_populates="child", cascade="all, delete-orphan")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0)  # time weight for scheduling
    slot_type = Column(String(1), default="A")  # "A" or "B"
    end_date = Column(Date, nullable=True) # Optional target end date
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    child = relationship("Child", back_populates="subjects")
    curriculum_topics = relationship("CurriculumTopic", back_populates="subject", cascade="all, delete-orphan")
    scheduled_slots = relationship("ScheduledSlot", back_populates="subject", cascade="all, delete-orphan")


class CurriculumTopic(Base):
    __tablename__ = "curriculum_topics"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(300), nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    complexity = Column(Integer, default=1)  # 1=easy, 2=medium, 3=hard
    completed = Column(Boolean, default=False)  # manually mark topic as done
    language = Column(String(10), nullable=True)  # 'pt', 'en', etc.
    chapter_order = Column(Integer, default=0)
    pdf_filename = Column(String(255), nullable=True)
    pdf_path = Column(String(500), nullable=True)  # path to stored PDF file
    pdf_page_offset = Column(Integer, default=0) # offset to map TOC pages to PDF physical pages
    is_core = Column(Boolean, default=True)  # True = Main curriculum, False = Accessory
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subject = relationship("Subject", back_populates="curriculum_topics")
    scheduled_slots = relationship("ScheduledSlot", back_populates="topic", cascade="all, delete-orphan")


class TimeWindow(Base):
    __tablename__ = "time_windows"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    weekday = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(String(5), nullable=False)  # "08:00"
    end_time = Column(String(5), nullable=False)    # "11:00"

    # Relationships
    child = relationship("Child", back_populates="time_windows")


class BlockedDay(Base):
    __tablename__ = "blocked_days"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=True)  # NULL = all children
    date = Column(Date, nullable=False)
    block_type = Column(String(20), nullable=False)  # 'holiday', 'sick', 'custom'
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    child = relationship("Child", back_populates="blocked_days")


class ScheduledSlot(Base):
    __tablename__ = "scheduled_slots"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(Integer, ForeignKey("curriculum_topics.id", ondelete="CASCADE"), nullable=True)
    date = Column(Date, nullable=False)
    time_start = Column(String(5), nullable=False)
    time_end = Column(String(5), nullable=False)
    page_from = Column(Integer, nullable=True)
    page_to = Column(Integer, nullable=True)

    # Relationships
    child = relationship("Child", back_populates="scheduled_slots")
    subject = relationship("Subject", back_populates="scheduled_slots")
    topic = relationship("CurriculumTopic", back_populates="scheduled_slots")
    completion = relationship("Completion", back_populates="slot", uselist=False, cascade="all, delete-orphan")


class Completion(Base):
    __tablename__ = "completions"

    id = Column(Integer, primary_key=True, index=True)
    slot_id = Column(Integer, ForeignKey("scheduled_slots.id", ondelete="CASCADE"), nullable=False, unique=True)
    completed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    slot = relationship("ScheduledSlot", back_populates="completion")


class AppSetting(Base):
    """Key-value settings table to replace fragile .env file writes."""
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CanvasInsert(Base):
    """Links a supplementary topic to appear after a parent topic in the Daily Canvas."""
    __tablename__ = "canvas_inserts"

    id = Column(Integer, primary_key=True, index=True)
    parent_topic_id = Column(Integer, ForeignKey("curriculum_topics.id", ondelete="CASCADE"), nullable=False)
    insert_topic_id = Column(Integer, ForeignKey("curriculum_topics.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, default=0)  # ordering among inserts for same parent
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    parent_topic = relationship("CurriculumTopic", foreign_keys=[parent_topic_id])
    insert_topic = relationship("CurriculumTopic", foreign_keys=[insert_topic_id])


class CanvasAIContent(Base):
    """
    Caches AI-generated enrichment content for a specific topic + page range.

    Each row stores one type of AI output ('quiz', 'audio', 'terms', 'explain')
    as a JSON string. The unique constraint on (topic_id, page_start, page_end,
    content_type) prevents duplicate generation for the same material.

    content_type values:
        'quiz'    – JSON array of MCQ questions with choices and answer
        'audio'   – Plain-text summary intended for browser SpeechSynthesis TTS
        'terms'   – JSON array of {term, definition} objects
        'explain' – Plain-text "Explain Like I'm 10" paragraph
    """
    __tablename__ = "canvas_ai_content"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "page_start", "page_end", "content_type",
            name="uq_ai_content_topic_pages_type"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(
        Integer, ForeignKey("curriculum_topics.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    # One of: 'quiz', 'audio', 'terms', 'explain'
    content_type = Column(String(20), nullable=False)
    # JSON-encoded payload; structure depends on content_type
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    topic = relationship("CurriculumTopic")
