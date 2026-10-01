@echo off
title Push OpenCut Studio to GitHub
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push_to_github.ps1"

if errorlevel 1 (
    echo.
    echo [Co loi xay ra trong qua trinh thuc thi]
    pause
)
