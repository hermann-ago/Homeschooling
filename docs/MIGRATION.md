# Migration and cutover runbook

The migration has three stages: storage and runtime replacement (this code), tutoring and read-along integration (this code), and then the verified data migration and cutover described here.

After cutover there is **one authoritative record**: the home server's SQLite database (`data\homeschooling.sqlite3` in the project folder), with its files in the synced Homeschooling Drive folder. The Excel tracker, Supabase and the new database are never synchronized with each other. The daily Excel copy the server writes is read-only output, not a second record.

> **Status (2026-09-26):** the hosted app is retired. The Vercel project was deleted, and the Supabase project "Homeschooling" was paused so its owner can delete it from the Supabase dashboard. Its complete data is in `data\migration\export-20260925-225941-connector` and was checked against the live database before the pause: every table has the same row count and latest change. Only the login mapping (`family_accounts`) was left out, and the home server doesn't need it. Always run the steps below with `--export` pointing at that folder. `POSTGRES_URL` no longer applies.

Keep the `Lucas - History` folder with its Excel tracker untouched until the migration is accepted, and keep the export folder as long as you want the old records. The code before the move to the home server is commit `1104cd4`.

All commands run on the host computer from `backend\` with `venv\Scripts\python -m …`. Reports are written to the project's `data\migration-reports`.

## 0. Prepare the host

1. Complete SETUP_GUIDE.md: install, start and check the Drive folder (**Settings → Home server** shows it as Available).
2. Mark the Homeschooling folder **Available offline** (the import reads the History folder's files and books).
3. Install the migration extras:
   ```powershell
   venv\Scripts\pip install -r requirements-migration.txt
   cd migration\legacy; npm install; cd ..\..
   ```

## 1. Dry run (changes nothing)

Put the hosted credentials in `backend\.env` (never commit it):

```
POSTGRES_URL=<read access to the Supabase database>
BLOB_READ_WRITE_TOKEN=<the Vercel Blob store, for the book PDFs>
```

Then run one command:

```powershell
venv\Scripts\python -m migration.dry_run
```

It exports the hosted data read-only into `data\migration\export-<time>`, imports that export and the `Lucas - History` folder into a **throwaway copy** of the database, and reconciles the copy against both sources. Files the import would add are written to a temporary folder instead of Google Drive. It prints a summary to paste back for review and saves the full report.

- `--export <folder>` reuses an earlier export; `--no-hosted` checks only the History folder.
- Without `POSTGRES_URL`, the hosted part is skipped with a warning. Without `BLOB_READ_WRITE_TOKEN` and Node, book PDFs are not downloaded and the book checks are incomplete.

Repeat until the summary is clean, then continue with the real import below.

## 2. Export the hosted app (read-only)

The GitHub repository contains the application code, not necessarily its live data. Exporting needs authenticated access:

- `POSTGRES_URL`: read access to the Supabase database,
- `BLOB_READ_WRITE_TOKEN`: the Vercel Blob store.

With both in `backend\.env` (or set for this terminal only):

```powershell
venv\Scripts\python -m migration.export_hosted --out ..\data\migration\export-1
```

(You can instead reuse the export folder the dry run created.)

This writes every table (children, subjects, documents, topics, schedules, completions with their timestamps, annotations with their revisions, enrichment content and settings) plus the book PDFs named by SHA-256, and `manifest.json` with counts and checksums. Nothing hosted is changed. Keep the export folder.

## 3. Import the hosted data

```powershell
venv\Scripts\python -m migration.import_hosted --export ..\data\migration\export-1
```

- Source IDs, timestamps and annotation revisions are preserved.
- Each subject gets its Kid → Grade → Subject folder (see SETUP_GUIDE.md §4).
- Books already in the Homeschooling folder with the same SHA-256 are referenced where they are. The others are copied into the `Books` folder of the subject that uses them (`_Unassigned Books` when none does), from the export or from a `--books-from` folder.
- `--books-from <folder>` is only read. Use it for book copies kept outside the Drive folder.
- The first app's upload folder has already been sorted into the subject `Books` folders (11 of the 20 books, matching checksums). Its leftovers, including the first app's `homeschool.db`, are in `_Archive\homeschooling_data`. The 9 remaining documents are 4 distinct books: No mundo das consoantes – Volume 2 (Mila, Português), Sparks And Stars Parent Guide (Mila, Science), Good and Beautiful Math 1_compressed (Mila, Math) and Level 4 Course Book Part 1 (Lucas, Language Arts). Put the same files into those `Books` folders; they are matched by name and exact size.
- Annotation strokes and enrichment content become files in the Drive folder, indexed in the database.
- Re-running is safe: finished batches are skipped by their operation IDs.

## 4. Import the tutoring evidence

`--source` is only read; the folder is not changed. With Google Drive for desktop, the path is usually the one below:

```powershell
venv\Scripts\python -m migration.import_history --source "G:\My Drive\Casa, Família e Vida Prática\Homeschooling\Lucas - History"
```

The import brings in:

- **Tracker workbook:** preferences, sessions, answers and reviews. First answers stay verbatim, and help and revisions are kept separately. Assisted answers are never marked independent.
- **Chapters and teacher key:** chapter tests, the teacher key (with its known conflicts) and the reviewed question-to-topic mappings.
- **Reviewed passages:** their exact sentences, boundaries and review notes.
- **Cached narration:** each Neural2 track is marked synchronized only if its original hash (voice, rate and passage) matches the reviewed passage. The Robin Hood ElevenLabs audio is preserved as legacy audio.
- **Files:** the textbook, the tests, audio and evidence photos are copied into Lucas's History `Books`, `Audio` and `Student Work` folders, so the History folder can be archived later without breaking any record. The originals stay where they are.

Topics are merged with any existing History topics by **source document and page range**, never by title alone. An ambiguous overlap is reported and not created. Review it, then rerun with `--create-unmatched` if the new topics are wanted.

If the app already holds the textbook as a different file (same page count, and at least 90% of the curriculum's topic titles on it), that document is treated as the **same book**: it keeps its ID and topics but now uses the History folder's copy, and topics on it are also matched by title (a combined tracker topic "A / B" by any part). The app's completions are kept; only those the tracker explicitly marks otherwise are reported. An app topic inside a combined tracker topic is kept and reported as a possible duplicate.

Books the old app recorded without a checksum are linked to a PDF in the Drive folder (or a `--books-from` folder) with the same name and exact size.

### The unfinished lesson

Lucas's Genghis Khan discussion is imported as an **unfinished** session:

- its observations are kept verbatim,
- the reading signal is noted,
- the next prompt is *"What did the man who spoke up do next?"*,
- C21-T01 stays incomplete, and no mastery is inferred.

`context/session.json` is reported as superseded, because the workbook already records that C20-T02 session. Any entries in `pending_updates.json` are reported as a conflict and are never imported silently.

## 5. Reconcile

```powershell
venv\Scripts\python -m migration.reconcile --export ..\data\migration\export-1 --history "<Lucas - History folder>"
```

It compares:

- counts and IDs per table and relationships,
- book hashes, and every file the database refers to (present in the Drive folder, matching its checksum),
- annotation revisions and stroke content,
- sample schedule and completion values,
- every History session, answer (the first answer verbatim) and review,
- completed topics and the Genghis checkpoint.

Conflicting evidence is listed, not overwritten. Resolve each conflict, for example by re-exporting or recording a decision, and rerun until the report is clean.

## 6. Back up and test a restore

```powershell
venv\Scripts\python -m migration.backup create
venv\Scripts\python -m migration.backup verify
```

`create` writes an integrity-checked copy of the database to the Drive folder's `_App Backups` and to `data\backups`. `verify` opens a copy of the newest backup on its own (never the live database), checks its integrity and compares every table's row count with the live database.

## 7. Cut over

1. Stop writes to the old systems:
   - **Hosted app:** tell the family to stop using it, and pause the Vercel deployment (for example by removing the production domain or pausing the project).
   - **Excel tracker:** end any History lesson that is using it.
2. If anything changed since step 1, export again into a new folder and run steps 3–5 against it. Batches that were already imported are skipped. New rows go through reconciliation; nothing is overwritten.
3. Verify the app:
   - two devices (a parent and a learner) see schedules, completions and handwriting as before,
   - "Start today's lesson" resumes the Genghis discussion,
   - the reader shows the correct pages and boundaries.
4. `venv\Scripts\python -m migration.cutover check` must report `ready`: the Drive folder is available, the newest reconciliation is clean and a backup newer than it exists.
5. Update the History project's entry instructions:
   ```powershell
   venv\Scripts\python -m migration.cutover history-instructions --source "<Lucas - History folder>"          # preview
   venv\Scripts\python -m migration.cutover history-instructions --source "<Lucas - History folder>" --apply  # write
   ```
   The originals are first copied to `backups\pre-integrated-tutor\` in that folder. From now on, the History tutor uses the MCP tools and stops writing to Excel.

## 8. Retire dependencies

The active runtime no longer uses Vercel, Supabase or Blob; this branch removes them. Keep the export folder, the hosted project and the History archive until the family accepts the migration. Deleting the Supabase project, the Vercel project and the Blob store is a separate final action.

## Rollback (before acceptance)

1. Stop the home server.
2. Restore the History project's original `AGENTS.md` / `START_HERE.md` from `backups\pre-integrated-tutor\`, so History lessons use the Excel tracker again.

The hosted app can no longer be restored: its Vercel project was deleted and its Supabase project is being deleted. Its data survives only in the export folder. The History folder was never modified. Anything recorded after cutover stays in the new database and its backups (and in the read-only Excel copy).
