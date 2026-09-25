"""Stage the hosted export into the Homeschooling Database workbook and Drive.

    python -m migration.import_hosted --export <export folder> [--dry-run]

Source IDs, timestamps and annotation revisions are preserved. Books already
beneath the Homeschooling folder (same SHA-256) are referenced by Drive file ID;
the rest are uploaded to ``Books``. Annotation strokes and enrichment content go
to Drive files with their IDs indexed in Sheets. The workbook must not already
hold app data unless this is a resumed run of the same import.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .common import Report, chunks, parse_time, staged

ENTITY_TABLES = ("children", "subjects", "documents", "topics", "time_windows", "blocked_days", "scheduled_slots",
                 "completions", "canvas_inserts", "enrichment", "settings", "annotations")


def _load(export: Path, table: str) -> list[dict]:
    path = export / "tables" / f"{table}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _pick(row: dict, *columns) -> dict:
    return {c: row.get(c) for c in columns if c in row}


def import_export(store, drive, export: Path, report: Report) -> Report:
    manifest = json.loads((export / "manifest.json").read_text(encoding="utf-8"))
    prior_imports = [op for op in store.all("operation_receipts") if op["id"].startswith("import-hosted-")]
    occupied = {t: len(store.all(t)) for t in ENTITY_TABLES if store.all(t)}
    if occupied and not prior_imports:
        raise RuntimeError(f"The workbook already holds data {occupied}; import into a new workbook")

    drive_by_sha = {}
    if drive is not None and hasattr(drive, "list_pdfs"):
        drive_by_sha = {f.get("sha256Checksum"): f for f in drive.list_pdfs() if f.get("sha256Checksum")}

    def simple(table, source, columns, rename=None):
        rows = _load(export, source)
        report.count(table, source=len(rows))
        for index, part in chunks(rows):
            def work(tx, part=part):
                for row in part:
                    values = _pick(row, *columns)
                    for old, new in (rename or {}).items():
                        values[new] = values.pop(old)
                    tx.insert(table, values)
            staged(store, f"import-hosted-{table}-{index:03d}", f"Import {table} ({index + 1})", work, report)

    simple("children", "children", ("id", "name", "nickname", "color", "grade_year", "created_at"))

    documents = _load(export, "documents")
    report.count("documents", source=len(documents))

    def import_documents(tx):
        for row in documents:
            book = manifest.get("books", {}).get(str(row["id"]), {})
            sha = book.get("sha256") or row.get("sha256")
            if book and not book.get("matches_record", True):
                report.conflict("book_checksum", f"Document {row['id']} bytes differ from its recorded checksum",
                                recorded=row.get("sha256"), downloaded=book.get("sha256"))
            existing = drive_by_sha.get(sha)
            if existing:
                file_id, source = existing["id"], "drive"
            elif book.get("file"):
                data = (export / "books" / book["file"]).read_bytes()
                file_id, _ = tx.add_blob(data, "Books", row["original_filename"], "application/pdf")
                source = "migrated"
            else:
                file_id, source = None, "missing"
                report.conflict("book_missing", f"No bytes were exported for document {row['id']}",
                                blob_path=row.get("blob_path"))
            tx.insert("documents", {**_pick(row, "id", "original_filename", "size_bytes", "page_count", "status",
                                            "created_at"),
                                    "drive_file_id": file_id, "sha256": sha, "source": source,
                                    "legacy_blob_path": row.get("blob_path")})
    staged(store, "import-hosted-documents-000", "Import documents", import_documents, report)

    simple("subjects", "subjects", ("id", "child_id", "name", "weight", "slot_type", "end_date", "created_at"))
    simple("topics", "curriculum_topics", ("id", "subject_id", "title", "page_start", "page_end", "complexity",
                                           "completed", "completed_at", "language", "chapter_order", "pdf_filename",
                                           "document_id", "pdf_page_offset", "is_core", "created_at"))
    simple("time_windows", "time_windows", ("id", "child_id", "weekday", "start_time", "end_time"))
    simple("blocked_days", "blocked_days", ("id", "child_id", "date", "block_type", "note", "created_at"))
    simple("scheduled_slots", "scheduled_slots", ("id", "child_id", "subject_id", "topic_id", "date", "time_start",
                                                  "time_end", "page_from", "page_to"))
    simple("completions", "completions", ("id", "slot_id", "completed_at"))
    simple("canvas_inserts", "canvas_inserts", ("id", "parent_topic_id", "insert_topic_id", "position", "created_at"))

    enrichment = _load(export, "canvas_ai_content")
    report.count("enrichment", source=len(enrichment))
    for index, part in chunks(enrichment, 100):
        def work(tx, part=part):
            for row in part:
                name = f"enrichment-topic{row['topic_id']}-p{row['page_start']}-{row['page_end']}-{row['content_type']}.txt"
                file_id, sha = tx.add_blob(row["content"].encode("utf-8"), "Tutor Content", name, "text/plain")
                tx.insert("enrichment", {**_pick(row, "id", "topic_id", "page_start", "page_end", "content_type",
                                                 "created_at"), "content_file_id": file_id, "content_sha256": sha})
        staged(store, f"import-hosted-enrichment-{index:03d}", "Import enrichment", work, report)

    settings = _load(export, "app_settings")
    report.count("settings", source=len(settings))
    keys = [s["key"] for s in settings]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        report.conflict("settings_duplicate", "Several accounts stored the same setting; the newest is kept",
                        keys=duplicates)

    def import_settings(tx):
        newest = {}
        for row in sorted(settings, key=lambda r: r.get("updated_at") or ""):
            newest[row["key"]] = row
        for key, row in newest.items():
            tx.insert("settings", {"id": key, "value": row["value"]}, updated_at=parse_time(row.get("updated_at")))
    staged(store, "import-hosted-settings-000", "Import settings", import_settings, report)

    annotations = _load(export, "pdf_page_annotations")
    report.count("annotations", source=len(annotations))
    for index, part in chunks(annotations, 100):
        def work(tx, part=part):
            for row in part:
                strokes = row["strokes"] if isinstance(row["strokes"], list) else json.loads(row["strokes"])
                body = json.dumps({"child_id": row["child_id"], "document_id": row["document_id"],
                                   "page_number": row["page_number"], "strokes": strokes},
                                  separators=(",", ":"), sort_keys=True).encode()
                name = f"annotations-child{row['child_id']}-doc{row['document_id']}-p{row['page_number']}-r{row['revision']}.json"
                file_id, sha = tx.add_blob(body, "Annotations", name, "application/json")
                tx.insert("annotations", {**_pick(row, "id", "child_id", "document_id", "page_number", "created_at"),
                                          "file_id": file_id, "sha256": sha, "stroke_count": len(strokes)},
                          revision=row["revision"], updated_at=parse_time(row.get("updated_at")))
        staged(store, f"import-hosted-annotations-{index:03d}", "Import annotations", work, report)

    for table in ENTITY_TABLES:
        report.count(table, imported=len(store.all(table)))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate into a throwaway local store")
    args = parser.parse_args(argv)
    report = Report("import-hosted" + ("-dry-run" if args.dry_run else ""))
    if args.dry_run:
        from storage import Store
        store = Store(Path(tempfile.mkdtemp()) / "dry-run").load()
        import_export(store, None, args.export, report)
    else:
        from app_context import AppContext
        context = AppContext(start_worker=False)
        import_export(context.store, context.drive, args.export, report)
        report.notes.append(f"Sync after import: {context.store.flush(max_ops=100_000)['state']}")
    path = report.write(Path(args.export) / "reports")
    print(json.dumps(report.as_dict()["counts"], indent=2))
    print(f"Report: {path} ({'clean' if not report.conflicts else f'{len(report.conflicts)} conflicts'})")
    return 0 if not report.conflicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
