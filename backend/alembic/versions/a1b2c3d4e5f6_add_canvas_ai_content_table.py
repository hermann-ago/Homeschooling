"""add_canvas_ai_content_table

Revision ID: a1b2c3d4e5f6
Revises: bf2254b8bf1b
Create Date: 2026-04-03

Adds the canvas_ai_content table that caches AI-generated enrichment
content (quizzes, audio summaries, key terms, simplified explanations)
for each topic + page range combination.

The unique constraint (uq_ai_content_topic_pages_type) ensures that
generating the same content type for the same topic/pages only results
in one cached row — re-generates overwrite via upsert logic in the router.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'bf2254b8bf1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'canvas_ai_content',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('page_start', sa.Integer(), nullable=False),
        sa.Column('page_end', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['topic_id'], ['curriculum_topics.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'topic_id', 'page_start', 'page_end', 'content_type',
            name='uq_ai_content_topic_pages_type'
        ),
    )
    op.create_index(op.f('ix_canvas_ai_content_id'), 'canvas_ai_content', ['id'], unique=False)
    op.create_index(op.f('ix_canvas_ai_content_topic_id'), 'canvas_ai_content', ['topic_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_canvas_ai_content_topic_id'), table_name='canvas_ai_content')
    op.drop_index(op.f('ix_canvas_ai_content_id'), table_name='canvas_ai_content')
    op.drop_table('canvas_ai_content')
