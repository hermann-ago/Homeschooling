"""Back up the database to the Drive folder and check that a backup restores.

    python -m migration.backup create
    python -m migration.backup verify [<backup.sqlite3>]

A backup is an integrity-checked copy of the SQLite database written to the
Homeschooling folder's ``Backups`` (Google Drive keeps it off the computer) and
to %LOCALAPPDATA%\\Homeschooling\\backups. ``verify`` opens a copy of a backup on
its own, never the live database, and compares its row counts with the live
database. To restore, stop the server and copy the backup over
%LOCALAPPDATA%\\Homeschooling\\homeschooling.sqlite3 (keep the old file).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from storage.backups import create_backup, verify_restore


def find_backup(context, name: str | None) -> Path | None:
    folders = [context.config.backup_dir]
    if context.files.available:
        folders.insert(0, context.files.root / "Backups")
    if name and Path(name).is_file():
        return Path(name)
    candidates = sorted((p for folder in folders if folder.exists() for p in folder.glob("homeschooling-*.sqlite3")),
                        key=lambda p: p.name)
    if name:
        candidates = [p for p in candidates if p.name == name]
    return candidates[-1] if candidates else None


def verify(context, backup: Path) -> dict:
    result = verify_restore(backup)
    live = {name: len(context.store.all(name)) for name in result["counts"]}
    result["backup"] = str(backup)
    result["matches_live"] = result["counts"] == live
    result["differences"] = {k: {"backup": result["counts"][k], "live": live[k]}
                             for k in live if result["counts"][k] != live[k]}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create")
    check = commands.add_parser("verify")
    check.add_argument("backup", nargs="?")
    args = parser.parse_args(argv)
    from app_context import AppContext
    context = AppContext(start_worker=False)
    if args.command == "create":
        print(json.dumps(create_backup(context.store, context.config.backup_dir), indent=2))
        return 0
    backup = find_backup(context, args.backup)
    if backup is None:
        raise SystemExit("No backup found; run `python -m migration.backup create` first")
    result = verify(context, backup)
    print(json.dumps(result, indent=2))
    return 0 if result["integrity"] and result["matches_live"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
