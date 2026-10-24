@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\python_environment.py --launch %*
    exit /b
)
start "" /b pythonw tools\python_environment.py --launch %*
