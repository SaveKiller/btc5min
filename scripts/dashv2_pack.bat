@echo off
cd /d "%~dp0\.."
if not exist dist mkdir dist
set OUT=dist\btc5min-dashv2-offline.zip
echo Packaging dashV2 app bundle (zip LZMA-9, senza round in data/) to %OUT%
python scripts\dashv2_pack.py --output %OUT% %*
echo.
echo Done. Send %OUT% to the target PC.
pause
