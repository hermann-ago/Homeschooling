"""Measurements for the live tutor plan (docs/plans/LIVE_TUTOR_PLAN.md). Read-only, no API calls.

    python tools/live_tutor.py waits [--since 2026-11-01]
        How long provider calls took, by kind (recorded from 2026-11-11 on).

    python tools/live_tutor.py replies [--since 2026-11-01]
        The wait a child felt in past lessons: from sending an answer or a
        question to the tutor's reply appearing, taken from the saved lesson.

    python tools/live_tutor.py transcript --session 2026-11-06-c1-01 --out ../tmp/live-tutor/before.md
        One lesson as it was taught: every prepared and live line with the
        child's answers. Output holds learner records: keep it under tmp/.
"""
import argparse
import json
import sqlite3
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import HostConfig  # noqa: E402


def _open(name):
    db = sqlite3.connect(f"file:{(HostConfig().dir / name).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _summary(values):
    values = sorted(values)
    return {"n": len(values), "median": round(statistics.median(values), 1),
            "p90": round(values[min(len(values) - 1, int(len(values) * 0.9))], 1), "max": round(values[-1], 1)}


def _table(rows, headers):
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(len(headers))]
    for row in [headers, *rows]:
        print("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)))


def waits(since):
    groups = {}
    with _open("ai-usage.sqlite3") as db:
        timed = "seconds" in [row[1] for row in db.execute("PRAGMA table_info(requests)")]
        for row in db.execute("SELECT category, model, operation, seconds FROM requests "
                              "WHERE seconds IS NOT NULL AND status='completed' AND created_at>=?", (since,)) if timed else ():
            groups.setdefault((row["category"], row["operation"], row["model"]), []).append(row["seconds"])
    if not groups:
        print("No timed calls yet: durations are recorded from the first call after this tool was added.")
        return
    rows = [(c, o, m, *(_summary(v)[k] for k in ("n", "median", "p90", "max"))) for (c, o, m), v in sorted(groups.items())]
    _table(rows, ("kind", "operation", "model", "calls", "median s", "p90 s", "longest s"))


def _reply_waits(db, session_id):
    """Seconds between each learner message and the teacher message that follows it in the same step."""
    found, asked = [], {}
    for message in db.execute("SELECT action_id, role, created_at FROM lesson_dialogue WHERE session_id=? ORDER BY sequence", (session_id,)):
        if message["role"] == "student":
            asked[message["action_id"]] = message["created_at"]
        elif message["role"] == "teacher" and message["action_id"] in asked:
            sent = asked.pop(message["action_id"])
            found.append((datetime.fromisoformat(message["created_at"].replace("Z", "+00:00"))
                          - datetime.fromisoformat(sent.replace("Z", "+00:00"))).total_seconds())
    return found


def replies(since):
    with _open("homeschooling.sqlite3") as db:
        names = {row["id"]: row["name"] for row in db.execute("SELECT id, name FROM children")}
        rows, everything = [], []
        for session in db.execute("SELECT s.id, s.child_id, t.title FROM tutor_sessions s JOIN topics t ON t.id=s.topic_id "
                                  "WHERE s.date>=? ORDER BY s.id", (since,)):
            found = _reply_waits(db, session["id"])
            if found:
                everything += found
                rows.append((session["id"], names.get(session["child_id"]), session["title"][:38], *(_summary(found)[k] for k in ("n", "median", "p90", "max"))))
    if not rows:
        print("No live replies in that period.")
        return
    _table(rows, ("lesson", "learner", "title", "replies", "median s", "p90 s", "longest s"))
    total = _summary(everything)
    print(f"\nAll {total['n']} replies: median {total['median']} s, 9 in 10 within {total['p90']} s, longest {total['max']} s.")
    # A reply within a second was checked by the app against the key, without an AI call.
    slow = [v for v in everything if v > 1]
    print(f"Checked by the app at once: {len(everything) - len(slow)}.")
    if slow:
        ai = _summary(slow)
        print(f"Written by the AI: {ai['n']} replies, median {ai['median']} s, 9 in 10 within {ai['p90']} s; "
              f"{sum(v <= 3 for v in slow)} within 3 s.")


def transcript(session_id, out):
    with _open("homeschooling.sqlite3") as db:
        session = db.execute("SELECT s.*, t.title, c.name FROM tutor_sessions s JOIN topics t ON t.id=s.topic_id "
                             "JOIN children c ON c.id=s.child_id WHERE s.id=?", (session_id,)).fetchone()
        if not session:
            raise SystemExit(f"No lesson {session_id}")
        lines = [f"# {session['title']} — {session['name']}, {session['date']} ({session_id})", "",
                 "PREPARED lines were written before the lesson; LIVE lines were written during it.", ""]
        steps = db.execute("SELECT action_id, activity_kind, origin, prompt, status FROM lesson_actions WHERE session_id=? "
                           "ORDER BY activity_order, rowid", (session_id,)).fetchall()
        waits_found = _reply_waits(db, session_id)
        prepared = live = 0
        for number, step in enumerate(steps, 1):
            planned = step["origin"] == "required_book" or not step["action_id"].startswith(("question-", "follow-up", "support-"))
            lines += [f"## {number}. {step['activity_kind']} · {step['status']}", "",
                      f"**{'PREPARED' if planned else 'LIVE'} tutor:** {(step['prompt'] or '').strip()}", ""]
            prepared += planned
            live += not planned
            sent = result = None
            for message in db.execute("SELECT role, text, assessment, created_at FROM lesson_dialogue WHERE session_id=? AND action_id=? "
                                      "ORDER BY sequence", (session_id, step["action_id"])):
                if message["role"] == "student":
                    sent = message["created_at"]
                    # The grade is saved with the child's message it judges.
                    result = (json.loads(message["assessment"]) if message["assessment"] else {}).get("result")
                    lines += [f"**Child:** {(message['text'] or '(photo)').strip()}", ""]
                else:
                    live += 1
                    wait = ""
                    if sent:
                        wait = f", after {(datetime.fromisoformat(message['created_at'].replace('Z', '+00:00')) - datetime.fromisoformat(sent.replace('Z', '+00:00'))).total_seconds():.0f} s"
                        sent = None
                    lines += [f"**LIVE tutor** ({result or 'reply'}{wait}): {(message['text'] or '').strip()}", ""]
        lines += ["---", f"{prepared} prepared lines, {live} live lines."
                  + (f" Live reply waits: median {_summary(waits_found)['median']} s, longest {_summary(waits_found)['max']} s." if waits_found else "")]
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{target}: {len(steps)} steps, {prepared} prepared and {live} live tutor lines")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("waits", "replies"):
        commands.add_parser(name).add_argument("--since", default="2026-11-01")
    one = commands.add_parser("transcript")
    one.add_argument("--session", required=True)
    one.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "waits":
        waits(args.since)
    elif args.command == "replies":
        replies(args.since)
    else:
        transcript(args.session, args.out)


if __name__ == "__main__":
    main()
