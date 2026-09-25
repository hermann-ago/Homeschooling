"""Create, validate, back up and summarise the Homeschooling Database workbook."""
from __future__ import annotations

from datetime import date

from .gateway import quote_tab
from .schema import META_TAB, OVERVIEW_TAB, SCHEMA_VERSION, TABLES, row_to_cells

WORKBOOK_NAME = "Homeschooling Database"


def _cells(values):
    return {"values": [{"userEnteredValue": {"stringValue": str(v)}} for v in values]}


def bootstrap(sheets) -> list[str]:
    """Add any missing tabs with their headers. Existing tabs are never rewritten."""
    titles = sheets.metadata()
    wanted = [OVERVIEW_TAB, *(t.tab for t in TABLES.values()), META_TAB]
    missing = [t for t in wanted if t not in titles]
    if not missing:
        return []
    sheets.batch_update([{"addSheet": {"properties": {"title": t, "gridProperties": {"frozenRowCount": 1}}}}
                         for t in missing])
    titles = sheets.metadata()
    requests = []
    for spec in TABLES.values():
        if spec.tab in missing:
            requests.append({"updateCells": {"start": {"sheetId": titles[spec.tab], "rowIndex": 0, "columnIndex": 0},
                                             "fields": "userEnteredValue", "rows": [_cells(spec.header)]}})
    if META_TAB in missing:
        requests.append({"updateCells": {"start": {"sheetId": titles[META_TAB], "rowIndex": 0, "columnIndex": 0},
                                         "fields": "userEnteredValue",
                                         "rows": [_cells(["key", "value"]), _cells(["schema_version", SCHEMA_VERSION]),
                                                  _cells(["writer", "Homeschooling home server (single writer)"])]}})
    if requests:
        sheets.batch_update(requests)
    return missing


def overview_rows(store) -> list[list[str]]:
    today = date.today()
    status = store.status()
    rows = [
        ["Homeschooling Database", ""],
        ["This workbook is written only by the home server.", "Use parent maintenance mode before editing cells."],
        ["Sync state", status["state"]],
        ["Last saved", status.get("last_saved_at") or ""],
        ["", ""],
        ["Learner", "Subjects", "Topics completed", "Open reviews", "Reviews due", "Unfinished lessons"],
    ]
    for child in sorted(store.all("children"), key=lambda c: c["id"]):
        subjects = store.find("subjects", child_id=child["id"])
        subject_ids = {s["id"] for s in subjects}
        topics = [t for t in store.all("topics") if t["subject_id"] in subject_ids]
        reviews = [r for r in store.find("reviews", child_id=child["id"]) if r["status"] == "Open"]
        due = [r for r in reviews if r["next_due"] and r["next_due"] <= today]
        unfinished = [c for c in store.find("checkpoints", child_id=child["id"]) if c["status"] == "open"]
        rows.append([child["name"], str(len(subjects)), str(sum(1 for t in topics if t["completed"])),
                     str(len(reviews)), str(len(due)), str(len(unfinished))])
    rows += [["", ""], ["Tab", "Rows"]]
    rows += [[spec.tab, str(len(store.all(spec.name)))] for spec in TABLES.values()]
    return rows


def write_overview(store) -> None:
    sheets = store.sheets
    if sheets is None:
        return
    ids = sheets.metadata()
    rows = overview_rows(store)
    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows] + [[""] * width for _ in range(max(0, 60 - len(rows)))]
    sheets.batch_update([{"updateCells": {"start": {"sheetId": ids[OVERVIEW_TAB], "rowIndex": 0, "columnIndex": 0},
                                          "fields": "userEnteredValue", "rows": [_cells(r) for r in padded]}}])


def export_snapshot(store) -> dict:
    """Plain JSON copy of every tab, used for Drive backups and restore tests."""
    return {"schema_version": SCHEMA_VERSION,
            "tabs": {spec.tab: [spec.header] + [row_to_cells(spec, r) for r in store.all(spec.name)]
                     for spec in TABLES.values()}}


def restore_requests(sheets, snapshot: dict) -> list[dict]:
    """Requests that load a backup into an empty, bootstrapped workbook."""
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Backup schema version does not match this app")
    ids = sheets.metadata()
    requests = []
    for tab, rows in snapshot["tabs"].items():
        if tab not in ids:
            raise ValueError(f"Workbook is missing tab {tab}")
        existing = sheets.get_values([quote_tab(tab)])[0]
        if len(existing) > 1:
            raise ValueError(f"{tab} is not empty; restore only into a new workbook")
        if len(rows) > 1:
            requests.append({"appendCells": {"sheetId": ids[tab], "fields": "userEnteredValue",
                                             "rows": [_cells(r) for r in rows[1:]]}})
    return requests
