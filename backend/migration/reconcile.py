"""Compare the staged workbook with the migration sources and report differences.

    python -m migration.reconcile --export <export folder> [--history <Lucas - History folder>]

Checks record counts and IDs, relationships, book hashes (Drive's SHA-256 when
available), annotation revisions and stroke content, and representative learner
records from the History workbook. Differences are reported; nothing is changed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from storage.schema import TABLES

from .common import Report

SOURCE_TO_TABLE = {"children": "children", "subjects": "subjects", "documents": "documents",
                   "curriculum_topics": "topics", "time_windows": "time_windows", "blocked_days": "blocked_days",
                   "scheduled_slots": "scheduled_slots", "completions": "completions",
                   "canvas_inserts": "canvas_inserts", "canvas_ai_content": "enrichment",
                   "pdf_page_annotations": "annotations"}


def check_relationships(store, report: Report):
    for spec in TABLES.values():
        for row in store.all(spec.name):
            for fk in spec.foreign_keys:
                value = row.get(fk.column)
                if value is not None and store.get(fk.table, value) is None:
                    report.conflict("relationship", f"{spec.tab} {row['id']}: {fk.column} {value} is missing")


def reconcile_hosted(store, export: Path, report: Report, drive=None) -> Report:
    manifest = json.loads((export / "manifest.json").read_text(encoding="utf-8"))
    for source, table in SOURCE_TO_TABLE.items():
        expected = set(manifest["tables"].get(source, {}).get("ids", []))
        actual = {r["id"] for r in store.all(table)}
        missing, extra = sorted(expected - actual), sorted(actual - expected)
        report.count(table, source=len(expected), workbook=len(actual & expected))
        if missing:
            report.conflict("missing_rows", f"{table}: {len(missing)} source rows are not in the workbook", ids=missing[:50])
        if extra and table not in ("topics", "documents"):  # History import may add topics and books
            report.warnings.append(f"{table}: {len(extra)} rows exist only in the workbook")
    settings = json.loads((export / "tables" / "app_settings.json").read_text(encoding="utf-8"))
    for row in settings:
        current = store.get("settings", row["key"])
        if not current:
            report.conflict("missing_setting", f"Setting {row['key']} is missing")
    exported_docs = {d["id"]: d for d in json.loads((export / "tables" / "documents.json").read_text(encoding="utf-8"))}
    for document_id, source in exported_docs.items():
        row = store.get("documents", document_id)
        if not row:
            continue
        book = manifest.get("books", {}).get(str(document_id), {})
        expected_sha = book.get("sha256") or source.get("sha256")
        if row["sha256"] != expected_sha:
            report.conflict("book_hash", f"Document {document_id} checksum differs", workbook=row["sha256"],
                            source=expected_sha)
        if drive is not None and row["drive_file_id"] and not row["drive_file_id"].startswith("pending:"):
            drive_sha = drive.metadata(row["drive_file_id"]).get("sha256Checksum")
            if drive_sha and drive_sha != row["sha256"]:
                report.conflict("book_hash", f"Document {document_id}: Drive copy differs from the recorded checksum")
        elif row["drive_file_id"] and row["drive_file_id"].startswith("pending:"):
            report.warnings.append(f"Document {document_id} has not been uploaded to Drive yet")
    import hashlib
    annotations = json.loads((export / "tables" / "pdf_page_annotations.json").read_text(encoding="utf-8"))
    for source in annotations:
        row = store.get("annotations", source["id"])
        if not row:
            continue
        strokes = source["strokes"] if isinstance(source["strokes"], list) else json.loads(source["strokes"])
        body = json.dumps({"child_id": source["child_id"], "document_id": source["document_id"],
                           "page_number": source["page_number"], "strokes": strokes},
                          separators=(",", ":"), sort_keys=True).encode()
        if row["revision"] != source["revision"]:
            report.conflict("annotation_revision", f"Annotation {source['id']} revision {row['revision']} "
                            f"≠ source {source['revision']}")
        if row["sha256"] != hashlib.sha256(body).hexdigest():
            report.conflict("annotation_content", f"Annotation {source['id']} strokes differ from the export")
    for source_name in ("completions", "scheduled_slots"):
        rows = json.loads((export / "tables" / f"{source_name}.json").read_text(encoding="utf-8"))
        table = SOURCE_TO_TABLE[source_name]
        for sample in rows[:3] + rows[-3:]:
            current = store.get(table, sample["id"])
            if current is None:
                continue
            for column, value in sample.items():
                if column in current and column not in ("owner_id",) and value is not None:
                    left = current[column].isoformat() if hasattr(current[column], "isoformat") else current[column]
                    if str(left)[:19] != str(value)[:19]:
                        report.conflict("sample_value", f"{table} {sample['id']}.{column}: {left!r} ≠ {value!r}")
    check_relationships(store, report)
    return report


def reconcile_history(store, source: Path, report: Report) -> Report:
    from .import_history import read_tracker
    config = json.loads((Path(source) / "tutor.json").read_text(encoding="utf-8"))
    tracker = read_tracker(Path(source) / config["tracker"])
    checks = (("sessions", "tutor_sessions", "Session ID"), ("answers", "attempts", "Answer ID"),
              ("reviews", "reviews", "Review ID"))
    for kind, table, key in checks:
        rows = [r for r in tracker.get(kind, []) if r.get(key)]
        present = [r for r in rows if store.get(table, str(r[key]).strip())]
        report.count(f"history_{kind}", source=len(rows), workbook=len(present))
        if len(present) != len(rows):
            report.conflict("history_missing", f"{len(rows) - len(present)} {kind} are missing")
    for row in tracker.get("answers", []):
        attempt = store.get("attempts", str(row["Answer ID"]).strip())
        if attempt and (attempt["first_answer"] or "") != (str(row.get("First answer (verbatim)") or "").strip()):
            report.conflict("history_answer", f"{row['Answer ID']}: first answer differs from the tracker")
        if attempt and (row.get("Hint given") or row.get("Corrected answer")) and attempt["independence"] == "independent":
            report.conflict("history_independence", f"{row['Answer ID']}: assisted answer marked independent")
    completed = {str(r["Topic ID"]).strip() for r in tracker.get("topics", []) if r.get("Coverage") == "Completed"}
    history_topics = {t["source_key"]: t for t in store.all("topics") if t["source_key"]}
    stored_completed = {k for k, t in history_topics.items() if t["completed"]}
    if completed != stored_completed:
        report.conflict("history_completion", "Completed topics differ",
                        tracker=sorted(completed), workbook=sorted(stored_completed))
    genghis = [s for s in store.all("tutor_sessions") if s["id"].endswith("C21-T01-recovered")]
    if not genghis or genghis[0]["status"] != "unfinished":
        report.conflict("genghis", "The recovered Genghis discussion is not an unfinished session")
    else:
        checkpoint = store.get("checkpoints", f"{genghis[0]['id']}-cp")
        if not checkpoint or checkpoint["next_prompt"] != "What did the man who spoke up do next?":
            report.conflict("genghis", "The Genghis checkpoint's next prompt was not preserved")
        if history_topics.get("C21-T01", {}).get("completed"):
            report.conflict("genghis", "C21-T01 must not be complete")
    check_relationships(store, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--history", type=Path)
    args = parser.parse_args(argv)
    from app_context import AppContext
    context = AppContext(start_worker=False)
    report = Report("reconcile")
    status = context.store.status()
    if status["state"] != "saved":
        report.conflict("sync", f"The workbook is not fully saved ({status['state']}); flush before reconciling")
    if args.export:
        reconcile_hosted(context.store, args.export, report, context.drive)
    if args.history:
        reconcile_history(context.store, args.history, report)
    path = report.write(context.config.dir / "migration-reports")
    print(json.dumps(report.as_dict(), indent=2, default=str)[:6000])
    print(f"Report: {path}")
    return 0 if not report.conflicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
