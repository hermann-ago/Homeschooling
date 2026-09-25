"""Export the hosted (Supabase + Vercel Blob) data before cutover. Read-only.

    python -m migration.export_hosted --out <export folder>

Needs ``POSTGRES_URL`` (read access to the hosted database) and, for books,
``BLOB_READ_WRITE_TOKEN`` with Node available (``migration/legacy/download_blobs.mjs``
uses the same @vercel/blob API the old app used). GitHub holds the code only;
this export is where the live data comes from.

The export folder receives one JSON file per table, the book PDFs named by
SHA-256, and ``manifest.json`` with row counts and checksums used later by
``migration.reconcile``. Nothing in the hosted systems is changed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .common import sha256_file, sha256_json

TABLES = ("children", "subjects", "documents", "curriculum_topics", "time_windows", "blocked_days",
          "scheduled_slots", "completions", "canvas_inserts", "canvas_ai_content", "app_settings",
          "pdf_page_annotations")


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def export_tables(connection, out: Path) -> dict:
    manifest = {}
    with connection.cursor() as cursor:
        cursor.execute("set transaction read only")
        for table in TABLES:
            cursor.execute(f"select * from app.{table} order by id")
            columns = [c.name for c in cursor.description]
            rows = [{c: _plain(v) for c, v in zip(columns, row)} for row in cursor.fetchall()]
            (out / "tables").mkdir(parents=True, exist_ok=True)
            path = out / "tables" / f"{table}.json"
            path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
            manifest[table] = {"count": len(rows), "sha256": sha256_json(rows),
                               "ids": [r["id"] for r in rows]}
    return manifest


def download_books(out: Path, documents: list[dict]) -> dict:
    books = out / "books"
    books.mkdir(parents=True, exist_ok=True)
    listing = out / "blob-list.json"
    listing.write_text(json.dumps([d["blob_path"] for d in documents]), encoding="utf-8")
    script = Path(__file__).with_name("legacy") / "download_blobs.mjs"
    subprocess.run(["node", str(script), str(listing), str(books)], check=True)
    result = {}
    for document in documents:
        path = books / (document["blob_path"].replace("/", "__"))
        if not path.exists():
            result[str(document["id"])] = {"error": "missing download"}
            continue
        digest = sha256_file(path)
        final = books / f"{digest}.pdf"
        if not final.exists():
            path.rename(final)
        else:
            path.unlink()
        result[str(document["id"])] = {"file": final.name, "sha256": digest, "size": final.stat().st_size,
                                       "recorded_sha256": document.get("sha256"),
                                       "matches_record": document.get("sha256") in (None, digest)}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--skip-books", action="store_true")
    args = parser.parse_args(argv)
    import psycopg
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(os.environ["POSTGRES_URL"], prepare_threshold=None) as connection:
        tables = export_tables(connection, out)
    documents = json.loads((out / "tables" / "documents.json").read_text(encoding="utf-8"))
    books = {} if args.skip_books else download_books(out, documents)
    manifest = {"exported_at": datetime.now().astimezone().isoformat(), "tables": tables, "books": books}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({t: v["count"] for t, v in tables.items()}, indent=2))
    problems = [k for k, v in books.items() if v.get("error") or not v.get("matches_record", True)]
    if problems:
        print(f"Books needing attention: {problems}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
