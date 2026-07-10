@echo off
cd /d "%~dp0"
title BTC5MIN convert

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

if /i "%~1"=="all" (
  echo [%TIME%] Rigenerazione completa txt da data\YYYY-MM-DD\bin ...
  "%PY%" -m src.convert
) else (
  echo [%TIME%] Conversione bin -^> txt in data\YYYY-MM-DD\bin ...
  "%PY%" -m src.convert --sync
)
if errorlevel 1 goto :err
echo.
pause
exit /b 0

:err
echo.
pause
exit /b 1
