# Migration and cutover runbook

The migration has three stages: storage and runtime replacement (this code), tutoring and read-along integration (this code), and then the verified data migration and cutover described here.

After cutover there is **one authoritative record**: the Homeschooling Database workbook. Excel, Supabase and Sheets are never synchronized with each other.

Keep these untouched until the migration is accepted:

- the previous Vercel/Supabase deployment (rollback point: commit `1104cd4`),
- the hosted database,
- the `Lucas - History` folder with its Excel tracker.

Deleting hosted resources is a separate, final decision.

> **Before merging this branch:** if the Vercel project still auto-deploys `main`, disconnect its Git integration (or pause deployments) first. Otherwise, merging would replace the working hosted app before cutover.

All commands run on the host computer from `backend\` with `venv\Scripts\python -m …`. Reports are written to `%LOCALAPPDATA%\Homeschooling\migration-reports`.

## 0. Prepare the host

1. Complete SETUP_GUIDE.md: install, start, pair a parent device and connect Google.
2. Confirm that **Settings → Home server** links to an empty *Homeschooling Database* workbook.
3. Install the migration extras:
   ```powershell
   venv\Scripts\pip install -r requirements-migration.txt
   cd migration\legacy; npm install; cd ..\..
   ```

## 1. Inventory and export the hosted app (read-only)

The GitHub repository contains the application code, not necessarily its live data. Exporting needs authenticated access:

- `POSTGRES_URL`: read access to the Supabase database,
- `BLOB_READ_WRITE_TOKEN`: the Vercel Blob store.

Set both for this terminal only:

```powershell
$env:POSTGRES_URL = "<from Supabase>"; $env:BLOB_READ_WRITE_TOKEN = "<from Vercel>"
venv\Scripts\python -m migration.export_hosted --out "%LOCALAPPDATA%\Homeschooling\export-1"
```

This writes every table (children, subjects, documents, topics, schedules, completions with their timestamps, annotations with their revisions, enrichment content and settings) plus the book PDFs named by SHA-256, and `manifest.json` with counts and checksums. Nothing hosted is changed. Keep the export folder.

## 2. Stage the replacement

```powershell
venv\Scripts\python -m migration.import_hosted --export "%LOCALAPPDATA%\Homeschooling\export-1" --dry-run
venv\Scripts\python -m migration.import_hosted --export "%LOCALAPPDATA%\Homeschooling\export-1"
```

- Source IDs, timestamps and annotation revisions are preserved.
- Books already beneath the Homeschooling folder with the same SHA-256 are referenced by Drive file ID. The others are uploaded to `Books`.
- Annotation strokes and enrichment content become Drive files, indexed in Sheets.
- Re-running is safe: finished batches are skipped by their operation IDs.

## 3. Import the tutoring evidence

`--source` is only read; the folder is not changed. With Google Drive for desktop, the path is usually the one below:

```powershell
venv\Scripts\python -m migration.import_history --source "G:\My Drive\Casa, Família e Vida Prática\Homeschooling\Lucas - History" --dry-run
venv\Scripts\python -m migration.import_history --source "G:\My Drive\Casa, Família e Vida Prática\Homeschooling\Lucas - History"
```

The import brings in:

- **Tracker workbook:** preferences, sessions, answers and reviews. First answers stay verbatim, and help and revisions are kept separately. Assisted answers are never marked independent.
- **Chapters and teacher key:** chapter tests, the teacher key (with its known conflicts) and the reviewed question-to-topic mappings.
- **Reviewed passages:** their exact sentences, boundaries and review notes.
- **Cached narration:** each Neural2 track is marked synchronized only if its original hash (voice, rate and passage) matches the reviewed passage. The Robin Hood ElevenLabs audio is preserved as legacy audio. Audio and evidence photos are referenced by Drive file ID and not copied.

Topics are merged with any existing History topics by **source document and page range**, never by title alone. An ambiguous overlap is reported and not created. Review it, then rerun with `--create-unmatched` if the new topics are wanted.

### The unfinished lesson

Lucas's Genghis Khan discussion is imported as an **unfinished** session:

- its observations are kept verbatim,
- the reading signal is noted,
- the next prompt is *"What did the man who spoke up do next?"*,
- C21-T01 stays incomplete, and no mastery is inferred.

`context/session.json` is reported as superseded, because the workbook already records that C20-T02 session. Any entries in `pending_updates.json` are reported as a conflict and are never imported silently.

## 4. Reconcile

Wait until **Settings → Sync** shows everything saved to Google, then run:

```powershell
venv\Scripts\python -m migration.reconcile --export "%LOCALAPPDATA%\Homeschooling\export-1" --history "<Lucas - History folder>"
```

It compares:

- counts and IDs per table and relationships,
- book hashes, using Drive's SHA-256,
- annotation revisions and stroke content,
- sample schedule and completion values,
- every History session, answer (the first answer verbatim) and review,
- completed topics and the Genghis checkpoint.

Conflicting evidence is listed, not overwritten. Resolve each conflict, for example by re-exporting, fixing in maintenance mode or recording a decision, and rerun until the report is clean.

## 5. Back up and test a restore

```powershell
venv\Scripts\python -m migration.backup create
venv\Scripts\python -m migration.backup restore "%LOCALAPPDATA%\Homeschooling\backups\<file>.json"
```

`create` writes the backup to Drive `Backups` and to the local copy. `restore` loads it into a **new** workbook and verifies every tab cell for cell; the live workbook is not changed. Afterwards you can move the restored test workbook to Drive trash.

## 6. Cut over

1. Stop writes to the old systems:
   - **Hosted app:** tell the family to stop using it, and pause the Vercel deployment (for example by removing the production domain or pausing the project).
   - **Excel tracker:** end any History lesson that is using it.
2. If anything changed since step 1, export again into a new folder and run steps 2–4 against it. Batches that were already imported are skipped. New rows go through reconciliation; nothing is overwritten.
3. Verify the app:
   - two devices (a parent and a learner) see schedules, completions and handwriting as before,
   - "Start today's lesson" resumes the Genghis discussion,
   - the reader shows the correct pages and boundaries.
4. `venv\Scripts\python -m migration.cutover check` must report `ready`: everything saved, no maintenance mode, a clean reconciliation and a backup.
5. Update the History project's entry instructions:
   ```powershell
   venv\Scripts\python -m migration.cutover history-instructions --source "<Lucas - History folder>"          # preview
   venv\Scripts\python -m migration.cutover history-instructions --source "<Lucas - History folder>" --apply  # write
   ```
   The originals are first copied to `backups\pre-integrated-tutor\` in that folder. From now on, the History tutor uses the MCP tools and stops writing to Excel.

## 7. Retire dependencies

The active runtime no longer uses Vercel, Supabase or Blob; this branch removes them. Keep the export folder, the hosted project and the History archive until the family accepts the migration. Deleting the Supabase project, the Vercel project and the Blob store is a separate final action.

## Rollback (before acceptance)

1. Stop the home server.
2. Restore the Vercel deployment of `1104cd4` and the History project's original `AGENTS.md` / `START_HERE.md` from `backups\pre-integrated-tutor\`.

The old systems were never modified. Anything recorded in the new workbook after cutover stays in that workbook, and can be exported with `migration.backup create` if needed.
