@echo off
cd /d "%~dp0"
title BTC5MIN backfill intraday Lighter
echo [%TIME%] Backfill intraday: Hk negli header .txt Lighter (idempotente)...

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

set "ROUNDS=H:\ticks\lighter-rounds5m"
if not "%~1"=="" set "WORKERS=%~1"
if "%WORKERS%"=="" set "WORKERS=12"

echo rounds:  %ROUNDS%
echo workers: %WORKERS%
echo.

"%PY%" -u scripts\backfill_lighter_intraday.py "%ROUNDS%" %WORKERS%
if errorlevel 1 goto :err
echo.
echo [%TIME%] Completato.
pause
exit /b 0

:err
echo.
echo [%TIME%] Errore.
pause
exit /b 1
