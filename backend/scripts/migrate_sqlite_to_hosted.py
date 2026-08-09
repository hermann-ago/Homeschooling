"""Idempotently migrate the local SQLite dataset and referenced PDFs to hosted Postgres/Blob.

Required environment: SQLITE_DATABASE, UPLOADS_DIR, MIGRATION_OWNER_ID, BLOB_BASE_URL and
BLOB_READ_WRITE_TOKEN. POSTGRES_URL is additionally required for the direct database mode.
Start with --dry-run; the JSON manifest makes uploads resumable and preserves the original
database and files unchanged.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import psycopg

TABLES = ("children", "blocked_days", "subjects", "time_windows", "scheduled_slots",
          "completions", "canvas_inserts", "canvas_ai_content", "app_settings")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_page_count(path: Path) -> int:
    """Read PDF metadata without parsing the full book in Python."""
    result = subprocess.run(
        [os.environ.get("PDFINFO_PATH", "pdfinfo"), str(path)],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"pdfinfo did not report a page count for {path}")


def rows(connection, table):
    return [dict(row) for row in connection.execute(f"select * from {table}").fetchall()]


def upload(path: Path, blob_path: str, base_url: str, token: str):
    """Use Vercel's supported multipart SDK for files larger than one request."""
    del base_url, token  # Authentication is supplied to the child process through its environment.
    script = Path(__file__).with_name("upload_blob.mjs")
    subprocess.run(["node", str(script), str(path), blob_path], check=True)


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


