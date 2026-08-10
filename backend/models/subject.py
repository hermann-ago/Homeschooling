from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0)
    slot_type = Column(String(1), default="A")
    end_date = Column(Date, nullable=True)
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
    complexity = Column(Integer, default=1)
    completed = Column(Boolean, default=False)
    language = Column(String(10), nullable=True)
    chapter_order = Column(Integer, default=0)
    pdf_filename = Column(String(255), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    pdf_page_offset = Column(Integer, default=0)
    is_core = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subject = relationship("Subject", back_populates="curriculum_topics")
    document = relationship("Document", back_populates="topics")
    scheduled_slots = relationship("ScheduledSlot", back_populates="topic", cascade="all, delete-orphan")
