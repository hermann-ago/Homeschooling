"""End-to-end acceptance scenarios from the integration plan (section 5)."""
import os
import re
from pathlib import Path
from uuid import uuid4

from tests.test_tutoring import seed_history

REPO = Path(__file__).resolve().parents[2]


def test_cached_reading_and_pending_work_survive_an_outage(harness):
    s = seed_history(harness)
    started = harness.call("POST", "/api/tutor/sessions/start", role="tutor", key="outage-start",
                           json={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    params = {"learner": s["lucas"]["id"], "topic": s["genghis"]["id"], "session": started["session_id"]}
    first = harness.call("GET", "/api/tutor/reader", role="learner", params=params).json()
    pdf = harness.call("GET", f"/api/documents/{s['book']['id']}/content", role="learner")
    # The internet goes down: Drive and Sheets are both unreachable.
    harness.drive.faults.extend(["offline"] * 20)
    harness.sheets.fail_next(*["offline"] * 3)
    assert harness.call("GET", "/api/tutor/reader", role="learner", params=params).json()["passage"] == first["passage"]
    assert harness.call("GET", f"/api/documents/{s['book']['id']}/content", role="learner").content == pdf.content
    path = f"/api/annotations/children/{s['lucas']['id']}/documents/{s['book']['id']}/pages/2"
    stroke = {"id": str(uuid4()), "color": "#111827", "width": 0.004, "points": [[0.1, 0.1], [0.2, 0.2]]}
    saved = harness.call("PUT", path, role="learner", key="offline-ink", json={"base_revision": 0, "strokes": [stroke]})
    assert saved.status_code == 200 and saved.headers["x-sync-state"] == "pending"
    checkpoint = harness.call("POST", f"/api/tutor/sessions/{started['session_id']}/checkpoint", role="tutor",
                              key="offline-cp", json={
                                  "expected_revision": started["revision"], "phase": "discussion",
                                  "next_prompt": "What did the man who spoke up do next?",
                                  "observations": [{"prompt": "What did he do with the tribes?",
                                                    "first_response": "he made all of them join together"}]})
    assert checkpoint.headers["x-sync-state"] == "pending"
    harness.restart()  # the host restarts before the internet returns
    harness.drive.faults.clear()
    harness.sheets.faults.clear()
    harness.call("POST", "/api/sync/now")
    harness.call("POST", "/api/sync/now")
    for operation in ("offline-ink", "offline-cp"):
        assert harness.call("GET", f"/api/sync/operations/{operation}").json()["state"] == "saved"
    receipts = [r[0] for r in harness.sheets.rows("Operation Receipts")[1:]]
    assert receipts.count("offline-ink") == 1 and receipts.count("offline-cp") == 1
    assert len(harness.sheets.rows("Annotation References")) == 2


def test_runtime_has_no_vercel_or_supabase_dependencies():
    runtime = [REPO / "backend", REPO / "frontend" / "src", REPO / "launcher", REPO / "tutor_mcp"]
    offenders = []
    for root in runtime:
        for path in root.rglob("*"):
            if path.suffix not in (".py", ".js", ".jsx", ".mjs", ".json") or any(
                    part in ("node_modules", "migration", "tests", "venv", ".tmp-localappdata") for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"supabase|@vercel|VERCEL|POSTGRES_URL", text):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == []
    assert not (REPO / "vercel.json").exists() and not (REPO / "api").exists()
    package = (REPO / "frontend" / "package.json").read_text()
    assert "supabase" not in package and "@vercel" not in package


def test_complete_lesson_without_hosted_configuration(harness):
    for name in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "POSTGRES_URL", "BLOB_READ_WRITE_TOKEN", "VERCEL"):
        assert not os.getenv(name)
    s = seed_history(harness)
    start = harness.call("POST", "/api/tutor/sessions/start", role="tutor", key="full-1",
                         json={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    answers = harness.call("POST", f"/api/tutor/sessions/{start['session_id']}/attempts", role="tutor", key="full-2",
                           json={"expected_revision": start["revision"], "attempts": [
                               {"question_ref": "Q1", "first_answer": "the Yakka", "first_result": "Correct"}]}).json()
    reviews = harness.call("POST", f"/api/tutor/sessions/{start['session_id']}/reviews", role="tutor", key="full-3",
                           json={"expected_revision": answers["revision"], "reviews": [
                               {"concept": "Why the united tribes were harder to defeat",
                                "evidence": "Needed a clue about fighting together"}]}).json()
    finish = harness.call("POST", f"/api/tutor/sessions/{start['session_id']}/finish", role="tutor", key="full-4",
                          json={"expected_revision": reviews["revision"], "next_topic_id": s["conquest"]["id"],
                                "learner_explained": "Explained how fear helped the Mongols win.",
                                "understanding": "With help", "complete_topic": True})
    assert finish.status_code == 200 and finish.headers["x-sync-state"] == "saved"
    assert harness.ctx.store.get("topics", s["genghis"]["id"])["understanding"] == "With help"
    assert harness.call("GET", "/api/sync/status").json()["state"] == "saved"
