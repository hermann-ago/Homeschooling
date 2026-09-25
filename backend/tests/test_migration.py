import hashlib
import json
import sqlite3

from migration.backup import verify
from migration.common import Report
from migration.import_history import import_history
from migration.import_hosted import import_export
from migration.reconcile import reconcile_history, reconcile_hosted
from storage import Store
from storage.backups import create_backup
from tests.migration_fixtures import build_history_folder, build_hosted_export


def migrate(harness, tmp_path, drive_has_book=True):
    source = harness.drive / "Lucas - History"
    history = build_history_folder(source)
    if drive_has_book:
        harness.add_file(history["book"], "Books/Story of the World V.2.pdf")
    export = build_hosted_export(tmp_path / "export", history["book"])
    store = harness.ctx.store
    hosted = import_export(store, export, Report("import-hosted"))
    imported = import_history(store, source, Report("import-history"))
    return store, history, export, hosted, imported, source


def test_hosted_export_imports_with_ids_timestamps_revisions_and_book_dedupe(harness, tmp_path):
    store, history, export, hosted, _, _ = migrate(harness, tmp_path)
    assert not hosted.conflicts, hosted.conflicts
    assert store.get("children", 2)["name"] == "Mila"
    document = store.get("documents", 3)
    assert document["file_path"] == "Books/Story of the World V.2.pdf"  # found by checksum, not copied again
    assert [p.name for p in (harness.drive / "Books").glob("*.pdf")
            if hashlib.sha256(p.read_bytes()).hexdigest() == history["book_sha"]] == ["Story of the World V.2.pdf"]
    assert document["legacy_blob_path"] == "documents/abc.pdf"
    assert store.get("completions", 4)["completed_at"].isoformat() == "2026-08-20T13:00:00+00:00"
    annotation = store.get("annotations", 7)
    assert annotation["revision"] == 4 and annotation["updated_at"].isoformat() == "2026-08-11T15:00:00+00:00"
    assert store.get("settings", "SCHOOL_YEAR_END")["value"] == "2026-12-18"
    report = reconcile_hosted(store, export, Report("reconcile"))
    assert not report.conflicts, report.conflicts
    assert report.counts["files"]["referenced"] > 0
    # Annotation strokes and enrichment content are files; the database holds references.
    assert "points" not in json.dumps(store.all("annotations"), default=str)
    assert (harness.drive / annotation["file_path"]).is_file()


def test_missing_book_is_copied_into_books(harness, tmp_path):
    store, history, *_ = migrate(harness, tmp_path, drive_has_book=False)
    document = store.get("documents", 3)
    assert document["file_path"] == "Books/Story of the World V.2.pdf" and document["source"] == "migrated"
    assert (harness.drive / document["file_path"]).read_bytes() == history["book"]
    # The History import reuses that book (same checksum) instead of adding another.
    assert sum(1 for d in store.all("documents") if d["sha256"] == history["book_sha"]) == 1


def test_history_import_preserves_unfinished_genghis_and_evidence(harness, tmp_path):
    store, history, _, _, imported, source = migrate(harness, tmp_path)
    assert [c["kind"] for c in imported.conflicts] == [], imported.conflicts
    genghis_topic = next(t for t in store.all("topics") if t["source_key"] == "C21-T01")
    # Merged with the hosted topic 40 by document and pages, not duplicated.
    assert genghis_topic["id"] == 40 and genghis_topic["completed"] is False
    assert genghis_topic["stop_before"] == "The Mongol Conquest of China"
    session = store.get("tutor_sessions", "2026-09-24-C21-T01-recovered")
    assert session["status"] == "unfinished"
    checkpoint = store.get("checkpoints", "2026-09-24-C21-T01-recovered-cp")
    assert checkpoint["next_prompt"] == "What did the man who spoke up do next?"
    assert checkpoint["observations"][1]["revision"] == "they coudl oncquor way more"
    assert "im ready" in checkpoint["basis"]
    q4 = store.get("attempts", "2026-09-11-01-Q04")
    assert q4["first_answer"] == "The forest of England" and q4["revised_answer"] == "Forest of Nottingham"
    assert q4["independence"] == "with_help"
    q1 = store.get("attempts", "2026-09-11-01-Q01")
    assert q1["independence"] == "independent"
    # Evidence photos are copied into Student Work; the originals stay in the History folder.
    assert q1["evidence_paths"] == ["Student Work/2026-09-11-01-page-71.jpg"]
    assert (harness.drive / "Student Work" / "2026-09-11-01-page-71.jpg").is_file()
    assert (source / "evidence" / "2026-09-11" / "page-71.jpg").is_file()
    assert store.get("reviews", "2026-09-14-01-R01")["status"] == "Open"
    assert any("superseded" in s for s in imported.skipped)
    # Teacher key and mapping stay teacher-only tables.
    assert store.get("teacher_keys", f"{genghis_topic['subject_id']}:19:4-4")["exception"].startswith("The key says")
    assert store.get("question_maps", f"{genghis_topic['subject_id']}:21:3")["topic_id"] == 40
    report = reconcile_history(store, source, Report("reconcile"))
    assert not report.conflicts, report.conflicts


def test_history_folder_is_never_modified(harness, tmp_path):
    source = harness.drive / "Lucas - History"
    build_history_folder(source)
    before = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
    import_history(harness.ctx.store, source, Report("import-history"))
    after = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
    assert after == before


