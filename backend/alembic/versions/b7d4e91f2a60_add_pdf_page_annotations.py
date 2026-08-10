"""Add persistent per-child PDF page annotations.

Revision ID: b7d4e91f2a60
Revises: f4b927a1c3de
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7d4e91f2a60"
down_revision: Union[str, None] = "f4b927a1c3de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_children_id_owner", "children", ["id", "owner_id"])
    op.create_unique_constraint("uq_documents_id_owner", "documents", ["id", "owner_id"])
    op.create_table(
        "pdf_page_annotations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column(
            "strokes",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("page_number > 0", name="ck_pdf_page_annotations_page_positive"),
        sa.CheckConstraint("revision > 0", name="ck_pdf_page_annotations_revision_positive"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["family_accounts.user_id"],
            name="pdf_page_annotations_owner_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_id", "owner_id"],
            ["children.id", "children.owner_id"],
            name="pdf_page_annotations_child_owner_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["documents.id", "documents.owner_id"],
            name="pdf_page_annotations_document_owner_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "child_id",
            "document_id",
            "page_number",
            name="uq_pdf_page_annotations_page",
        ),
    )
    op.create_index(
        "ix_pdf_page_annotations_owner_id",
        "pdf_page_annotations",
        ["owner_id"],
    )
    op.create_index(
        "ix_pdf_page_annotations_child_owner",
        "pdf_page_annotations",
        ["child_id", "owner_id"],
    )
    op.create_index(
        "ix_pdf_page_annotations_document_owner",
        "pdf_page_annotations",
        ["document_id", "owner_id"],
    )


def downgrade() -> None:
    op.drop_table("pdf_page_annotations")
    op.drop_constraint("uq_documents_id_owner", "documents", type_="unique")
    op.drop_constraint("uq_children_id_owner", "children", type_="unique")
