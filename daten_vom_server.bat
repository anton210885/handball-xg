@echo off
rem Holt die aktuelle Datenbank vom Online-Server auf diesen PC (die lokale wird vorher gesichert).
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
backend\.venv\Scripts\python.exe deploy\pull_db.py
echo.
pause
