"""The usage ledger also records how long each provider call took."""
import sqlite3
from datetime import datetime, timedelta, timezone

from services.ai_budget import BudgetLedger


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def seconds(path, request_id):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT seconds FROM requests WHERE id=?", (request_id,)).fetchone()[0]


def test_a_call_records_the_time_from_sending_to_its_reply(tmp_path):
    clock = Clock()
    ledger = BudgetLedger(tmp_path / "usage.sqlite3", clock)
    for request_id in ("answered", "failed"):
        ledger.reserve(request_id, "teaching", 1000, {}, provider="openai", model="fast", operation="Assessment")
    clock.now += timedelta(seconds=2.4)
    ledger.settle("answered", 300, {"output_tokens": 80})
    clock.now += timedelta(seconds=10)
    ledger.mark("failed", "uncertain")
    assert seconds(tmp_path / "usage.sqlite3", "answered") == 2.4
    assert seconds(tmp_path / "usage.sqlite3", "failed") == 12.4


def test_an_older_ledger_gains_the_column_and_keeps_its_records(tmp_path):
    path = tmp_path / "usage.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE requests (id TEXT PRIMARY KEY, month TEXT NOT NULL, category TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL, operation TEXT NOT NULL, reserved INTEGER NOT NULL,
            charged INTEGER NOT NULL, status TEXT NOT NULL, usage TEXT, created_at TEXT NOT NULL)""")
        db.execute("INSERT INTO requests VALUES ('old','2026-10','teaching','openai','m','Review',5,5,'completed',NULL,'2026-10-01T00:00:00+00:00')")
    ledger = BudgetLedger(path, Clock())
    assert seconds(path, "old") is None
    ledger.reserve("new", "voice", 10, {}, provider="inworld", model="flash", operation="narration")
    ledger.settle("new", 5)
    assert seconds(path, "new") == 0.0
