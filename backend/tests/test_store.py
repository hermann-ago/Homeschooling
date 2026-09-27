import sqlite3

import pytest

from storage import (
    SAVED, DriveFolder, DuplicateOperation, FileUnavailable, IntegrityViolation, OutsideBoundary, RevisionConflict,
    Store,
)
from storage.backups import create_backup, export_excel, latest_backup, verify_restore


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "Drive" / "Homeschooling"
    root.mkdir(parents=True)
    drive = DriveFolder(root)
    drive.ensure_folders()
    return drive


def open_store(tmp_path, folder=None):
    return Store(tmp_path / "local" / "homeschooling.sqlite3", folder).load()


def test_commit_is_saved_with_a_receipt(tmp_path):
    store = open_store(tmp_path)
    with store.transaction(operation_id="op-1") as tx:
        child = tx.insert("children", {"name": "Lucas", "color": "#123456"})
    assert tx.result["sync"] == SAVED
    assert store.operation_state("op-1") == SAVED
    connection = sqlite3.connect(tmp_path / "local" / "homeschooling.sqlite3")
    assert connection.execute("SELECT name FROM children WHERE id=?", (child["id"],)).fetchone() == ("Lucas",)
    assert [r[0] for r in connection.execute("SELECT id FROM operation_receipts")] == ["op-1"]


def test_data_survives_restart(tmp_path):
    store = open_store(tmp_path)
    with store.transaction(operation_id="op-a") as tx:
        tx.insert("children", {"name": "Lucas"})
        tx.insert("preferences", {"id": "1:narrator", "child_id": 1, "key": "narrator",
                                  "value": {"voice": "en-US-Neural2-J", "rate": 0.9}})
    restarted = open_store(tmp_path)
    assert [c["name"] for c in restarted.all("children")] == ["Lucas"]
    assert restarted.all("preferences")[0]["value"] == {"voice": "en-US-Neural2-J", "rate": 0.9}
    assert restarted.operation_state("op-a") == SAVED
    with restarted.transaction() as tx:
        second = tx.insert("children", {"name": "Mila"})
    assert second["id"] == 2


def test_failed_transaction_changes_nothing(tmp_path):
    store = open_store(tmp_path)
    with pytest.raises(RuntimeError):
        with store.transaction(operation_id="op-fail") as tx:
            tx.insert("children", {"name": "Lucas"})
            raise RuntimeError("boom")
    assert store.all("children") == [] and store.operation_state("op-fail") is None
    assert open_store(tmp_path).all("children") == []


def test_repeated_operation_id_is_rejected_not_duplicated(tmp_path):
    store = open_store(tmp_path)
    with store.transaction(operation_id="op-x", request_sha256="abc") as tx:
        tx.insert("children", {"name": "Lucas"})
    with pytest.raises(DuplicateOperation) as duplicate:
        with store.transaction(operation_id="op-x", request_sha256="abc") as tx:
            tx.insert("children", {"name": "Lucas"})
    assert duplicate.value.same_request
    assert len(store.all("children")) == 1


def test_expected_revision_conflict(tmp_path):
    store = open_store(tmp_path)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
    with store.transaction() as tx:
        tx.update("children", child["id"], {"nickname": "Luke"}, expected_revision=1)
    with pytest.raises(RevisionConflict) as conflict:
        with store.transaction() as tx:
            tx.update("children", child["id"], {"nickname": "L"}, expected_revision=1)
    assert conflict.value.current["revision"] == 2


def test_database_edit_outside_the_app_is_not_overwritten(tmp_path):
    store = open_store(tmp_path)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
    connection = sqlite3.connect(tmp_path / "local" / "homeschooling.sqlite3")
    with connection:
        connection.execute("UPDATE children SET revision=7 WHERE id=?", (child["id"],))
    connection.close()
    with pytest.raises(RevisionConflict):
        with store.transaction() as tx:
            tx.update("children", child["id"], {"nickname": "Luke"})
    assert store.get("children", child["id"])["nickname"] is None


def test_cascade_and_restrict(tmp_path):
    store = open_store(tmp_path)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "History"})
        topic = tx.insert("topics", {"subject_id": subject["id"], "title": "Genghis", "page_start": 1, "page_end": 2})
        tx.insert("tutor_sessions", {"id": "s1", "child_id": child["id"], "subject_id": subject["id"],
                                     "topic_id": topic["id"], "status": "unfinished"})
    with pytest.raises(IntegrityViolation):
        with store.transaction() as tx:
            tx.delete("topics", topic["id"])
    assert store.get("topics", topic["id"]) is not None


