from datetime import datetime

from sqlalchemy import Column, DateTime, String

from database import Base


class FamilyAccount(Base):
    """The single approved Supabase user for this private family app."""

    __tablename__ = "family_accounts"

    user_id = Column(String(36), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
