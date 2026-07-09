@echo off
cd /d "%~dp0"
title BTC5MIN sync poly
set HOST=ticksaver
set REMOTE=/opt/btc5min/data
set LISTFILE=%TEMP%\btc5min_sync_days.txt
set FILELIST=%TEMP%\btc5min_sync_files.txt
set SSH_OPTS=-o ConnectTimeout=15

echo Sync %HOST%:%REMOTE% -^> data\yyyy-mm-dd\bin e data\yyyy-mm-dd\txt
echo solo cartelle giorno yyyy-mm-dd, solo file mancanti, timestamp preservati
echo.

if not exist data mkdir data

echo Elenco cartelle giorno su remoto ...
ssh %SSH_OPTS% %HOST% "cd %REMOTE% && ls -d [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]" > "%LISTFILE%"
if errorlevel 1 goto :err

for /f "usebackq delims=" %%D in ("%LISTFILE%") do (
  echo %%D| findstr /r "^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$" >nul
  if not errorlevel 1 (
    call :sync_subdir %%D bin
    if errorlevel 1 goto :err
    call :sync_subdir %%D txt
    if errorlevel 1 goto :err
  )
)

call :sync_collector
if errorlevel 1 goto :err

echo.
echo Fatto.
pause
exit /b 0

:sync_subdir
set DAY=%1
set SUB=%2
ssh %SSH_OPTS% %HOST% "ls -1 %REMOTE%/%DAY%/%SUB%" > "%FILELIST%" 2>nul
if errorlevel 1 exit /b 0
if not exist "data\%DAY%\%SUB%" mkdir "data\%DAY%\%SUB%"
for /f "usebackq delims=" %%F in ("%FILELIST%") do (
  if not exist "data\%DAY%\%SUB%\%%F" (
    echo Scarico %DAY%/%SUB%/%%F ...
    scp %SSH_OPTS% -p %HOST%:%REMOTE%/%DAY%/%SUB%/%%F "data\%DAY%\%SUB%\%%F"
    if errorlevel 1 exit /b 1
  )
)
exit /b 0

:sync_collector
if exist "data\collector-poly.log" exit /b 0
echo Scarico collector.log ...
scp %SSH_OPTS% -p %HOST%:%REMOTE%/collector.log data\collector-poly.log
if errorlevel 1 exit /b 1
exit /b 0

:err
echo ERRORE - codice %ERRORLEVEL%
pause
exit /b 1
