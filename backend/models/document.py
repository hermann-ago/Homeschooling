from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Uuid
from sqlalchemy.orm import relationship

from database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Uuid(as_uuid=False), nullable=False, index=True)
    blob_path = Column(String(600), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    page_count = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="ready")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    topics = relationship("CurriculumTopic", back_populates="document")
