@echo off
set PYTHONPATH=%~dp0
cd /d %~dp0dash-api
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8765
