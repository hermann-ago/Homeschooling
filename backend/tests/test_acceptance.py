"""End-to-end acceptance scenarios from the integration plan (section 5)."""
import os
import re
from pathlib import Path
from uuid import uuid4

from tests.test_tutoring import seed_history

REPO = Path(__file__).resolve().parents[2]


def test_reading_and_work_continue_without_internet(harness):
    """The server needs no internet: the database is local and Drive files are on disk."""
    s = seed_history(harness)
    started = harness.call("POST", "/api/tutor/sessions/start", role="tutor", key="outage-start",
                           json={"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"]}).json()
    params = {"learner": s["lucas"]["id"], "topic": s["genghis"]["id"], "session": started["session_id"]}
    draft = harness.call("GET", "/api/tutor/context", role="tutor", params={
        "child_id": s["lucas"]["id"], "subject_id": s["history"]["id"], "phase": "reading"}).json()["reading"]
    harness.call("POST", f"/api/tutor/passages/{s['genghis']['id']}/review", role="tutor", json={
        "reviewed_pdf_pages": [2, 3], "notes": "Checked both pages", "passage_sha256": draft["passage_sha256"]})
    first = harness.call("GET", "/api/tutor/reader", role="learner", params=params).json()
    assert first["passage"]["status"] == "verified"
    import socket
    real_connect = socket.socket.connect

    def offline(*args, **kwargs):
        raise OSError("network is down")
    socket.socket.connect = offline
    try:
        assert harness.call("GET", "/api/tutor/reader", role="learner", params=params).json()["passage"] == first["passage"]
        assert harness.call("GET", f"/api/documents/{s['book']['id']}/content", role="learner").status_code == 200
        path = f"/api/annotations/children/{s['lucas']['id']}/documents/{s['book']['id']}/pages/2"
        stroke = {"id": str(uuid4()), "color": "#111827", "width": 0.004, "points": [[0.1, 0.1], [0.2, 0.2]]}
        saved = harness.call("PUT", path, role="learner", key="offline-ink",
                             json={"base_revision": 0, "strokes": [stroke]})
        assert saved.status_code == 200 and saved.headers["x-sync-state"] == "saved"
        checkpoint = harness.call("POST", f"/api/tutor/sessions/{started['session_id']}/checkpoint", role="tutor",
                                  key="offline-cp", json={
                                      "expected_revision": started["revision"], "phase": "discussion",
                                      "next_prompt": "What did the man who spoke up do next?",
                                      "observations": [{"prompt": "What did he do with the tribes?",
                                                        "first_response": "he made all of them join together"}]})
        assert checkpoint.headers["x-sync-state"] == "saved"
    finally:
        socket.socket.connect = real_connect
    harness.restart()
    for operation in ("offline-ink", "offline-cp"):
        assert harness.call("GET", f"/api/sync/operations/{operation}").json()["state"] == "saved"
    receipts = [r["id"] for r in harness.ctx.store.all("operation_receipts")]
    assert receipts.count("offline-ink") == 1 and receipts.count("offline-cp") == 1
    assert len(harness.ctx.store.all("annotations")) == 1


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
    assert harness.call("GET", "/api/storage/status").json()["state"] == "saved"


def test_missing_drive_folder_is_reported_not_fatal(harness, tmp_path):
    harness.config.update(drive_folder=str(tmp_path / "unplugged"))
    harness.restart()
    status = harness.call("GET", "/api/storage/status").json()
    assert status["drive_folder_available"] is False
    assert harness.call("GET", "/api/children").status_code == 200  # the database still works
    assert harness.call("GET", "/api/documents/drive/books").status_code == 503
