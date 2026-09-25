"""Back up the workbook to Drive and restore a backup into a new workbook.

    python -m migration.backup create
    python -m migration.backup restore <backup.json> [--name "Homeschooling Database (restored)"]

A backup is a JSON copy of every tab (exact cell text), stored in the Drive
``Backups`` folder and under %LOCALAPPDATA%\\Homeschooling\\backups. Restoring
never touches the live workbook: it creates a new workbook, loads the backup
and verifies every tab before reporting success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from storage.workbook import bootstrap, export_snapshot, restore_requests


def create_backup(store, drive, local_dir: Path) -> dict:
    status = store.status()
    snapshot = export_snapshot(store)
    snapshot["created_at"] = datetime.now(timezone.utc).isoformat()
    snapshot["sync_state"] = status["state"]
    body = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    name = f"homeschooling-database-{snapshot['created_at'][:19].replace(':', '')}.json"
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / name).write_bytes(body)
    file_id = drive.upload(body, name, "application/json", "Backups", {"sha256": sha, "kind": "database-backup"}) \
        if drive is not None else None
    return {"name": name, "sha256": sha, "drive_file_id": file_id, "sync_state": status["state"],
            "rows": {tab: len(rows) - 1 for tab, rows in snapshot["tabs"].items()}}


def restore_into(sheets, snapshot: dict) -> dict:
    """Load a backup into an empty workbook and verify it cell for cell."""
    bootstrap(sheets)
    requests = restore_requests(sheets, snapshot)
    for start in range(0, len(requests), 20):
        sheets.batch_update(requests[start:start + 20])
    from storage.gateway import quote_tab
    problems = []
    for tab, rows in snapshot["tabs"].items():
        actual = sheets.get_values([quote_tab(tab)])[0]
        trimmed = [[c for c in r] for r in rows]
        for row in trimmed:
            while row and row[-1] == "":
                row.pop()
        if actual != trimmed:
            problems.append(tab)
    return {"verified": not problems, "mismatched_tabs": problems,
            "rows": {tab: len(rows) - 1 for tab, rows in snapshot["tabs"].items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create")
    restore = commands.add_parser("restore")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--name", default="Homeschooling Database (restored)")
    args = parser.parse_args(argv)
    from app_context import AppContext
    context = AppContext(start_worker=False)
    if args.command == "create":
        context.store.flush(max_ops=100_000)
        print(json.dumps(create_backup(context.store, context.drive, context.config.dir / "backups"), indent=2))
        return 0
    from google_io.rest import GoogleRest
    from google_io.sheets import SheetsClient
    snapshot = json.loads(args.backup.read_text(encoding="utf-8"))
    spreadsheet_id = context.drive.create_workbook(args.name)
    result = restore_into(SheetsClient(GoogleRest(context.auth), spreadsheet_id), snapshot)
    result["spreadsheet_id"] = spreadsheet_id
    print(json.dumps(result, indent=2))
    print("The live workbook was not changed. To switch to the restored copy, set spreadsheet_id in config.json.")
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
