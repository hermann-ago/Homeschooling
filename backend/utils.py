"""
Shared utility functions for routers.
"""
from sqlalchemy.orm import Session

from models import ScheduledSlot, AppSetting
from schemas import ScheduledSlotResponse


def slot_to_response(slot: ScheduledSlot) -> ScheduledSlotResponse:
    """Convert a ScheduledSlot ORM instance to a ScheduledSlotResponse schema."""
    return ScheduledSlotResponse(
        id=slot.id,
        child_id=slot.child_id,
        subject_id=slot.subject_id,
        topic_id=slot.topic_id,
        date=slot.date,
        time_start=slot.time_start,
        time_end=slot.time_end,
        page_from=slot.page_from,
        page_to=slot.page_to,
        subject_name=slot.subject.name if slot.subject else None,
        topic_title=slot.topic.title if slot.topic else None,
        pdf_path=slot.topic.pdf_path if slot.topic else None,
        pdf_page_offset=slot.topic.pdf_page_offset if slot.topic else 0,
        is_completed=slot.completion is not None,
        completed_at=slot.completion.completed_at if slot.completion else None,
    )


# Default settings fallbacks
SETTING_DEFAULTS = {
    "SCHOOL_YEAR_START": "2026-02-01",
    "SCHOOL_YEAR_END": "2026-12-31",
}


def get_setting(db: Session, key: str) -> str:
    """Get an app setting from the database, falling back to defaults."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if setting:
        return setting.value
    return SETTING_DEFAULTS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> None:
    """Set an app setting in the database (upsert)."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    db.commit()
