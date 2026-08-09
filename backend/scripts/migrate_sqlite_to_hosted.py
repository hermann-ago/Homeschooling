"""Idempotently migrate the local SQLite dataset and referenced PDFs to hosted Postgres/Blob.

Required environment: SQLITE_DATABASE, UPLOADS_DIR, POSTGRES_URL, MIGRATION_OWNER_ID,
BLOB_BASE_URL and BLOB_READ_WRITE_TOKEN.  Start with --dry-run; the JSON manifest makes
uploads resumable and preserves the original database and files unchanged.
"""
import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import httpx
import psycopg
from pypdf import PdfReader

TABLES = ("children", "blocked_days", "subjects", "time_windows", "scheduled_slots",
          "completions", "canvas_inserts", "canvas_ai_content", "app_settings")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(connection, table):
    return [dict(row) for row in connection.execute(f"select * from {table}").fetchall()]


def upload(path: Path, blob_path: str, base_url: str, token: str):
    url = f"{base_url.rstrip('/')}/{blob_path}"
    with path.open("rb") as stream, httpx.Client(timeout=None) as client:
        response = client.put(url, content=stream, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/pdf",
            "x-api-version": "7",
        })
    response.raise_for_status()


def upsert_rows(cursor, table, values, owner_id):
    if not values:
        return
    for row in values:
        row = dict(row)
        if table in {"children", "blocked_days", "app_settings"}:
            row["owner_id"] = owner_id
        # Legacy local path is intentionally not carried into hosted topics.
        row.pop("pdf_path", None)
        columns = list(row)
        placeholders = ", ".join(["%s"] * len(columns))
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "id")
        cursor.execute(
            f"insert into app.{table} ({', '.join(columns)}) values ({placeholders}) "
            f"on conflict (id) do update set {updates}",
            [row[column] for column in columns],
        )


def reset_sequences(cursor):
    for table in ("children", "blocked_days", "subjects", "documents", "curriculum_topics",
                  "time_windows", "scheduled_slots", "completions", "canvas_inserts",
                  "canvas_ai_content", "app_settings"):
        cursor.execute(
            "select setval(pg_get_serial_sequence(%s, 'id'), "
            "coalesce((select max(id) from app." + table + "), 1), true)",
            (f"app.{table}",),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", default="migration-manifest.json")
    args = parser.parse_args()
    sqlite_path = Path(os.environ["SQLITE_DATABASE"])
    uploads_dir = Path(os.environ["UPLOADS_DIR"])
    owner_id = os.environ["MIGRATION_OWNER_ID"]
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"documents": {}}

    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    topics = rows(source, "curriculum_topics")
    paths = {row["pdf_path"] for row in topics if row.get("pdf_path")}
    documents = {}
    for stored_path in sorted(paths):
        candidate = Path(stored_path)
        if not candidate.is_absolute():
            candidate = uploads_dir / candidate.name
        if not candidate.exists() or candidate.stat().st_size == 0:
            raise RuntimeError(f"Referenced PDF is unavailable or empty: {stored_path}")
        digest = sha256(candidate)
        documents.setdefault(digest, {"path": candidate, "source_paths": []})["source_paths"].append(stored_path)

    print(json.dumps({
        "records": {table: len(rows(source, table)) for table in TABLES},
        "topics": len(topics), "unique_documents": len(documents),
        "bytes": sum(item["path"].stat().st_size for item in documents.values()),
    }, indent=2))
    if args.dry_run:
        return

    with psycopg.connect(os.environ["POSTGRES_URL"]) as database:
        with database.cursor() as cursor:
            cursor.execute("select 1 from app.family_accounts where user_id=%s", (owner_id,))
            if not cursor.fetchone():
                raise RuntimeError("Run the one-time hosted setup first; its account is the migration owner.")
            digest_to_id = {}
            for digest, item in documents.items():
                blob_path = f"documents/{digest}.pdf"
                state = manifest["documents"].setdefault(digest, {"blob_path": blob_path, "uploaded": False})
                if not state["uploaded"]:
                    upload(item["path"], blob_path, os.environ["BLOB_BASE_URL"], os.environ["BLOB_READ_WRITE_TOKEN"])
                    state["uploaded"] = True
                    manifest_path.write_text(json.dumps(manifest, indent=2))
                cursor.execute(
                    "insert into app.documents (owner_id, blob_path, original_filename, size_bytes, page_count, sha256) "
                    "values (%s,%s,%s,%s,%s,%s) on conflict (blob_path) do update set sha256=excluded.sha256 "
                    "returning id",
                    (owner_id, blob_path, item["path"].name, item["path"].stat().st_size, len(PdfReader(item["path"]).pages), digest),
                )
                digest_to_id[digest] = cursor.fetchone()[0]

            for table in ("children", "blocked_days", "subjects"):
                upsert_rows(cursor, table, rows(source, table), owner_id)
            for topic in topics:
                source_path = topic.pop("pdf_path", None)
                document_id = None
                if source_path:
                    candidate = Path(source_path)
                    if not candidate.is_absolute():
                        candidate = uploads_dir / candidate.name
                    document_id = digest_to_id[sha256(candidate)]
                topic["document_id"] = document_id
                upsert_rows(cursor, "curriculum_topics", [topic], owner_id)
            for table in ("time_windows", "scheduled_slots", "completions", "canvas_inserts", "canvas_ai_content", "app_settings"):
                upsert_rows(cursor, table, rows(source, table), owner_id)
            reset_sequences(cursor)
    print("Migration complete. Re-run safely to validate the manifest and database state.")


if __name__ == "__main__":
    main()
