@echo off
rem Entwicklungsmodus: Backend (Port 8011) und Vite mit Live-Neuladen (Port 5173) in zwei Fenstern.
rem Fuer den normalen Gebrauch start.vbs nehmen (ohne Fenster).
cd /d "%~dp0"
start "Handball xG - Backend" cmd /k "cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8011"
start "Handball xG - Oberflaeche" cmd /k "cd frontend && npm run dev"
timeout /t 6 >nul
start http://localhost:5173
