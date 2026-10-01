@echo off
title OpenCut Bodycam Studio v2.0
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   OpenCut Bodycam Studio v2.0 - Web Engine
echo ========================================================
echo.

set "PY_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PY_EXE%" (
    echo [0/2] First time setup: Creating Python virtual environment...
    python -m venv .venv
    call "%~dp0.venv\Scripts\activate.bat"
    echo Installing dependencies from requirements.txt...
    pip install -r requirements.txt
)

if not exist "config.json" (
    if exist "config.example.json" copy "config.example.json" "config.json" >nul
)

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo [1/2] Starting FastAPI server at http://127.0.0.1:8000 ...
echo [2/2] Opening OpenCut Studio in browser...
echo.

"%PY_EXE%" -X utf8 server.py

if errorlevel 1 (
    echo.
    echo [Server stopped with error]
    pause
)
