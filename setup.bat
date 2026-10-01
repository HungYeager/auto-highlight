@echo off
:: ============================================================
:: setup.bat  —  First-time setup for Viral Bodycam Clipper
:: Run ONCE before using run.bat
:: ============================================================
title Viral Bodycam Clipper — Setup
color 0A
cls

echo.
echo  =====================================================
echo    Viral Bodycam Clipper  —  Setup
echo    Powered by Google Gemini AI + FFmpeg
echo  =====================================================
echo.

:: ── 1. Detect Python ─────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% equ 0 ( set PYTHON=python & goto :py_ok )
py --version >nul 2>&1
if %errorlevel% equ 0 ( set PYTHON=py     & goto :py_ok )
echo  [ERROR] Python not found.
echo  Download Python 3.10+ from: https://python.org/downloads
echo  Make sure to check "Add Python to PATH" during install.
echo.
pause
exit /b 1
:py_ok
echo  [OK] Python found.

:: ── 2. Install pip packages ───────────────────────────────
echo.
echo  Installing Python packages...
%PYTHON% -m pip install --upgrade pip --quiet
%PYTHON% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Package install failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  [OK] Packages installed.
if not exist "config.json" (
    if exist "config.example.json" copy "config.example.json" "config.json" >nul
)

:: ── 3. Check FFmpeg ───────────────────────────────────────
echo.
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] FFmpeg found.
) else (
    echo  [WARNING] FFmpeg not found.
    echo.
    echo  FFmpeg is required to process videos.
    echo  Install options:
    echo    Option A ^(recommended^):  winget install --id Gyan.FFmpeg -e
    echo    Option B ^(manual^):        https://ffmpeg.org/download.html
    echo.
    echo  After installing FFmpeg, restart this setup to verify,
    echo  or just run run.bat — the app will detect FFmpeg on startup.
    echo.
)

:: ── 4. Done ───────────────────────────────────────────────
echo.
echo  =====================================================
echo    Setup complete!  Run  run.bat  to launch.
echo  =====================================================
echo.
pause
