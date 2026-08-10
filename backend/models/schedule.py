from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Uuid
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class TimeWindow(Base):
    __tablename__ = "time_windows"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    weekday = Column(Integer, nullable=False)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)

    # Relationships
    child = relationship("Child", back_populates="time_windows")


class BlockedDay(Base):
    __tablename__ = "blocked_days"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Uuid(as_uuid=False), nullable=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=True)
    date = Column(Date, nullable=False)
    block_type = Column(String(20), nullable=False)
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
