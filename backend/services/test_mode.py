"""Per-browser rehearsal in the same app, with shared AI costs and reusable materials.

All ordinary transactions and file changes use a private working area. Only
prepared guides and content-addressed narration are deliberately shared.
"""
from __future__ import annotations

from contextlib import closing
from http.cookies import SimpleCookie
import json
import re
import shutil
import sqlite3
import threading
import uuid
import logging
from urllib.parse import parse_qs

from app_context import AppContext
from config import HostConfig
from dependencies import live_context, select_context, _json
from storage import DriveFolder, FileUnavailable
from storage import layout

COOKIE = "homeschooling_test"
HEADER = b"x-homeschooling-mode"


def mode_token(scope):
    headers = dict(scope.get("headers", []))
    explicit = headers.get(HEADER)
    if explicit is not None:
        return explicit.decode("ascii", errors="replace")
    query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="replace"))
    if "app_mode" in query:
        return query["app_mode"][0]
    cookies = SimpleCookie()
    try:
        cookies.load(headers.get(b"cookie", b"").decode("latin-1"))
    except Exception:
        return "live"
    return cookies[COOKIE].value if COOKIE in cookies else "live"


class TestConfig(HostConfig):
    def __init__(self, directory, live):
        super().__init__(directory)
        self.live = live
        self.values = {"drive_folder": str(self.dir / "files")}

    def get(self, key, default=None):
        if key in ("ai", "tts", "provider_balances", "port"):
            return self.live.config.get(key, default)
        return self.values.get(key, default)

    def update(self, **changes):
        if any(k in changes for k in ("ai", "tts", "provider_balances", "drive_folder", "port")):
            raise ValueError("Leave test mode to change real provider, spending or storage settings.")
        return super().update(**changes)


class TestFiles(DriveFolder):
    """Read originals; copy a file lazily before returning a path that could be edited."""
    def __init__(self, directory, live):
        super().__init__(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.local = DriveFolder(self.root)
        self.base = live.files
        self.voice_folders = {layout.for_subject(live.store, s["id"], layout.AUDIO)
                              for s in live.store.all("subjects")}
        self.deleted_dir = self.root / ".deleted"
        self.deleted = {p.read_text(encoding="utf-8") for p in self.deleted_dir.glob("*.txt")}

    def read(self, relative, sha256=None):
        path = self.local.resolve(relative)
        if relative in self.deleted:
            raise FileUnavailable("This file was removed in test mode")
        return self.local.read(relative, sha256) if path.is_file() else self.base.read(relative, sha256)

    def resolve(self, relative):
        path = self.local.resolve(relative)
        if relative in self.deleted:
            raise FileUnavailable("This file was removed in test mode")
        if not path.exists() and self.base.available:
            original = self.base.resolve(relative)
            if original.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, path)
        return path

    def write_new(self, folder, name, data):
        # Audio is immutable by content hash. Never share photos, handwriting or uploads.
        if folder in self.voice_folders and name.startswith("narration-"):
            path, sha, _ = self.base.write_new(folder, name, data)
            return path, sha, False  # A rehearsal rollback cannot delete a shared recording.
        return self.local.write_new(folder, name, data)

    def remove(self, relative):
        import hashlib
        self.local.remove(relative)
        self.deleted.add(relative)
        self.deleted_dir.mkdir(exist_ok=True)
        (self.deleted_dir / (hashlib.sha256(relative.encode()).hexdigest() + ".txt")).write_text(relative, encoding="utf-8")

    def list_pdfs(self):
        rows = {p["path"]: p for p in (self.base.list_pdfs() if self.base.available else [])}
        rows.update({p["path"]: p for p in self.local.list_pdfs()})
        return [rows[p] for p in sorted(rows) if p not in self.deleted]

    def find_by_checksum(self, sha256, size=None, suffix=".pdf"):
        found = self.local.find_by_checksum(sha256, size, suffix)
        if not found and self.base.available:
            found = self.base.find_by_checksum(sha256, size, suffix)
        return found if found not in self.deleted else None


