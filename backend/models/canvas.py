from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class CanvasInsert(Base):
    __tablename__ = "canvas_inserts"

    id = Column(Integer, primary_key=True, index=True)
    parent_topic_id = Column(Integer, ForeignKey("curriculum_topics.id", ondelete="CASCADE"), nullable=False)
    insert_topic_id = Column(Integer, ForeignKey("curriculum_topics.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    parent_topic = relationship("CurriculumTopic", foreign_keys=[parent_topic_id])
    insert_topic = relationship("CurriculumTopic", foreign_keys=[insert_topic_id])


class CanvasAIContent(Base):
    __tablename__ = "canvas_ai_content"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "page_start", "page_end", "content_type",
            name="uq_ai_content_topic_pages_type"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("curriculum_topics.id", ondelete="CASCADE"), nullable=False, index=True)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    content_type = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    topic = relationship("CurriculumTopic")
