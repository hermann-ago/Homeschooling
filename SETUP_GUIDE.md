# Setting up the home server (Windows)

The home server runs on one Windows computer on the home network. Other devices (tablets, laptops, phones) open it in a browser. Nothing is exposed to the internet: no router port forwarding or public tunnel is needed, and the server refuses requests from outside the private network.

## 1. Install

1. Install [Git](https://git-scm.com/downloads), [Python 3.11+](https://www.python.org/downloads/) (tick "Add python.exe to PATH") and [Node.js LTS](https://nodejs.org/).
2. Clone the code into `C:\CodingLocal\Homeschooling`, **outside Google Drive and OneDrive** (the Desktop is usually synced by OneDrive):
   ```powershell
   git clone https://github.com/hermann-ago/Homeschooling C:\CodingLocal\Homeschooling
   cd C:\CodingLocal\Homeschooling
   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
   ```
3. Optional: put `GEMINI_API_KEY=…` in `backend\.env` to enable curriculum analysis and the AI learning tools.

Everything the computer keeps for the app lives in the project's **`data` folder** (`C:\CodingLocal\Homeschooling\data`), which Git ignores:

| In `data\` | What it is |
|---|---|
| `homeschooling.sqlite3` | the database (the one authoritative record) |
| `backups\` | local copies of the daily backups |
| `secrets\` | paired devices and the tutor credential |
| `home-tutor\` | the narration usage ledger |
| `migration\`, `migration-reports\` | the Supabase export and migration reports |
| `run\`, `responses\`, `cache\` | server bookkeeping |

The server refuses to start if this folder is inside Google Drive or OneDrive, because syncing a live database file can corrupt it. Verified backup copies go to Drive every day instead.

## 2. Start and stop

- **Start:** double-click `Start Homeschooling.cmd`. It starts the server if it isn't running, prints the address for other devices (for example `http://192.168.1.20:8000`) and opens the app.
- **Stop:** double-click `Stop Homeschooling.cmd`. It asks the recorded server to stop (the server writes a backup to the Drive folder first), then stops only that process. It never stops other programs that use the same port.
- **Status:** run `backend\venv\Scripts\python launcher\homeschooling.py status`.
- **Start by itself:** run `backend\venv\Scripts\python launcher\homeschooling.py autostart on` once. From then on the server starts without a window whenever this Windows user signs in, so anyone can switch the computer on and sign in. `autostart off` turns it off again, `autostart status` shows the setting, and Task Manager lists it under **Startup apps** as "Homeschooling home server". Starting and stopping by hand still works the same way.

While the server runs, it asks Windows not to sleep. Keep the computer on and connected when others need the app. Ending a lesson does not stop the server.

## 3. Pair devices

1. On any device, open the address and choose **A learner** or **A parent**. The device then shows a 6-digit code.
2. On the host computer, open the app. The **Devices waiting to pair** list shows the request. Type the code and approve it.
3. The device now holds a Homeschooling credential. It never receives Google credentials.

Parent devices can change settings, children, subjects, schedules and backups. Learner devices can use lessons, reading, handwriting and checklists, but never see teacher-only material. You can remove devices in **Settings → Home server → Paired devices**.

## 4. The Homeschooling Drive folder

1. Install [Google Drive for desktop](https://www.google.com/drive/download/) on the host computer and sign in with the family account.
2. The server looks for `G:\My Drive\Casa, Família e Vida Prática\Homeschooling` (or the `Meu Drive` spelling). If your folder is elsewhere, set it in **Settings → Home server → Homeschooling Drive folder** on the host computer, or put `HOMESCHOOLING_DRIVE_FOLDER=<path>` in `backend\.env`.
3. The app organises the folder **Kid → Grade → Subject** and creates the folders itself. Drive for desktop uploads whatever the app writes there.

   ```
   Homeschooling\
     Lucas\
       3rd Grade\
         History\
           Books\           the PDFs the lessons use
           Handwriting\     pen strokes drawn on book pages
           Student Work\    photos of answers and other evidence
           Audio\           read-along narration
           Lesson Content\  AI quizzes, summaries and reviewed passages
         Math\  Science\  Language Arts\  Portuguese\
     Mila\
       1st Grade\
         Language Arts\  Math\  Science\  Português\
     _App Backups\          daily database backups + the read-only Excel copy
     _Unassigned Books\     books no subject uses yet
     _Archive\              retired folders; the app never reads them
   ```

   - A subject's folder is fixed when the subject is created. Changing a child's grade later does not move anything: next year's subjects get the new grade folder, so each school year stays together.
   - A child without a grade (for example "N/A") has no grade level: `Joshua\Reading\…`.
   - To add a book by hand, drop the PDF into the subject's `Books` folder and link it from the subject on the **Curriculum** page ("Use a book already in Google Drive"). A book used by two children stays in the folder of the first one and is shared.
   - Don't rename or move files inside these folders; the app records where each file is. Books are found again by checksum if they move, other files are not.
4. **For lessons without internet**, right-click the Homeschooling folder in File Explorer and choose **Offline access → Available offline**. Drive's default "stream files" mode downloads a file only when it is first opened, so without this a book that was never opened on the host cannot open while offline.

The database itself never depends on the internet: saving works offline, and Drive uploads the new files when the connection returns.

Only the server reads the folder. Browsers and AI tutors get books and audio through the server and never see the folder or any Google credential. The server refuses any path outside the Homeschooling folder.

## 5. Backups and the Excel copy

- Every day, and whenever the server stops, a verified copy of the database is written to the folder's `_App Backups` (and to the project's `data\backups`). The newest 30 are kept. **Settings → Home server → Back up now** makes one on demand.
- `_App Backups\Homeschooling Database (read-only copy).xlsx` shows every table for reading. It is rewritten daily and leaves out answer keys. Edits in it are not read back; make changes in the app.
- To check a backup: `backend\venv\Scripts\python -m migration.backup verify` (from `backend`).
- To restore: stop the server, keep a copy of `data\homeschooling.sqlite3`, copy the chosen backup over it and start the server.
