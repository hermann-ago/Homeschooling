"""Atomic, durable reservations independent of lesson database transactions.

Money is stored as integer millionths of USD. Sent requests without known usage
stay charged at their reservation, including across restarts and month changes.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_LIMITS = {"teaching": 3, "books": 2, "voice": 2}


class BudgetError(ValueError):
    pass


def local_month(moment=None):
    try:
        zone = ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:  # bootstrap before tzdata is installed on Windows
        zone = timezone(timedelta(hours=-3))
    return (moment or datetime.now(timezone.utc)).astimezone(zone).strftime("%Y-%m")


def micros(dollars):
    return int((Decimal(str(dollars)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def token_cost(input_tokens, output_tokens, input_rate, output_rate):
    # Rates are USD per million tokens; the result is micro-USD.
    return int((Decimal(input_tokens) * Decimal(str(input_rate)) +
                Decimal(output_tokens) * Decimal(str(output_rate))).to_integral_value(rounding=ROUND_CEILING))


class BudgetLedger:
    def __init__(self, path: Path, clock=None):
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, month TEXT NOT NULL, category TEXT NOT NULL,
                provider TEXT NOT NULL, model TEXT NOT NULL, operation TEXT NOT NULL,
                reserved INTEGER NOT NULL, charged INTEGER NOT NULL, status TEXT NOT NULL,
                usage TEXT, created_at TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS request_month ON requests(month,category)")
            db.execute("CREATE TABLE IF NOT EXISTS narration_parts (id TEXT PRIMARY KEY, metadata TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS ai_results (id TEXT PRIMARY KEY, text TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS ai_outcomes (request_id TEXT PRIMARY KEY, cache_id TEXT, metadata TEXT NOT NULL, text TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS outcome_cache ON ai_outcomes(cache_id)")
            db.execute("CREATE TABLE IF NOT EXISTS narration_jobs (id TEXT PRIMARY KEY, metadata TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS generation_scopes (id TEXT PRIMARY KEY, category TEXT NOT NULL, maximum INTEGER NOT NULL, enabled INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS request_scopes (request_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS request_scope ON request_scopes(scope_id)")
            db.execute("CREATE TABLE IF NOT EXISTS voice_provider_calls (request_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, sent_at REAL NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, request_id, category, maximum, limits, *, provider, model, operation, scope_id=None):
        if category not in DEFAULT_LIMITS or not isinstance(maximum, int) or maximum < 1:
            raise BudgetError("Invalid spending reservation; no request sent")
        month = local_month(self.clock())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior and prior[0] != "rejected":
                raise BudgetError("This request was already sent. Its recording or usage must be reconciled before retrying.")
            if prior:
                db.execute("DELETE FROM requests WHERE id=?", (request_id,))
                db.execute("DELETE FROM request_scopes WHERE request_id=?", (request_id,))
            if scope_id:
                scope = db.execute("SELECT category,maximum,enabled FROM generation_scopes WHERE id=?", (scope_id,)).fetchone()
                if not scope or scope[0] != category or not scope[2]:
                    raise BudgetError("This preparation job is paused. No generation sent.")
            # Reservations track potential charges and prevent duplicate sends.
            # Provider billing controls spending; legacy app caps are not enforced.
            db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (request_id, month, category, provider, model, operation, maximum, maximum,
                        "reserved", None, self.clock().isoformat()))
            if scope_id:
                db.execute("INSERT INTO request_scopes VALUES (?,?)", (request_id, scope_id))
        return month

    def configure_scope(self, scope_id, maximum, category="books", enabled=True):
        if category not in DEFAULT_LIMITS or not isinstance(maximum, int) or maximum < 1:
            raise BudgetError("Choose a positive job spending limit")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO generation_scopes VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET maximum=excluded.maximum,enabled=excluded.enabled",
                       (scope_id, category, maximum, int(enabled)))

    def enable_scope(self, scope_id, enabled):
        with self.connect() as db:
            db.execute("UPDATE generation_scopes SET enabled=? WHERE id=?", (int(enabled), scope_id))

    def scope_summary(self, scope_id):
        with self.connect() as db:
            spent, uncertain = db.execute("SELECT COALESCE(SUM(r.charged),0),COALESCE(SUM(CASE WHEN r.status IN ('reserved','uncertain') THEN r.charged ELSE 0 END),0) FROM requests r JOIN request_scopes s ON s.request_id=r.id WHERE s.scope_id=?", (scope_id,)).fetchone()
        return {"tracking_only": True, "maximum_usd": None, "used_usd": spent / 1_000_000,
                "uncertain_usd": uncertain / 1_000_000, "remaining_usd": None}

    def settle(self, request_id, actual, usage=None):
        import json
        if not isinstance(actual, int) or actual < 0:
            raise BudgetError("Invalid provider usage; reservation retained")
        with self.connect() as db:
            db.execute("UPDATE requests SET charged=?, status='completed', usage=? WHERE id=?",
                       (actual, json.dumps(usage or {}), request_id))

    def mark(self, request_id, status):
        if status not in ("uncertain", "rejected"):
            raise BudgetError("Invalid request status")
        with self.connect() as db:
            db.execute("UPDATE requests SET status=?, charged=CASE WHEN ?='rejected' THEN 0 ELSE charged END WHERE id=?",
                       (status, status, request_id))

    def summary(self, limits):
        month = local_month(self.clock())
        with self.connect() as db:
            rows = db.execute("SELECT category,SUM(charged),SUM(CASE WHEN status IN ('reserved','uncertain') THEN charged ELSE 0 END) "
                              "FROM requests WHERE month=? GROUP BY category", (month,)).fetchall()
        totals = {r[0]: r[1:] for r in rows}
        summary = {"month": month, "currency": "USD", "tracking_only": True, "categories": {
            cat: {"limit_usd": None, "used_usd": totals.get(cat, (0, 0))[0] / 1_000_000,
                  "uncertain_usd": totals.get(cat, (0, 0))[1] / 1_000_000,
                  "remaining_usd": None}
            for cat in DEFAULT_LIMITS}}
        return summary

    def backup(self, destination):
        target = sqlite3.connect(destination)
        try:
            with self.connect() as source:
                source.backup(target)
        finally:
            target.close()

    def requests(self, uncertain_only=False):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT id,month,category,provider,model,operation,charged,status,created_at FROM requests " +
                              ("WHERE status IN ('reserved','uncertain') " if uncertain_only else "") +
                              "ORDER BY created_at DESC LIMIT 100").fetchall()
        return [{**dict(r), "charged_usd": r["charged"] / 1_000_000} for r in rows]

    def reconcile(self, request_id, actual):
        import json
        if not isinstance(actual, int) or actual < 0:
            raise BudgetError("Invalid charge; reservation retained")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
            if not row or row[0] != "uncertain":
                raise BudgetError("Only uncertain requests can be reconciled against a provider bill")
            db.execute("UPDATE requests SET charged=?,status=?,usage=? WHERE id=?",
                       (actual, "completed" if actual else "rejected", json.dumps({"source": "parent_verified_provider_bill"}), request_id))

    def recover_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE requests SET status='uncertain' WHERE status='reserved'")
        for job in self.jobs():
            if job["status"] in ("running", "queued"):
                job.update(status="paused", error="Interrupted by a server restart. Completed passages are saved.")
                self.save_job(job["id"], job)

    def save_job(self, job_id, metadata):
        import json
        with self.connect() as db:
            db.execute("INSERT INTO narration_jobs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata",
                       (job_id, json.dumps(metadata)))

    def jobs(self):
        import json
        with self.connect() as db:
            rows = db.execute("SELECT id,metadata FROM narration_jobs").fetchall()
        return [{"id": row[0], **json.loads(row[1])} for row in rows]

    def voice_cost(self, key):
        import json
        with self.connect() as db:
            job = db.execute("SELECT metadata FROM narration_jobs WHERE id=?", (key,)).fetchone()
            metadata = json.loads(job[0]) if job else {}
            if "request_ids" in metadata:
                return sum((db.execute("SELECT charged FROM requests WHERE id=?", (rid,)).fetchone() or (0,))[0]
                           for rid in set(metadata["request_ids"])) / 1_000_000
            return db.execute("SELECT COALESCE(SUM(charged),0) FROM requests WHERE id LIKE ?",
                              (f"voice:{key}:%",)).fetchone()[0] / 1_000_000

    def request_state(self, request_id):
        with self.connect() as db:
            row = db.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
        return row[0] if row else None

    def part(self, part_id):
        import json
        with self.connect() as db:
            row = db.execute("SELECT metadata FROM narration_parts WHERE id=?", (part_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_part(self, part_id, metadata):
        import json
        with self.connect() as db:
            db.execute("INSERT INTO narration_parts VALUES (?,?)", (part_id, json.dumps(metadata)))

    def replace_part(self, part_id, metadata):
        """Attach checked alignment to an existing raw purchase, retaining its bytes."""
        import json
        with self.connect() as db:
            previous = db.execute('SELECT metadata FROM narration_parts WHERE id=?', (part_id,)).fetchone()
            if not previous:
                raise BudgetError('The saved audio block is missing')
            old = json.loads(previous[0])
            if any(old.get(key) != metadata.get(key) for key in ('path', 'sha256', 'script_sha256')):
                raise BudgetError('Alignment cannot replace the purchased recording or script')
            db.execute('UPDATE narration_parts SET metadata=? WHERE id=?', (json.dumps(metadata), part_id))

    def claim_voice_slot(self, request_id, provider, model, *, dry_run=False):
        """Pace voice requests without imposing a local daily or spending cap."""
        now = self.clock()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            recent = db.execute('SELECT sent_at FROM voice_provider_calls WHERE provider=? AND model=? AND sent_at>? ORDER BY sent_at',
                                (provider, model, now.timestamp()-61)).fetchall()
            recent += [(datetime.fromisoformat(r[0]).timestamp(),) for r in db.execute(
                "SELECT created_at FROM requests r WHERE category='voice' AND provider=? AND model=? AND created_at>? AND id!=? AND NOT EXISTS (SELECT 1 FROM voice_provider_calls c WHERE c.request_id=r.id)",
                (provider, model, (now-timedelta(seconds=61)).isoformat(), request_id)).fetchall()]
            recent.sort()
            if len(recent) >= 9:
                return max(.1, recent[-9][0]+61-now.timestamp())
            if not dry_run:
                db.execute('INSERT INTO voice_provider_calls VALUES (?,?,?,?)', (request_id, provider, model, now.timestamp()))
        return 0

    def result(self, request_id):
        with self.connect() as db:
            row = db.execute("SELECT text FROM ai_results WHERE id=?", (request_id,)).fetchone()
        return row[0] if row else None

    def save_outcome(self, request_id, cache_id, metadata, text):
        import json
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO ai_outcomes VALUES (?,?,?,?)',
                       (request_id,cache_id,json.dumps(metadata),text))

    def outcome(self, identity):
        import json
        with self.connect() as db:
            row=db.execute('SELECT request_id,metadata,text FROM ai_outcomes WHERE request_id=? OR cache_id=? ORDER BY rowid DESC LIMIT 1',
                           (identity,identity)).fetchone()
        return {'request_id':row[0],**json.loads(row[1]),'text':row[2]} if row else None

    def completed(self, request_id):
        with self.connect() as db:
            row = db.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
        return bool(row and row[0] == "completed")

    def save_result(self, request_id, text):
        with self.connect() as db:
            db.execute("INSERT INTO ai_results VALUES (?,?)", (request_id, text))
