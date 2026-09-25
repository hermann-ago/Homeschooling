import json

import pytest

from storage import (
    PENDING, RECONCILE, SAVED, DuplicateOperation, FakeDrive, FakeSheets, IntegrityViolation, MaintenancePaused,
    RevisionConflict, Store,
)
from storage.workbook import bootstrap, export_snapshot, restore_requests


@pytest.fixture
def sheets():
    fake = FakeSheets()
    bootstrap(fake)
    return fake


def open_store(tmp_path, sheets, drive=None):
    return Store(tmp_path / "local", sheets, drive or FakeDrive()).load()


def child_rows(sheets):
    return sheets.rows("Children")[1:]


def test_commit_is_pending_until_verified_in_sheets(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    with store.transaction(operation_id="op-1") as tx:
        child = tx.insert("children", {"name": "Lucas", "color": "#123456"})
    assert tx.result["sync"] == PENDING
    assert store.operation_state("op-1") == PENDING
    store.flush()
    assert store.operation_state("op-1") == SAVED
    rows = child_rows(sheets)
    assert rows[0][0] == str(child["id"]) and rows[0][3] == "Lucas"
    assert [r[0] for r in sheets.rows("Operation Receipts")[1:]] == ["op-1"]


def test_lost_response_is_saved_once_and_not_duplicated(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    with store.transaction(operation_id="op-lost") as tx:
        tx.insert("children", {"name": "Lucas"})
    sheets.fail_next("lost_response")
    status = store.flush()
    assert status["pending"] == 1 and status["online"] is False
    store.flush()
    assert store.operation_state("op-lost") == SAVED
    assert len(child_rows(sheets)) == 1
    assert len(sheets.rows("Operation Receipts")) == 2


def test_offline_work_survives_restart_and_saves_once(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    sheets.fail_next("offline")
    with store.transaction(operation_id="op-a") as tx:
        tx.insert("children", {"name": "Lucas"})
    store.flush()
    assert store.status()["state"] == PENDING
    # Server restarts while Google is still unreachable.
    sheets.fail_next("offline")
    restarted = Store(tmp_path / "local", sheets, FakeDrive()).load()
    assert [c["name"] for c in restarted.all("children")] == ["Lucas"]
    assert restarted.operation_state("op-a") == PENDING
    restarted.flush()
    restarted.flush()
    assert restarted.operation_state("op-a") == SAVED
    assert len(child_rows(sheets)) == 1


def test_repeated_operation_id_is_rejected_not_duplicated(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    with store.transaction(operation_id="op-x", request_sha256="abc") as tx:
        tx.insert("children", {"name": "Lucas"})
    with pytest.raises(DuplicateOperation) as duplicate:
        with store.transaction(operation_id="op-x", request_sha256="abc") as tx:
            tx.insert("children", {"name": "Lucas"})
    assert duplicate.value.same_request
    assert len(store.all("children")) == 1


def test_expected_revision_conflict(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
    with store.transaction() as tx:
        tx.update("children", child["id"], {"nickname": "Luke"}, expected_revision=1)
    with pytest.raises(RevisionConflict) as conflict:
        with store.transaction() as tx:
            tx.update("children", child["id"], {"nickname": "L"}, expected_revision=1)
    assert conflict.value.current["revision"] == 2


def test_sheet_edit_outside_app_needs_reconciliation(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
    store.flush()
    sheets.edit_cell("Children", 1, 1, "7")  # someone bumped the revision directly
    with store.transaction(operation_id="op-edit") as tx:
        tx.update("children", child["id"], {"nickname": "Luke"})
    store.flush()
    assert store.operation_state("op-edit") == RECONCILE
    assert store.get("children", child["id"])["nickname"] is None  # not applied to the live view
    assert store.unsettled()[0]["last_error"].startswith("Children")
    store.discard("op-edit")
    assert store.status()["state"] == SAVED
    assert list((tmp_path / "local" / "queue" / "discarded").glob("*op-edit.json"))


def test_cascade_and_restrict(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
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


def test_blob_uploaded_before_reference_reaches_sheets(tmp_path, sheets):
    drive = FakeDrive()
    store = open_store(tmp_path, sheets, drive)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        document = tx.insert("documents", {"original_filename": "a.pdf", "page_count": 1})
        file_id, sha = tx.add_blob(b'{"strokes":[]}', "Annotations", "a.json", "application/json")
        tx.insert("annotations", {"child_id": child["id"], "document_id": document["id"], "page_number": 1,
                                  "file_id": file_id, "sha256": sha})
    assert file_id.startswith("pending:")
    drive.faults.append("offline")
    store.flush()
    assert all("pending:" not in cell for row in sheets.rows("Annotation References") for cell in row)
    store.flush()
    row = sheets.rows("Annotation References")[1]
    assert row[6] in drive.files and drive.files[row[6]]["data"] == b'{"strokes":[]}'
    assert store.all("annotations")[0]["file_id"] == row[6]


def test_maintenance_pauses_writes_and_validates(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    with store.transaction() as tx:
        tx.insert("children", {"name": "Lucas"})
    store.begin_maintenance()
    with pytest.raises(MaintenancePaused):
        with store.transaction() as tx:
            tx.insert("children", {"name": "Mila"})
    sheets.edit_cell("Children", 1, 0, "")  # parent blanked an id
    result = store.end_maintenance()
    assert result["resumed"] is False and result["problems"]
    sheets.edit_cell("Children", 1, 0, "1")
    sheets.edit_cell("Children", 1, 4, "Lu")  # nickname edited directly
    result = store.end_maintenance()
    assert result["resumed"] is True and result["edited_rows"] == 1
    assert store.get("children", 1)["nickname"] == "Lu"
    assert store.get("children", 1)["revision"] == 2


def test_backup_restores_into_new_workbook(tmp_path, sheets):
    store = open_store(tmp_path, sheets)
    with store.transaction() as tx:
        child = tx.insert("children", {"name": "Lucas"})
        tx.insert("preferences", {"id": f"{child['id']}:narrator", "child_id": child["id"], "key": "narrator",
                                  "value": {"voice": "en-US-Neural2-J", "rate": 0.9}})
    store.flush()
    snapshot = json.loads(json.dumps(export_snapshot(store)))
    fresh = FakeSheets()
    bootstrap(fresh)
    fresh.batch_update(restore_requests(fresh, snapshot))
    restored = Store(tmp_path / "restored", fresh, FakeDrive()).load()
    assert restored.all("children") == store.all("children")
    assert restored.all("preferences")[0]["value"] == {"rate": 0.9, "voice": "en-US-Neural2-J"}
