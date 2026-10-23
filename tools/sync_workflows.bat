@echo off
cd /d "%~dp0.."
python tools\sync_workflows.py
pause
