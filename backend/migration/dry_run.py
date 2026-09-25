"""One-command migration dry run on the host computer. Changes nothing.

    python -m migration.dry_run [--history <Lucas - History folder>] [--export <export folder>]

1. When no --export is given and POSTGRES_URL is set (backend/.env), exports the
   hosted data read-only into %LOCALAPPDATA%\\Homeschooling\\migration.
2. Imports the hosted export and the History project into a throwaway copy of
   the database. Files the import would add go to a temporary folder, not to
   Google Drive, and the History folder is only read.
3. Reconciles the copy against both sources and writes one report.

Paste the printed summary back for review. The full report is saved under
%LOCALAPPDATA%\\Homeschooling\\migration-reports.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .common import Report, dry_run_store

HISTORY_FOLDER = "Lucas - History"


def export_now(context, report: Report) -> Path | None:
    if not os.getenv("POSTGRES_URL"):
        report.warnings.append("POSTGRES_URL is not set: the hosted app's data was not exported or checked")
        return None
    from . import export_hosted
    out = context.config.dir / "migration" / f"export-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    books = bool(os.getenv("BLOB_READ_WRITE_TOKEN")) and shutil.which("node") is not None
    if not books:
        report.warnings.append("Books were not downloaded from Vercel Blob (needs BLOB_READ_WRITE_TOKEN and Node); "
                               "book checks are incomplete")
    export_hosted.main(["--out", str(out)] + ([] if books else ["--skip-books"]))
    report.notes.append(f"Hosted export: {out}")
    return out


def summary(report: Report) -> dict:
    data = report.as_dict()
    return {"clean": data["clean"], "counts": data["counts"],
            "conflicts": [{k: v for k, v in c.items() if k in ("kind", "detail")} for c in data["conflicts"]],
            "warnings": data["warnings"], "skipped": data["skipped"][:20], "notes": data["notes"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--history", type=Path, help="The Lucas - History folder (default: inside the Drive folder)")
    parser.add_argument("--export", type=Path, help="An existing hosted export folder")
    parser.add_argument("--no-hosted", action="store_true", help="Skip the hosted app's data")
    args = parser.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    except ImportError:
        pass
    from app_context import AppContext
    from .import_history import import_history
    from .import_hosted import import_export
    from .reconcile import check_files, check_relationships, reconcile_history, reconcile_hosted

    context = AppContext(start_worker=False)
    report = Report("dry-run")
    if not context.files.available:
        raise SystemExit(f"The Homeschooling Drive folder was not found ({context.files.root}). Start Google Drive "
                         "for desktop, or set HOMESCHOOLING_DRIVE_FOLDER to the folder's path.")
    report.notes.append(f"Drive folder: {context.files.root}")
    history = args.history or context.files.root / HISTORY_FOLDER
    store = dry_run_store(context)
    report.notes.append(f"Throwaway database: {store.path}")

    export = None if args.no_hosted else (args.export or export_now(context, report))
    if export:
        import_export(store, export, report)
    if history.is_dir():
        import_history(store, history, report)
    else:
        report.conflict("history_missing", f"History folder not found: {history}")
    if export:
        reconcile_hosted(store, export, report)
    if history.is_dir():
        reconcile_history(store, history, report)
    if not export and not history.is_dir():
        check_relationships(store, report)
        check_files(store, report)
    report.count("result", **{name: len(store.all(name)) for name in (
        "children", "subjects", "documents", "topics", "chapters", "tutor_sessions", "checkpoints", "attempts",
        "reviews", "passages", "audio_tracks", "evidence_files", "question_maps")})
    path = report.write(context.config.dir / "migration-reports")
    print("=== Homeschooling migration dry run: paste everything below ===")
    print(json.dumps(summary(report), indent=1, ensure_ascii=False, default=str))
    print(f"Full report: {path}")
    print("Nothing was changed: not the database, not Google Drive, not the History folder.")
    return 0 if not report.conflicts else 1


if __name__ == "__main__":
    sys.exit(main())
