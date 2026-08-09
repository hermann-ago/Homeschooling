from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from datetime import datetime
from database import Base

class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("owner_id", "key", name="uq_app_settings_owner_key"),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String(36), nullable=True, index=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
