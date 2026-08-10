import os
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("POSTGRES_URL", None)

from database import Base  # noqa: E402
from models import Child, Completion, CurriculumTopic, ScheduledSlot, Subject  # noqa: E402
from routers.calendar import list_standalone_topic_completions  # noqa: E402


class CalendarCompletionActivityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_only_returns_completions_without_calendar_history(self):
        owner_id = "13b98596-cb1b-4c30-9228-6f44b9149783"
        recorded_at = datetime(2026, 8, 10, 14, 30, tzinfo=timezone.utc)
        child = Child(owner_id=owner_id, name="Mila", color="#000000")
        subject = Subject(name="Language Arts", child=child)
        standalone = CurriculumTopic(
            title="Ahead chapter",
            page_start=1,
            page_end=2,
            completed=True,
            completed_at=recorded_at,
            subject=subject,
        )
        represented = CurriculumTopic(
            title="Scheduled chapter",
            page_start=3,
            page_end=4,
            completed=True,
            completed_at=recorded_at,
            subject=subject,
        )
        slot = ScheduledSlot(
            child=child,
            subject=subject,
            topic=represented,
            date=date(2026, 8, 10),
            time_start="09:00",
            time_end="09:30",
            page_from=3,
            page_to=4,
            completion=Completion(),
        )
        self.db.add_all([standalone, slot])
        self.db.commit()

        activities = list_standalone_topic_completions(
            child.id,
            user_id=owner_id,
            db=self.db,
        )

        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].topic_id, standalone.id)
        self.assertEqual(activities[0].topic_title, "Ahead chapter")


if __name__ == "__main__":
    unittest.main()
