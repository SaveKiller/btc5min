@echo off
cd /d "%~dp0"
title BTC5MIN collector
set LOG=data\collector.log
echo Avvio collector continuo BTC 5m - Ctrl+C per fermare
echo Log: %LOG%
echo.
python -m src.main 1>>"%LOG%"
set RC=%ERRORLEVEL%
echo.
echo ===== Uscita codice %RC% %date% %time% =====>>"%LOG%"
if %RC% NEQ 0 (
    echo ERRORE - codice %RC%
    echo Ultime righe del log:
    echo.
    powershell -NoProfile -Command "Get-Content -Path '%LOG%' -Tail 40"
    echo.
    echo Log completo: %LOG%
    pause
) else (
    echo Collector terminato normalmente.
    pause
)
