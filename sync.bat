@echo off
cd /d "%~dp0"
title BTC5MIN sync poly
set HOST=ticksaver
set REMOTE=/opt/btc5min/data

echo Sync %HOST%:%REMOTE% -^> data\yyyy-mm-dd\bin e data\yyyy-mm-dd\txt
echo.

echo Scarico cartelle giorno ...
scp -r %HOST%:%REMOTE%/????-??-?? data\
if errorlevel 1 goto :err

echo Scarico collector.log ...
scp %HOST%:%REMOTE%/collector.log data\collector-poly.log
if errorlevel 1 goto :err

echo.
echo Fatto.
pause
exit /b 0

:err
echo ERRORE - codice %ERRORLEVEL%
pause
exit /b 1
