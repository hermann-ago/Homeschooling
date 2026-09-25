"""Final cutover checks and the History project's new entry instructions.

    python -m migration.cutover check
    python -m migration.cutover history-instructions --source "<Lucas - History folder>" [--apply]

``check`` refuses cutover while anything is pending or unreconciled, or when
the newest reconciliation report has conflicts. ``history-instructions`` shows
(or with --apply writes) new AGENTS.md / START_HERE.md for the History project,
first copying the originals to backups/pre-integrated-tutor/ in that folder.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "tutor" / "history-project"


def readiness(store, reports_dir: Path) -> dict:
    status = store.status()
    reports = sorted(reports_dir.glob("reconcile-*.json")) if reports_dir.exists() else []
    latest = json.loads(reports[-1].read_text(encoding="utf-8")) if reports else None
    backups = sorted((reports_dir.parent / "backups").glob("*.json")) if (reports_dir.parent / "backups").exists() else []
    blockers = []
    if status["state"] != "saved":
        blockers.append(f"Sync state is {status['state']}")
    if status["maintenance"]:
        blockers.append("Maintenance mode is on")
    if not latest:
        blockers.append("No reconciliation report yet")
    elif latest["conflicts"]:
        blockers.append(f"Latest reconciliation has {len(latest['conflicts'])} conflicts")
    if not backups:
        blockers.append("No backup of the migrated workbook yet")
    return {"ready": not blockers, "blockers": blockers, "latest_reconcile": reports[-1].name if reports else None,
            "latest_backup": backups[-1].name if backups else None}


def render(child_id: int, subject_id: int, receipt: str) -> dict[str, str]:
    values = {"child_id": child_id, "subject_id": subject_id, "migration_receipt": receipt,
              "cutover_date": date.today().isoformat()}
    return {name.replace(".template", ""): (TEMPLATES / name).read_text(encoding="utf-8").format(**values)
            for name in ("AGENTS.md.template", "START_HERE.md.template")}


def write_history_instructions(source: Path, files: dict[str, str]) -> list[str]:
    backup = source / "backups" / "pre-integrated-tutor"
    backup.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in files.items():
        original = source / name
        if original.exists() and not (backup / name).exists():
            shutil.copy2(original, backup / name)
        original.write_text(text, encoding="utf-8")
        written.append(str(original))
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    history = commands.add_parser("history-instructions")
    history.add_argument("--source", required=True, type=Path)
    history.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    from app_context import AppContext
    context = AppContext(start_worker=False)
    check = readiness(context.store, context.config.dir / "migration-reports")
    if args.command == "check":
        print(json.dumps(check, indent=2))
        return 0 if check["ready"] else 1
    if not check["ready"]:
        print(json.dumps(check, indent=2))
        raise SystemExit("Cutover is blocked; resolve the blockers above first")
    child = next(c for c in context.store.all("children") if c["name"].lower() == "lucas")
    subject = next(s for s in context.store.find("subjects", child_id=child["id"]) if "history" in s["name"].lower())
    files = render(child["id"], subject["id"], check["latest_reconcile"])
    if not args.apply:
        for name, text in files.items():
            print(f"── {name} ──\n{text}")
        print("Dry run: nothing written. Add --apply to replace the History project's entry instructions.")
        return 0
    for path in write_history_instructions(args.source, files):
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
