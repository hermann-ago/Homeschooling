@echo off
rem Makes the home server start by itself whenever this Windows user signs in.
rem Double-click it in File Explorer: run from inside a Microsoft Store app (such as
rem Claude), Windows keeps the setting in that app's private copy and never uses it.
cd /d "%~dp0"
"backend\venv\Scripts\python.exe" launcher\homeschooling.py autostart on
pause
