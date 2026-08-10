from sqlalchemy import Column, Integer, String, DateTime, Uuid
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Child(Base):
    __tablename__ = "children"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Uuid(as_uuid=False), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    nickname = Column(String(50), nullable=True)
    color = Column(String(7), nullable=False, default="#6B9E8A")
    grade_year = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subjects = relationship("Subject", back_populates="child", cascade="all, delete-orphan")
    time_windows = relationship("TimeWindow", back_populates="child", cascade="all, delete-orphan")
    blocked_days = relationship("BlockedDay", back_populates="child", cascade="all, delete-orphan")
    scheduled_slots = relationship("ScheduledSlot", back_populates="child", cascade="all, delete-orphan")
