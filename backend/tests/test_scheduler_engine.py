import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("POSTGRES_URL", None)

from database import Base  # noqa: E402
from models import Child, Completion, CurriculumTopic, ScheduledSlot, Subject  # noqa: E402
from services.scheduler_engine import _clear_reschedulable_slots  # noqa: E402


class ClearReschedulableSlotsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_removes_future_completed_topics_but_keeps_completed_history(self):
        today = date(2026, 8, 10)
        child = Child(name="Mila", color="#000000")
        subject = Subject(name="Language Arts", child=child)
        completed_topic = CurriculumTopic(
            title="Completed lesson",
            page_start=1,
            page_end=1,
            completed=True,
            subject=subject,
        )
        remaining_topic = CurriculumTopic(
            title="Remaining lesson",
            page_start=2,
            page_end=2,
            completed=False,
            subject=subject,
        )
        self.db.add(child)
        self.db.flush()

        def add_slot(topic, slot_date, completed):
            slot = ScheduledSlot(
                child=child,
                subject=subject,
                topic=topic,
                date=slot_date,
                time_start="09:00",
                time_end="09:30",
                page_from=topic.page_start,
                page_to=topic.page_end,
            )
            if completed:
                slot.completion = Completion()
            self.db.add(slot)
            self.db.flush()
            return slot.id

        historical_completed_id = add_slot(
            completed_topic, today - timedelta(days=1), completed=True
        )
        current_completed_id = add_slot(completed_topic, today, completed=True)
        future_completed_id = add_slot(
            completed_topic, today + timedelta(days=1), completed=True
        )
        draft_past_id = add_slot(
            remaining_topic, today - timedelta(days=1), completed=False
        )
        draft_future_id = add_slot(
            remaining_topic, today + timedelta(days=1), completed=False
        )
        future_progress_id = add_slot(
            remaining_topic, today + timedelta(days=2), completed=True
        )

        deleted = _clear_reschedulable_slots(child.id, today, self.db)

        self.assertEqual(deleted, 4)
        remaining_ids = {
            slot.id for slot in self.db.query(ScheduledSlot).order_by(ScheduledSlot.id)
        }
        self.assertEqual(
            remaining_ids,
            {historical_completed_id, future_progress_id},
        )
        self.assertNotIn(current_completed_id, remaining_ids)
        self.assertNotIn(future_completed_id, remaining_ids)
        self.assertNotIn(draft_past_id, remaining_ids)
        self.assertNotIn(draft_future_id, remaining_ids)


if __name__ == "__main__":
    unittest.main()
