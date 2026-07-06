@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title BTC5MIN convert
set COUNT=0
echo Conversione bin senza txt corrispondente in data\
echo.
for %%f in (data\*.bin) do (
  if not exist "%%~dpnf.txt" (
    echo %%~nxf
    python -m src.convert "%%f" -o "%%~dpnf.txt"
    if errorlevel 1 (
      echo.
      echo ERRORE su %%f - codice !ERRORLEVEL!
      pause
      exit /b 1
    )
    set /a COUNT+=1
  )
)
echo.
if !COUNT! EQU 0 (
  echo Nessun bin da convertire.
) else (
  echo Fatto - !COUNT! file convertiti.
)
pause
