@echo off
cd /d "%~dp0"
title BTC5MIN sync poly
echo [%TIME%] Avvio sync...

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

"%PY%" -u sync.py
if errorlevel 1 goto :err
echo.
pause
exit /b 0

:err
echo.
pause
exit /b 1
