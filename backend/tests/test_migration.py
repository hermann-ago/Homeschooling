import json

from migration.backup import create_backup, restore_into
from migration.common import Report
from migration.import_history import DriveIndex, import_history
from migration.import_hosted import import_export
from migration.reconcile import reconcile_history, reconcile_hosted
from storage import FakeSheets, Store
from tests.migration_fixtures import build_history_folder, build_hosted_export


def migrate(harness, tmp_path, drive_has_book=True):
    history = build_history_folder(tmp_path / "Lucas - History")
    if drive_has_book:
        harness.drive.add_file(history["book"], "Story of the World V.2", file_id="1jX_ifE9DFGivsDeXCdOm8i5EsqgTiP_T")
    export = build_hosted_export(tmp_path / "export", history["book"])
    store = harness.ctx.store
    hosted = import_export(store, harness.drive, export, Report("import-hosted"))
    index = DriveIndex(history["drive_paths"])
    imported = import_history(store, tmp_path / "Lucas - History", index, Report("import-history"))
    store.flush(max_ops=10_000)
    return store, history, export, hosted, imported, index


def test_hosted_export_imports_with_ids_timestamps_revisions_and_book_dedupe(harness, tmp_path):
    store, history, export, hosted, _, _ = migrate(harness, tmp_path)
    assert not hosted.conflicts, hosted.conflicts
    assert store.get("children", 2)["name"] == "Mila"
    document = store.get("documents", 3)
    assert document["drive_file_id"] == "1jX_ifE9DFGivsDeXCdOm8i5EsqgTiP_T"  # existing Drive book, not re-uploaded
    assert document["legacy_blob_path"] == "documents/abc.pdf"
    assert store.get("completions", 4)["completed_at"].isoformat() == "2026-08-20T13:00:00+00:00"
    annotation = store.get("annotations", 7)
    assert annotation["revision"] == 4 and annotation["updated_at"].isoformat() == "2026-08-11T15:00:00+00:00"
    assert store.get("settings", "SCHOOL_YEAR_END")["value"] == "2026-12-18"
    report = reconcile_hosted(store, export, Report("reconcile"), harness.drive)
    assert not report.conflicts, report.conflicts
    assert store.status()["state"] == "saved"
    # Annotation strokes and enrichment content live in Drive, not in cells.
    assert all("points" not in c for r in harness.sheets.rows("Annotation References") for c in r)


def test_history_import_preserves_unfinished_genghis_and_evidence(harness, tmp_path):
    store, history, _, _, imported, _ = migrate(harness, tmp_path)
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
    assert store.get("attempts", "2026-09-11-01-Q01")["independence"] == "independent"
    assert store.get("attempts", "2026-09-11-01-Q01")["evidence_file_ids"] == ["photoFileId0001"]
    assert store.get("reviews", "2026-09-14-01-R01")["status"] == "Open"
    assert any("superseded" in s for s in imported.skipped)
    # Teacher key and mapping stay teacher-only tabs.
    assert store.get("teacher_keys", f"{genghis_topic['subject_id']}:19:4-4")["exception"].startswith("The key says")
    assert store.get("question_maps", f"{genghis_topic['subject_id']}:21:3")["topic_id"] == 40
    report = reconcile_history(store, tmp_path / "Lucas - History", Report("reconcile"))
    assert not report.conflicts, report.conflicts


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
    assert "SECRET" not in json.dumps(reader)


def test_legacy_audio_is_preserved_without_invented_timings(harness, tmp_path):
    store, *_ = migrate(harness, tmp_path)
    rabbi = store.get("audio_tracks", "history:c20-t02-clever-rabbi-google-neural2-manifest")
    assert rabbi["status"] == "legacy" and rabbi["timing"] is None
    robin = store.get("audio_tracks", "history:robin-hood-elevenlabs")
    assert robin["provider"] == "elevenlabs" and robin["status"] == "legacy"


def test_rerunning_imports_does_not_duplicate(harness, tmp_path):
    store, history, export, _, _, index = migrate(harness, tmp_path)
    counts = {t: len(store.all(t)) for t in ("children", "topics", "attempts", "tutor_sessions", "audio_tracks")}
    again = import_history(store, tmp_path / "Lucas - History", index, Report("again"))
    import_export(store, harness.drive, export, Report("again-hosted"))
    assert {t: len(store.all(t)) for t in counts} == counts
    assert again.skipped


def test_conflicting_topics_are_reported_not_overwritten(harness, tmp_path):
    history = build_history_folder(tmp_path / "Lucas - History")
    store = harness.ctx.store
    import hashlib
    with store.transaction() as tx:
        lucas = tx.insert("children", {"name": "Lucas"})
        subject = tx.insert("subjects", {"child_id": lucas["id"], "name": "History"})
        book = tx.insert("documents", {"drive_file_id": "1jX_ifE9DFGivsDeXCdOm8i5EsqgTiP_T", "page_count": 7,
                                       "original_filename": "Story of the World V.2.pdf",
                                       "sha256": hashlib.sha256(history["book"]).hexdigest()})
        tx.insert("topics", {"subject_id": subject["id"], "title": "Mongols (AI guess)", "page_start": 3,
                             "page_end": 5, "pdf_page_offset": 2, "document_id": book["id"], "completed": True})
    report = import_history(store, tmp_path / "Lucas - History", DriveIndex(history["drive_paths"]), Report("x"))
    kinds = {c["kind"] for c in report.conflicts}
    assert "topic_ambiguous" in kinds
    assert store.find("topics", title="Mongols (AI guess)")[0]["completed"] is True


def test_backup_restores_into_a_new_verified_workbook(harness, tmp_path):
    store, *_ = migrate(harness, tmp_path)
    backup = create_backup(store, harness.drive, tmp_path / "backups")
    assert backup["drive_file_id"] in harness.drive.files and backup["sync_state"] == "saved"
    snapshot = json.loads((tmp_path / "backups" / backup["name"]).read_text())
    fresh = FakeSheets()
    result = restore_into(fresh, snapshot)
    assert result["verified"], result
    restored = Store(tmp_path / "restored", fresh, harness.drive).load()
    for table in ("children", "attempts", "checkpoints", "annotations", "passages"):
        assert restored.all(table) == store.all(table)