def test_files_are_written_into_the_drive_folder(tmp_path, folder):
    store = open_store(tmp_path, folder)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        document = tx.insert("documents", {"original_filename": "a.pdf", "page_count": 1})
        path, sha = tx.add_blob(b'{"strokes":[]}', "Lucas/3rd Grade/History/Handwriting", "a.json",
                                "application/json")
        tx.insert("annotations", {"child_id": child["id"], "document_id": document["id"], "page_number": 1,
                                  "file_path": path, "sha256": sha})
    handwriting = "Lucas/3rd Grade/History/Handwriting"
    assert path == f"{handwriting}/a.json"
    assert (folder.root / handwriting / "a.json").read_bytes() == b'{"strokes":[]}'
    assert folder.read(path, sha) == b'{"strokes":[]}'
    # Identical content reuses the file; different content never overwrites it.
    assert folder.write(handwriting, "a.json", b'{"strokes":[]}')[0] == f"{handwriting}/a.json"
    assert folder.write(handwriting, "a.json", b'{"strokes":[1]}')[0] == f"{handwriting}/a-2.json"
    assert not list(folder.root.rglob("*.part"))
    # Only subject folders with a known kind (or the top-level app folders) can be written.
    for bad in ("Annotations", "Lucas/History/Secrets", "../Lucas/History/Books", "_Archive/Books", "C:/x/Books"):
        with pytest.raises(OutsideBoundary):
            folder.write(bad, "a.json", b"{}")


def test_drive_folder_boundary_and_availability(tmp_path, folder):
    (tmp_path / "Drive" / "secret.pdf").write_bytes(b"%PDF-1.4")
    for bad in ("../secret.pdf", "/etc/passwd", "C:/Windows/win.ini", "Books/../../secret.pdf"):
        with pytest.raises(OutsideBoundary):
            folder.read(bad)
    with pytest.raises(FileUnavailable):
        folder.read("Books/missing.pdf")
    (folder.root / "Books").mkdir()
    (folder.root / "Books" / "book.pdf").write_bytes(b"%PDF-1.4 book")
    (folder.root / "_Archive").mkdir()
    (folder.root / "_Archive" / "old.pdf").write_bytes(b"%PDF-1.4 book")  # retired material is never listed
    with pytest.raises(FileUnavailable):
        folder.read("Books/book.pdf", sha256="0" * 64)
    assert [f["path"] for f in folder.list_pdfs()] == ["Books/book.pdf"]
    from storage.files import sha256_bytes
    assert folder.find_by_checksum(sha256_bytes(b"%PDF-1.4 book"), size=13) == "Books/book.pdf"
    offline = DriveFolder(tmp_path / "not-mounted")
    assert not offline.available
    with pytest.raises(FileUnavailable):
        offline.read("Books/book.pdf")


def test_backup_is_verified_and_restorable(tmp_path, folder):
    store = open_store(tmp_path, folder)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        tx.insert("preferences", {"id": f"{child['id']}:narrator", "child_id": child["id"], "key": "narrator",
                                  "value": {"voice": "en-US-Neural2-J", "rate": 0.9}})
    result = create_backup(store, tmp_path / "local-backups")
    assert result["counts"]["children"] == 1
    assert (folder.root / "_App Backups" / result["name"]).exists()
    assert latest_backup(store, tmp_path / "local-backups") == result["name"]
    check = verify_restore(folder.root / "_App Backups" / result["name"])
    assert check["integrity"] and check["counts"]["children"] == 1 and check["counts"]["preferences"] == 1
    restored = Store(folder.root / "_App Backups" / result["name"]).load()
    assert restored.all("preferences")[0]["value"] == {"rate": 0.9, "voice": "en-US-Neural2-J"}


def test_excel_copy_leaves_out_answer_keys(tmp_path, folder):
    import openpyxl
    store = open_store(tmp_path, folder)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        subject = tx.insert("subjects", {"child_id": child["id"], "name": "History"})
        tx.insert("teacher_keys", {"id": "k1", "subject_id": subject["id"], "chapter": 21, "question_start": 1,
                                   "question_end": 1,
                                   "answer": "SECRET-ANSWER"})
    relative = export_excel(store)
    workbook = openpyxl.load_workbook(folder.root / relative, read_only=True)
    text = " ".join(str(c) for ws in workbook.worksheets for row in ws.iter_rows(values_only=True) for c in row)
    assert "Lucas" in text and "SECRET-ANSWER" not in text


def test_layout_is_kid_grade_subject():
    from storage import layout
    assert [layout.grade_folder(g) for g in ("3rd", "1ST", "4", "12", "Pre-K", "N/A", "", None)] == \
        ["3rd Grade", "1ST Grade", "4th Grade", "12th Grade", "Pre-K", None, None, None]
    assert layout.subject_folder({"name": "Lucas", "grade_year": "3rd"}, "History") == "Lucas/3rd Grade/History"
    assert layout.subject_folder({"name": "Mila", "grade_year": "1st"}, "Português") == "Mila/1st Grade/Português"
    assert layout.subject_folder({"name": "Joshua", "grade_year": "N/A"}, "Reading") == "Joshua/Reading"
    assert layout.subject_folder({"name": "Olivia", "grade_year": "Pre-K"}, "Math: Counting") == "Olivia/Pre-K/Math_ Counting"
