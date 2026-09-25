from datetime import datetime, timezone


def mark_topic_completed(topic: dict, completed_at: datetime | None = None) -> dict:
    """Mark a topic complete and automatically record when it happened."""
    topic["completed"] = True
    if topic.get("completed_at") is None:
        topic["completed_at"] = completed_at or datetime.now(timezone.utc)
    return topic


def mark_topic_incomplete(topic: dict) -> dict:
    """Undo topic completion and its recorded completion time."""
    topic["completed"] = False
    topic["completed_at"] = None
    return topic


def save_topic(tx, topic: dict) -> dict:
    return tx.update("topics", topic["id"], {"completed": topic["completed"], "completed_at": topic["completed_at"]})
