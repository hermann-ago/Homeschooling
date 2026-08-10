from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


class PdfPageAnnotation(Base):
    __tablename__ = "pdf_page_annotations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["child_id", "owner_id"],
            ["children.id", "children.owner_id"],
            name="pdf_page_annotations_child_owner_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["documents.id", "documents.owner_id"],
            name="pdf_page_annotations_document_owner_fkey",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "owner_id",
            "child_id",
            "document_id",
            "page_number",
            name="uq_pdf_page_annotations_page",
        ),
        CheckConstraint("page_number > 0", name="ck_pdf_page_annotations_page_positive"),
        CheckConstraint("revision > 0", name="ck_pdf_page_annotations_revision_positive"),
        Index("ix_pdf_page_annotations_child_owner", "child_id", "owner_id"),
        Index("ix_pdf_page_annotations_document_owner", "document_id", "owner_id"),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    owner_id = Column(
        Uuid(as_uuid=False),
        ForeignKey("family_accounts.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    child_id = Column(Integer, nullable=False)
    document_id = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=False)
    strokes = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
