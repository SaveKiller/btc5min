@echo off
cd /d "%~dp0"
title BTC5MIN lighter synthetic rounds
echo [%TIME%] Build round sintetici Lighter (skip .txt gia presenti)...

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

set "INPUT=H:\ticks\lighter-fullrawticks\btc"
set "OUTPUT=H:\ticks\lighter-rounds5m"
if not "%~1"=="" set "WORKERS=%~1"
if "%WORKERS%"=="" set "WORKERS=12"

echo input:  %INPUT%
echo output: %OUTPUT%
echo workers: %WORKERS%
echo.

"%PY%" -u scripts\build_lighter_rounds.py all "%INPUT%" "%OUTPUT%" %WORKERS%
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