def compatible_topic(test, topic_id):
    original = test.live.store.get("topics", topic_id)
    candidate = test.store.get("topics", topic_id)
    if not original or not candidate:
        return False
    fields = ("subject_id", "document_id", "title", "page_start", "page_end", "pdf_page_offset", "start_at", "stop_before")
    if any(original.get(k) != candidate.get(k) for k in fields):
        return False
    doc_id = original.get("document_id")
    if doc_id and test.live.store.get("documents", doc_id) != test.store.get("documents", doc_id):
        return False
    subject = test.store.get("subjects", original["subject_id"])
    real_subject = test.live.store.get("subjects", original["subject_id"])
    if subject != real_subject:
        return False
    if test.books.fingerprint(subject["id"]) != test.live.books.fingerprint(subject["id"]):
        return False
    source_passages = lambda db: sorted((p["id"], p["passage_sha256"], p["status"])
                                       for p in db.find("passages", topic_id=topic_id))
    if source_passages(test.store) != source_passages(test.live.store):
        return False
    child_id = subject["child_id"]
    if test.store.get("children", child_id) != test.live.store.get("children", child_id):
        return False
    from tutoring.skills import packet
    from tutoring.lesson_context import status
    from tutoring.family_skill import packet as family_packet
    return (packet(test.store, subject)["sha256"] == packet(test.live.store, real_subject)["sha256"]
            and status(test, subject["id"]) == status(test.live, subject["id"])
            and family_packet(test.store, child_id)['sha256'] == family_packet(test.live.store, child_id)['sha256'])


def sync_materials(test):
    shared = [(table, row) for table in ('library_book_skills', 'library_materials')
        for row in test.live.store.all(table) if not test.store.get(table, row['id'])
        and test.store.get('library_books', row['book_id'])]
    if shared:
        with test.store.transaction(kind='test.materials.library') as tx:
            for table, row in shared:
                tx.insert(table, row)
    from tutoring.skills import packet
    new_skills = [row for row in test.live.store.all("subject_skills") if not test.store.get("subject_skills", row["id"])
                  and test.store.get("subjects", row["subject_id"])
                  and packet(test.store, test.store.get("subjects", row["subject_id"]))["sha256"] == row["sha256"]]
    if new_skills:
        with test.store.transaction(kind="test.materials.skills") as tx:
            for row in new_skills:
                tx.insert("subject_skills", row)
    # Prepared materials are independent of completion, attempts, reviews and checkpoints.
    missing = [(table, row) for table in ("guides", "audio_tracks") for row in test.live.store.all(table)
               if not test.store.get(table, row["id"]) and compatible_topic(test, row["topic_id"])]
    if missing:
        with test.store.transaction(kind="test.materials") as tx:
            for table, row in missing:
                tx.insert(table, row)
    # Only source/preparation artifacts are shared, never learner evidence.
    notes=[r for r in test.live.store.all('source_annotations') if not test.store.get('source_annotations',r['id'])
        and any(d['sha256']==r['document_sha256'] for d in test.store.all('documents'))]
    reports=[r for r in test.live.store.all('lesson_script_reviews') if not test.store.get('lesson_script_reviews',r['id'])
        and test.store.get('guides',r['guide_id'])]
    if notes or reports:
        with test.store.transaction(kind='test.materials.review') as tx:
            for r in notes:tx.insert('source_annotations',r)
            for r in reports:tx.insert('lesson_script_reviews',r)


def publish_audio(test):
    missing = [row for row in test.store.all("audio_tracks")
               if not test.live.store.get("audio_tracks", row["id"]) and compatible_topic(test, row["topic_id"])]
    for row in missing:
        manifest = json.loads(test.file_bytes(row["manifest_path"]))
        paths = [row["manifest_path"], *[part["path"] for part in manifest.get("tracks", []) if not part.get("fallback")]]
        # Local-only audio (e.g. a newly invented learner) is not a real lesson cache.
        if not all(test.live.files.resolve(path).is_file() for path in paths):
            continue
        with test.live.store.transaction(kind="materials.audio_cache") as tx:
            if not tx.get("audio_tracks", row["id"]):
                tx.insert("audio_tracks", row)


