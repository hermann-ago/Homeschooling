import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("POSTGRES_URL", None)

from services.completion_tracking import (  # noqa: E402
    mark_topic_completed,
    mark_topic_incomplete,
)


class CompletionTrackingTests(unittest.TestCase):
    def test_completion_time_is_automatic_and_cleared_when_undone(self):
        topic = SimpleNamespace(completed=False, completed_at=None)
        recorded_at = datetime(2026, 8, 10, 14, 30, tzinfo=timezone.utc)

        mark_topic_completed(topic, recorded_at)

        self.assertTrue(topic.completed)
        self.assertEqual(topic.completed_at, recorded_at)

        mark_topic_incomplete(topic)

        self.assertFalse(topic.completed)
        self.assertIsNone(topic.completed_at)

    def test_repeated_completion_keeps_the_original_time(self):
        first_time = datetime(2026, 8, 10, 14, 30, tzinfo=timezone.utc)
        topic = SimpleNamespace(completed=True, completed_at=first_time)

        mark_topic_completed(
            topic,
            datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(topic.completed_at, first_time)


if __name__ == "__main__":
    unittest.main()
