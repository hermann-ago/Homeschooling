@echo off
rem Starts the shared home server (or reports that it is already running) and opens the app.
cd /d "%~dp0"
"backend\venv\Scripts\python.exe" launcher\homeschooling.py start %*
pause
