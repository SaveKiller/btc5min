@echo off
cd /d "%~dp0"
title dashV2

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m dashv2
) else (
    python -m dashv2
)
pause