class TestModes:
    def __init__(self, live):
        self.live = live
        self.directory = live.config.dir / "test-mode"
        self.contexts = {}
        self.lock = threading.RLock()

    def create(self):
        token = uuid.uuid4().hex
        directory = self.directory / token
        directory.mkdir(parents=True)
        with closing(sqlite3.connect(self.live.store.path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(directory / "homeschooling.sqlite3")) as copy:
                source.backup(copy)
                copy.execute("UPDATE book_imports SET status='failed', error='Paused in test mode; resume explicitly if needed' WHERE status IN ('queued','running')")
                copy.execute("UPDATE lesson_preparation_jobs SET status='paused', error='Copied into test mode. Prepare explicitly in this mode if needed.' WHERE status IN ('queued','running')")
                # Shared ledger scopes must never let a rehearsal pause/resume a
                # real in-flight job. Saved checkpoints remain reusable.
                partial_jobs = copy.execute("SELECT id FROM collection_analysis_jobs WHERE status NOT IN ('ready','needs_review')").fetchall()
                for (source_id,) in partial_jobs:
                    # A separate, read-only identity exposes saved partial maps for
                    # rehearsal without borrowing the real job's ledger controls.
                    snapshot_id = "rehearsal-source-" + uuid.uuid4().hex
                    copy.execute("UPDATE subject_maps SET job_id=? WHERE job_id=?", (snapshot_id, source_id))
                    copy.execute("UPDATE collection_analysis_jobs SET id=?,status='snapshot',rehearsal_snapshot=1,source_job_id=?,error='Read-only test snapshot. Continue the original analysis in normal mode.' WHERE id=?",
                                 (snapshot_id, source_id, source_id))
                copy.commit()
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("The test working area failed its integrity check")
        (directory / "active").write_text("yes")
        self.get(token)
        return token

    def get(self, token):
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Invalid test session. Reload the app before continuing.")
        directory = self.directory / token
        if not (directory / "active").is_file():
            raise ValueError("This test session has ended. Reload the app before continuing.")
        with self.lock:
            if token not in self.contexts:
                config = TestConfig(directory, self.live)
                ctx = AppContext(config, start_worker=False, live=self.live, files=TestFiles(directory / "files", self.live))
                from tutoring.books import ImportWorker
                ctx.import_worker = ImportWorker(ctx.books)
                ctx.import_worker.start()
                from tutoring.subject_analysis import AnalysisWorker
                ctx.analysis_worker = AnalysisWorker(ctx.subject_analysis)
                ctx.analysis_worker.start()
                self.contexts[token] = ctx
            ctx = self.contexts[token]
            sync_materials(ctx)
            return ctx

    def end(self, token):
        ctx = self.get(token)
        ctx.import_worker.stop()
        if ctx.analysis_worker:
            ctx.analysis_worker.stop()
        (ctx.config.dir / "active").unlink()
        # Keep the private working area for recovery; never merge its learner records.

    def shutdown(self):
        for ctx in self.contexts.values():
            ctx.shutdown()


def manager(live):
    if not hasattr(live, "test_modes"):
        live.test_modes = TestModes(live)
    return live.test_modes


class TestModeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        root = live_context()
        token = mode_token(scope)
        async def mode_safe_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"vary", b"X-Homeschooling-Mode, Cookie"))
                message = {**message, "headers": headers}
            await send(message)
        if token == "live" or scope["path"] == "/api/test-mode":
            return await self.app(scope, receive, mode_safe_send)
        path = scope["path"]
        protected = path.startswith(("/api/host/", "/api/pairing/")) or (scope["method"] != "GET" and
            (path.startswith("/api/ai/") or path == "/api/storage/drive-folder"))
        if protected:
            return await _json(send, 400, {"detail": "Leave test mode before changing real keys, spending or host settings."})
        try:
            ctx = manager(root).get(token)
        except ValueError as exc:
            return await _json(send, 409, {"detail": str(exc)})
        with select_context(ctx):
            await self.app(scope, receive, mode_safe_send)
            try:
                publish_audio(ctx)
            except Exception:
                logging.getLogger(__name__).exception("Could not index a reusable test narration; its saved parts remain cached")
