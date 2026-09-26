# Setting up the home server (Windows)

The home server runs on one Windows computer on the home network. Other devices (tablets, laptops, phones) open it in a browser. Nothing is exposed to the internet: no router port forwarding or public tunnel is needed, and the server refuses requests from outside the private network.

## 1. Install

1. Install [Git](https://git-scm.com/downloads), [Python 3.11+](https://www.python.org/downloads/) (tick "Add python.exe to PATH") and [Node.js LTS](https://nodejs.org/).
2. Clone the code **outside Google Drive**. A OneDrive-synced folder such as the Desktop works, because local data never lives next to the code:
   ```powershell
   git clone https://github.com/hermann-ago/Homeschooling "$env:USERPROFILE\source\Homeschooling"
   cd "$env:USERPROFILE\source\Homeschooling"
   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
   ```
3. Optional: put `GEMINI_API_KEY=…` in `backend\.env` to enable curriculum analysis and the AI learning tools.

Local data lives in `%LOCALAPPDATA%\Homeschooling`: the database (`homeschooling.sqlite3`), local backup copies, caches and paired devices. The server refuses to put it in a synced folder, because Drive syncing a live database file can corrupt it. Only verified backup copies go to Drive.

## 2. Start and stop

- **Start:** double-click `Start Homeschooling.cmd`. It starts the server if it isn't running, prints the address for other devices (for example `http://192.168.1.20:8000`) and opens the app.
- **Stop:** double-click `Stop Homeschooling.cmd`. It asks the recorded server to stop (the server writes a backup to the Drive folder first), then stops only that process. It never stops other programs that use the same port.
- **Status:** run `backend\venv\Scripts\python launcher\homeschooling.py status`.

While the server runs, it asks Windows not to sleep. Keep the computer on and connected when others need the app. Ending a lesson does not stop the server.

## 3. Pair devices

1. On any device, open the address and choose **A learner** or **A parent**. The device then shows a 6-digit code.
2. On the host computer, open the app. The **Devices waiting to pair** list shows the request. Type the code and approve it.
3. The device now holds a Homeschooling credential. It never receives Google credentials.

Parent devices can change settings, children, subjects, schedules and backups. Learner devices can use lessons, reading, handwriting and checklists, but never see teacher-only material. You can remove devices in **Settings → Home server → Paired devices**.

## 4. The Homeschooling Drive folder

1. Install [Google Drive for desktop](https://www.google.com/drive/download/) on the host computer and sign in with the family account.
2. The server looks for `G:\My Drive\Casa, Família e Vida Prática\Homeschooling` (or the `Meu Drive` spelling). If your folder is elsewhere, set it in **Settings → Home server → Homeschooling Drive folder** on the host computer, or put `HOMESCHOOLING_DRIVE_FOLDER=<path>` in `backend\.env`.
3. The server creates `Books`, `Student Work`, `Audio`, `Annotations`, `Tutor Content` and `Backups` inside that folder. Drive for desktop uploads whatever the app writes there.
4. **For lessons without internet**, right-click the Homeschooling folder in File Explorer and choose **Offline access → Available offline**. Drive's default "stream files" mode downloads a file only when it is first opened, so without this a book that was never opened on the host cannot open while offline.

The database itself never depends on the internet: saving works offline, and Drive uploads the new files when the connection returns.

Only the server reads the folder. Browsers and AI tutors get books and audio through the server and never see the folder or any Google credential. The server refuses any path outside the Homeschooling folder.

## 5. Backups and the Excel copy

- Every day, and whenever the server stops, a verified copy of the database is written to the folder's `Backups` (and to `%LOCALAPPDATA%\Homeschooling\backups`). The newest 30 are kept. **Settings → Home server → Back up now** makes one on demand.
- `Homeschooling Database (read-only copy).xlsx` in the Homeschooling folder shows every table for reading. It is rewritten daily and leaves out answer keys. Edits in it are not read back; make changes in the app.
- To check a backup: `backend\venv\Scripts\python -m migration.backup verify` (from `backend`).
- To restore: stop the server, keep a copy of `%LOCALAPPDATA%\Homeschooling\homeschooling.sqlite3`, copy the chosen backup over it and start the server.
