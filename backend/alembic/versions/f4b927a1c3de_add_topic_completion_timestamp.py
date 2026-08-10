"""Add automatic curriculum topic completion timestamps.

Revision ID: f4b927a1c3de
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b927a1c3de"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "curriculum_topics",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        update curriculum_topics
        set completed_at = (
            select max(completions.completed_at)
            from scheduled_slots
            join completions on completions.slot_id = scheduled_slots.id
            where scheduled_slots.topic_id = curriculum_topics.id
        )
        where completed = true
          and exists (
            select 1
            from scheduled_slots
            join completions on completions.slot_id = scheduled_slots.id
            where scheduled_slots.topic_id = curriculum_topics.id
          )
        """
    )


def downgrade() -> None:
    op.drop_column("curriculum_topics", "completed_at")