def sql_literal(value):
    """Render values from our trusted local SQLite backup as PostgreSQL literals."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def upsert_statement(table, values, owner_id):
    if not values:
        return ""
    statements = []
    for row in values:
        row = dict(row)
        if table in {"children", "blocked_days", "app_settings"}:
            row["owner_id"] = owner_id
        row.pop("pdf_path", None)
        if table == "curriculum_topics":
            for column in ("completed", "is_core"):
                if column in row and row[column] is not None:
                    row[column] = bool(row[column])
        columns = list(row)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "id")
        statements.append(
            f"insert into app.{table} ({', '.join(columns)}) values "
            f"({', '.join(sql_literal(row[column]) for column in columns)}) "
            f"on conflict (id) do update set {updates};"
        )
    return "\n".join(statements)


def write_mcp_sql(output_dir, source, topics, documents, uploads_dir, owner_id):
    """Create bounded SQL batches for Supabase MCP when local pooler DNS is unavailable."""
    output_dir.mkdir(parents=True, exist_ok=True)
    batches = []
    document_rows = []
    digest_to_id = {}
    digest_by_size = {}
    for document_id, (digest, item) in enumerate(documents.items(), start=1):
        digest_to_id[digest] = document_id
        digest_by_size[item["path"].stat().st_size] = digest
        document_rows.append({
            "id": document_id,
            "owner_id": owner_id,
            "blob_path": f"documents/{digest}.pdf",
            "original_filename": item["path"].name,
            "size_bytes": item["path"].stat().st_size,
            "page_count": pdf_page_count(item["path"]),
            "sha256": digest,
        })
    account_check = (
        "do $$ begin if not exists (select 1 from app.family_accounts where user_id = "
        + sql_literal(owner_id)
        + ") then raise exception 'Run the one-time hosted setup first; its account is the migration owner.'; end if; end $$;\n"
    )
    batches.append(("00-documents.sql", account_check + upsert_statement("documents", document_rows, owner_id)))
    for index, table in enumerate(("children", "blocked_days", "subjects"), start=1):
        batches.append((f"0{index}-{table}.sql", upsert_statement(table, rows(source, table), owner_id)))
    hosted_topics = []
    for topic in topics:
        topic = dict(topic)
        source_path = topic.pop("pdf_path", None)
        if source_path:
            candidate = Path(source_path)
            if not candidate.is_absolute():
                candidate = uploads_dir / candidate.name
            topic["document_id"] = digest_to_id[digest_by_size[candidate.stat().st_size]]
        else:
            topic["document_id"] = None
        hosted_topics.append(topic)
    for part, start in enumerate(range(0, len(hosted_topics), 75), start=1):
        batches.append((
            f"04-curriculum-topics-{part:02d}.sql",
            upsert_statement("curriculum_topics", hosted_topics[start:start + 75], owner_id),
        ))
    for index, table in enumerate(("time_windows", "scheduled_slots", "completions", "canvas_inserts", "canvas_ai_content", "app_settings"), start=5):
        values = rows(source, table)
        for part, start in enumerate(range(0, len(values), 75), start=1):
            batches.append((
                f"{index:02d}-{table}-{part:02d}.sql",
                upsert_statement(table, values[start:start + 75], owner_id),
            ))
    sequence_sql = "\n".join(
        "select setval(pg_get_serial_sequence('app." + table + "', 'id'), "
        "coalesce((select max(id) from app." + table + "), 1), true);"
        for table in ("children", "blocked_days", "subjects", "documents", "curriculum_topics",
                      "time_windows", "scheduled_slots", "completions", "canvas_inserts",
                      "canvas_ai_content", "app_settings")
    )
    batches.append(("99-sequences.sql", sequence_sql))
    for name, contents in batches:
        (output_dir / name).write_text(contents + "\n", encoding="utf-8")


def build_hosted_payload(source, topics, documents, uploads_dir, owner_id):
    digest_to_id = {}
    digest_by_size = {}
    document_rows = []
    for document_id, (digest, item) in enumerate(documents.items(), start=1):
        digest_to_id[digest] = document_id
        digest_by_size[item["path"].stat().st_size] = digest
        document_rows.append({
            "id": document_id, "owner_id": owner_id, "blob_path": f"documents/{digest}.pdf",
            "original_filename": item["path"].name, "size_bytes": item["path"].stat().st_size,
            "page_count": pdf_page_count(item["path"]), "sha256": digest,
        })
    tables = {"documents": document_rows}
    for table in ("children", "blocked_days", "subjects", "time_windows", "scheduled_slots",
                  "completions", "canvas_inserts", "canvas_ai_content", "app_settings"):
        values = rows(source, table)
        if table in {"children", "blocked_days", "app_settings"}:
            for value in values:
                value["owner_id"] = owner_id
        tables[table] = values
    hosted_topics = []
    for topic in topics:
        topic = dict(topic)
        source_path = topic.pop("pdf_path", None)
        if source_path:
            candidate = Path(source_path)
            if not candidate.is_absolute():
                candidate = uploads_dir / candidate.name
            topic["document_id"] = digest_to_id[digest_by_size[candidate.stat().st_size]]
        else:
            topic["document_id"] = None
        for column in ("completed", "is_core"):
            if column in topic and topic[column] is not None:
                topic[column] = bool(topic[column])
        hosted_topics.append(topic)
    tables["curriculum_topics"] = hosted_topics
    return {"owner_id": owner_id, "tables": tables}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", default="migration-manifest.json")
    parser.add_argument("--mcp-sql-dir", help="Upload PDFs, then write database SQL batches for Supabase MCP execution.")
    parser.add_argument("--json-payload", help="Upload PDFs, then write the private bulk-import request body.")
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
    digest_by_size = json.loads(os.environ.get("BLOB_DIGEST_BY_SIZE", "{}"))
    for stored_path in sorted(paths):
        candidate = Path(stored_path)
        if not candidate.is_absolute():
            candidate = uploads_dir / candidate.name
        if not candidate.exists() or candidate.stat().st_size == 0:
            raise RuntimeError(f"Referenced PDF is unavailable or empty: {stored_path}")
        # On a resume, Blob metadata can map unique file sizes to their completed
        # content hashes. This avoids re-reading large Google Drive files.
        digest = digest_by_size.get(str(candidate.stat().st_size)) or sha256(candidate)
        documents.setdefault(digest, {"path": candidate, "source_paths": []})["source_paths"].append(stored_path)

    print(json.dumps({
        "records": {table: len(rows(source, table)) for table in TABLES},
        "topics": len(topics), "unique_documents": len(documents),
        "bytes": sum(item["path"].stat().st_size for item in documents.values()),
    }, indent=2))
    if args.dry_run:
        return

    if args.mcp_sql_dir:
        for digest, item in documents.items():
            blob_path = f"documents/{digest}.pdf"
            state = manifest["documents"].setdefault(digest, {"blob_path": blob_path, "uploaded": False})
            if not state["uploaded"]:
                upload(item["path"], blob_path, os.environ["BLOB_BASE_URL"], os.environ["BLOB_READ_WRITE_TOKEN"])
                state["uploaded"] = True
                manifest_path.write_text(json.dumps(manifest, indent=2))
        write_mcp_sql(Path(args.mcp_sql_dir), source, topics, documents, uploads_dir, owner_id)
        print(f"PDF upload complete. Supabase MCP SQL batches written to {args.mcp_sql_dir}.")
        return

    if args.json_payload:
        for digest, item in documents.items():
            blob_path = f"documents/{digest}.pdf"
            state = manifest["documents"].setdefault(digest, {"blob_path": blob_path, "uploaded": False})
            if not state["uploaded"]:
                upload(item["path"], blob_path, os.environ["BLOB_BASE_URL"], os.environ["BLOB_READ_WRITE_TOKEN"])
                state["uploaded"] = True
                manifest_path.write_text(json.dumps(manifest, indent=2))
        Path(args.json_payload).write_text(json.dumps(build_hosted_payload(source, topics, documents, uploads_dir, owner_id)), encoding="utf-8")
        print(f"PDF upload complete. Private import payload written to {args.json_payload}.")
        return

    # The hosted deployment uses Supavisor's transaction pooler, which does not
    # support psycopg prepared statements.
    with psycopg.connect(os.environ["POSTGRES_URL"], prepare_threshold=None) as database:
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
                    (owner_id, blob_path, item["path"].name, item["path"].stat().st_size, pdf_page_count(item["path"]), digest),
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
