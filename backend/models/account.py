from datetime import datetime

from sqlalchemy import Column, DateTime, Uuid

from database import Base


class FamilyAccount(Base):
    """The single approved Supabase user for this private family app."""

    __tablename__ = "family_accounts"

    user_id = Column(Uuid(as_uuid=False), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
