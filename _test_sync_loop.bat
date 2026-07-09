@echo off
set HOST=ticksaver
set REMOTE=/opt/btc5min/data
for /f "delims=" %%D in ('ssh %HOST% "find %REMOTE% -maxdepth 1 -mindepth 1 -type d -regextype posix-extended -regex '.*/[0-9]{4}-[0-9]{2}-[0-9]{2}$' -printf '%%f\n'"') do echo %%D
