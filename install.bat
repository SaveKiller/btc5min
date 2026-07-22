@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Installazione dashV2

echo.
echo  ============================================================
echo    INSTALLAZIONE DASHV2
echo    Dashboard replay BTC 5 minuti
echo  ============================================================
echo.

if exist "venv" if not exist ".venv" (
    echo  Trovato ambiente precedente venv: lo sposto in .venv...
    move venv .venv >nul
)

set PY=
set PY_VER=

for %%C in ("py -3.14" "py -3.13" "py -3.12" "py -3.11" "python" "py -3") do (
    if not defined PY (
        %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
        if !errorlevel! equ 0 (
            set "PY=%%~C"
            for /f "delims=" %%v in ('%%~C -c "import sys; print(sys.version.split()[0])"') do set "PY_VER=%%v"
        )
    )
)

if not defined PY (
    set REJECTED_VER=
    for %%C in ("python" "py -3" "py") do (
        if not defined REJECTED_VER (
            %%~C -c "exit" 2>nul
            if !errorlevel! equ 0 (
                for /f "delims=" %%v in ('%%~C -c "import sys; print(sys.version.split()[0])"') do set "REJECTED_VER=%%v"
            )
        )
    )
    echo  ERRORE: serve Python 3.11 o superiore.
    echo.
    if defined REJECTED_VER (
        echo  Sul PC e installato Python !REJECTED_VER! che non e sufficiente.
        echo.
    ) else (
        echo  Python non trovato su questo PC.
        echo.
    )
    echo  Scarica Python 3.12 da https://www.python.org/downloads/
    echo  Durante l installazione spunta "Add python.exe to PATH".
    echo  Poi riesegui questo file con doppio click.
    echo.
    pause
    exit /b 1
)

echo  Python !PY_VER! trovato ^(!PY!^). Versione OK.
echo.

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
    if errorlevel 1 (
        echo  Ambiente esistente creato con Python non valido: lo ricreo...
        rmdir /s /q .venv
    ) else (
        echo  Ambiente gia presente ^(cartella .venv^): aggiorno i componenti...
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo  Prima installazione: creo la cartella .venv ^(1-2 minuti^)...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo.
        echo  ERRORE: impossibile creare l ambiente Python.
        pause
        exit /b 1
    )
)

attrib -h -s .venv >nul 2>&1

echo.
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\python.exe -m pip install -r requirements-dashv2-offline.txt
if errorlevel 1 (
    echo.
    echo  ERRORE durante il download dei componenti.
    echo  Controlla la connessione internet e riprova.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    INSTALLAZIONE COMPLETATA
echo  ============================================================
echo.
echo  Python usato: !PY_VER!
echo  Ambiente installato nella cartella: .venv
echo.
echo  Cosa fare adesso:
echo.
echo  1^) Se ti hanno inviato anche i file dei round ^(cartelle con date^),
echo     copiali dentro la cartella "data" che vedi qui accanto.
echo     Se non li hai, chiedili a chi ti ha mandato il pacchetto.
echo.
echo  2^) Avvia la dashboard: doppio click su dashv2.bat
echo.
echo  3^) Si aprira una finestra nera: lasciala aperta.
echo     Nel browser vai su:  http://127.0.0.1:8780/
echo.
echo  4^) Per chiudere la dashboard: chiudi la finestra nera
echo     oppure premi Ctrl+C in quella finestra.
echo.
echo  --- Aggiornamenti futuri ---
echo  Nuovi round: copiali in "data" e riavvia dashv2.bat.
echo  Nuova versione del programma: estrai lo zip sopra questa cartella
echo  e riesegui install.bat ^(non serve rifare tutto da zero^).
echo.
pause
