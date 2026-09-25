# Setting up the home server (Windows)

The home server runs on one Windows computer on the home network. Other devices (tablets, laptops, phones) open it in a browser. Nothing is exposed to the internet: no router port forwarding or public tunnel is needed, and the server refuses requests from outside the private network.

## 1. Install

1. Install [Git](https://git-scm.com/downloads), [Python 3.11+](https://www.python.org/downloads/) (tick "Add python.exe to PATH") and [Node.js LTS](https://nodejs.org/).
2. Clone the code **outside Google Drive and OneDrive**:
   ```powershell
   git clone https://github.com/hermann-ago/Homeschooling "$env:USERPROFILE\source\Homeschooling"
   cd "$env:USERPROFILE\source\Homeschooling"
   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
   ```
3. Optional: put `GEMINI_API_KEY=…` in `backend\.env` to enable curriculum analysis and the AI learning tools.

Local data (the cache, pending changes, paired devices and the protected Google authorization) lives in `%LOCALAPPDATA%\Homeschooling`. The server refuses to put it in a synced folder.

## 2. Start and stop

- **Start:** double-click `Start Homeschooling.cmd`. It starts the server if it isn't running, prints the address for other devices (for example `http://192.168.1.20:8000`) and opens the app.
- **Stop:** double-click `Stop Homeschooling.cmd`. It first asks the recorded server to finish syncing, then stops only that process. It never stops other programs that use the same port.
- **Status:** run `backend\venv\Scripts\python launcher\homeschooling.py status`.

While the server runs, it asks Windows not to sleep. Keep the computer on and connected when others need the app. Ending a lesson does not stop the server.

## 3. Pair devices

1. On any device, open the address and choose **A learner** or **A parent**. The device then shows a 6-digit code.
2. On the host computer, open the app. The **Devices waiting to pair** list shows the request. Type the code and approve it.
3. The device now holds a Homeschooling credential. It never receives Google credentials.

Parent devices can change settings, children, subjects, schedules, sync and maintenance. Learner devices can use lessons, reading, handwriting and checklists, but never see teacher-only material. You can remove devices in **Settings → Home server → Paired devices**.

## 4. Connect Google (host computer only)

1. In [Google Cloud Console](https://console.cloud.google.com/), select or create a project.
2. Enable the **Google Drive API** and the **Google Sheets API**.
3. Configure the OAuth consent screen as "External" in testing mode, and add your Google account as a test user.
4. Go to **Credentials → Create credentials → OAuth client ID → Desktop app**, then download the JSON file.
5. On the host computer, go to **Settings → Home server**:
   1. Choose **Add Desktop OAuth client file** and select the JSON.
   2. Choose **Connect Google** and approve access. Google redirects back to `127.0.0.1` on this computer, and the server uses PKCE.
6. The server then creates `Books`, `Student Work`, `Audio`, `Annotations`, `Tutor Content` and `Backups` inside the [Homeschooling folder](https://drive.google.com/drive/folders/1HnHCy3dOXlAMeQUkU8R9-lm8esx01hMR). It also creates the **Homeschooling Database** workbook there.

About the permissions:

- **See your Google Drive files (read-only)** lets the app find books that already sit beneath the Homeschooling folder and link them by file ID, without copying them. Google's permission covers your whole Drive. The app itself refuses any file outside the Homeschooling folder.
- **Files created by this app** covers the workbook and everything the app creates: uploaded books, handwriting, audio, student work and backups.

If Google authorization expires or is revoked, changes stay **pending** on the host and nothing is lost. The sync indicator asks a parent to reconnect Google, on the host computer.

## 5. Editing the spreadsheet by hand

The home server is the only writer. Before editing cells in the workbook, choose **Settings → Home server → Start maintenance mode**.

While maintenance mode is on, changes pause on every device. When you finish editing, choose **I finished editing — check and resume**. The server then reloads and validates every tab (columns, types, IDs and relationships) and resumes only if the workbook is valid. If there are problems, it lists them and stays paused.

If a cell is edited without maintenance mode, the affected change is marked **needs reconciliation** instead of being overwritten. You can retry it or set it aside in **Settings → Sync**. Set-aside changes are kept under `%LOCALAPPDATA%\Homeschooling\store\queue\discarded`.
