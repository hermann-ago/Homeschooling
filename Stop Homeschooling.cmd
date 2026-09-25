@echo off
rem Stops only the server process this launcher recorded. Other programs are never touched.
cd /d "%~dp0"
"backend\venv\Scripts\python.exe" launcher\homeschooling.py stop
pause
