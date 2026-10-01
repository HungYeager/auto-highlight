@echo off
title Build OpenCutStudio Standalone Launcher
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   Build OpenCutStudio.exe Standalone Launcher (~11MB)
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtualenv khong ton tai. Vui long chay setup.bat truoc.
    pause
    exit /b 1
)

if exist "%~dp0updater_config.json" (
    set "EXTRA_DATA=--add-data "%~dp0updater_config.json;.""
) else (
    set "EXTRA_DATA="
)

.venv\Scripts\python.exe -m PyInstaller launcher.py --onefile --noconsole --name "OpenCutStudio" --specpath "%~dp0dist_launcher" %EXTRA_DATA% --clean --distpath "%~dp0dist_launcher"

if errorlevel 1 (
    echo.
    echo [LOI] Qua trinh dong goi that bai!
    pause
    exit /b 1
)

echo.
echo ========================================================
echo  [THANH CONG] File Launcher (~11MB) da duoc tao tai:
echo  dist_launcher\OpenCutStudio.exe
echo ========================================================
echo.
pause
