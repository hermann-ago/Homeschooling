from datetime import datetime, timezone

from models import CurriculumTopic


def mark_topic_completed(
    topic: CurriculumTopic,
    completed_at: datetime | None = None,
) -> None:
    """Mark a topic complete and automatically record when it happened."""
    topic.completed = True
    if topic.completed_at is None:
        topic.completed_at = completed_at or datetime.now(timezone.utc)


def mark_topic_incomplete(topic: CurriculumTopic) -> None:
    """Undo topic completion and its recorded completion time."""
    topic.completed = False
    topic.completed_at = None
