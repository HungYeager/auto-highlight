@echo off
title OpenCutStudio - Build Release EXE
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   OpenCutStudio - Build Release Package (.exe + .zip)
echo ========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "build_opencutstudio.ps1"

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check the output above.
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
pause