def test_start_todays_lesson_resumes_genghis_after_migration(harness, tmp_path):
    store, *_ = migrate(harness, tmp_path)
    lucas = next(c for c in store.all("children") if c["name"] == "Lucas")
    history = next(s for s in store.find("subjects", child_id=lucas["id"]) if s["name"] == "History")
    started = harness.call("POST", "/api/tutor/sessions/start", role="tutor", key="first-integrated-lesson",
                           json={"child_id": lucas["id"], "subject_id": history["id"]}).json()
    assert started["resumed"] is True
    assert started["next_prompt"] == "What did the man who spoke up do next?"
    reader = harness.call("GET", "/api/tutor/reader", role="learner", params={
        "learner": lucas["id"], "topic": started["topic"]["topic_id"], "session": started["session_id"]}).json()
    assert reader["passage"]["status"] == "verified"
    assert reader["passage"]["images"][0]["caption"] == "(book p. 4)"
    tracks = {t["track_id"]: t for t in reader["audio"]}
    assert tracks["history:narration-5e9d-google-neural2-manifest"]["synchronized"] is True
    part = harness.call("GET", "/api/tutor/audio/history:narration-5e9d-google-neural2-manifest/parts/0",
                        role="learner")
    assert part.status_code == 200 and part.content.startswith(b"ID3")
    assert "SECRET" not in json.dumps(reader)


def test_legacy_audio_is_preserved_without_invented_timings(harness, tmp_path):
    store, *_ = migrate(harness, tmp_path)
    rabbi = store.get("audio_tracks", "history:c20-t02-clever-rabbi-google-neural2-manifest")
    assert rabbi["status"] == "legacy" and rabbi["timing"] is None
    robin = store.get("audio_tracks", "history:robin-hood-elevenlabs")
    assert robin["provider"] == "elevenlabs" and robin["status"] == "legacy"
    manifest = json.loads(harness.ctx.file_bytes(robin["manifest_path"]))
    assert [(harness.drive / t["path"]).read_bytes() for t in manifest["tracks"]] == [
        b"ID3robin-hood-elevenlabs-part-1.mp3", b"ID3robin-hood-elevenlabs-part-2.mp3"]


def test_rerunning_imports_does_not_duplicate(harness, tmp_path):
    store, history, export, _, _, source = migrate(harness, tmp_path)
    counts = {t: len(store.all(t)) for t in ("children", "topics", "attempts", "tutor_sessions", "audio_tracks")}
    files = sorted(p for p in harness.drive.rglob("*") if p.is_file())
    again = import_history(store, source, Report("again"))
    import_export(store, export, Report("again-hosted"))
    assert {t: len(store.all(t)) for t in counts} == counts
    assert sorted(p for p in harness.drive.rglob("*") if p.is_file()) == files
    assert again.skipped


def test_conflicting_topics_are_reported_not_overwritten(harness, tmp_path):
    source = harness.drive / "Lucas - History"
    history = build_history_folder(source)
    store = harness.ctx.store
    with store.transaction() as tx:
        lucas = tx.insert("children", {"name": "Lucas"})
        subject = tx.insert("subjects", {"child_id": lucas["id"], "name": "History"})
        book = tx.insert("documents", {"file_path": "Books/Story of the World V.2.pdf", "page_count": 7,
                                       "original_filename": "Story of the World V.2.pdf",
                                       "sha256": hashlib.sha256(history["book"]).hexdigest()})
        tx.insert("topics", {"subject_id": subject["id"], "title": "Mongols (AI guess)", "page_start": 3,
                             "page_end": 5, "pdf_page_offset": 2, "document_id": book["id"], "completed": True})
    report = import_history(store, source, Report("x"))
    kinds = {c["kind"] for c in report.conflicts}
    assert "topic_ambiguous" in kinds
    assert store.find("topics", title="Mongols (AI guess)")[0]["completed"] is True


def test_backup_is_verified_against_the_live_database(harness, tmp_path):
    store, *_ = migrate(harness, tmp_path)
    backup = create_backup(store, tmp_path / "backups")
    result = verify(harness.ctx, harness.drive / "Backups" / backup["name"])
    assert result["integrity"] and result["matches_live"], result
    restored = Store(harness.drive / "Backups" / backup["name"]).load()
    for table in ("children", "attempts", "checkpoints", "annotations", "passages"):
        assert restored.all(table) == store.all(table)


def test_dry_run_changes_nothing(harness, tmp_path, monkeypatch, capsys):
    from migration import dry_run
    source = harness.drive / "Lucas - History"
    history = build_history_folder(source)
    export = build_hosted_export(tmp_path / "export", history["book"])
    database = harness.config.database_path

    def snapshot():
        files = {p.relative_to(harness.drive): p.stat().st_mtime_ns for p in harness.drive.rglob("*") if p.is_file()}
        rows = sqlite3.connect(database).execute("SELECT COUNT(*) FROM operation_receipts").fetchone()[0]
        return files, rows
    before = snapshot()
    monkeypatch.setenv("HOMESCHOOLING_DATA", str(harness.config.dir))
    monkeypatch.setenv("HOMESCHOOLING_DRIVE_FOLDER", str(harness.drive))
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    code = dry_run.main(["--export", str(export)])
    output = capsys.readouterr().out
    assert snapshot() == before
    summary = json.loads(output.split("===\n", 1)[1].rsplit("Full report:", 1)[0])
    assert code == 0 and summary["clean"], summary["conflicts"]
    assert summary["counts"]["result"]["tutor_sessions"] == 3
    assert summary["counts"]["history_answers"] == {"source": 2, "database": 2}
