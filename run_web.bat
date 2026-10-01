@echo off
title OpenCut Bodycam Studio v2.0
chcp 65001 >nul
echo ========================================================
echo   OpenCut Bodycam Studio v2.0 - Web Engine
echo ========================================================

cd /d "%~dp0"

:: ── Kill any process already using port 8000 (prevents WinError 10048) ──────
echo [0/2] Clearing port 8000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 "') do (
    if not "%%a"=="0" taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

if not exist ".venv\Scripts\activate.bat" (
    echo [0/2] First time setup: Creating Python virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing dependencies from requirements.txt...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

:: ── Ensure config.json exists ────────────────────────────────
if not exist "config.json" (
    if exist "config.example.json" copy "config.example.json" "config.json" >nul
)

:: ── Auto-Update Check (Tự động cập nhật code mới từ GitHub) ──
if exist "updater.py" (
    python updater.py
)

:: Set UTF-8 encoding to prevent charmap errors with Vietnamese filenames
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo [1/2] Starting FastAPI server at http://127.0.0.1:8000 ...
start /b python -X utf8 server.py

timeout /t 3 /nobreak >nul

echo [2/2] Opening OpenCut Studio...
start "" "msedge.exe" --app=http://127.0.0.1:8000 --window-size=1440,900 2>nul || ^
start "" "chrome.exe" --app=http://127.0.0.1:8000 --window-size=1440,900 2>nul || ^
start http://127.0.0.1:8000

echo Done! Server running at http://127.0.0.1:8000
