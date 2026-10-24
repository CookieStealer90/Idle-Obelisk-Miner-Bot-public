@echo off
setlocal
cd /d "%~dp0"
title Bot - Install Python Environment
call :RUN --install
if errorlevel 1 (
    echo Installation failed. Review the error above.
    pause
    exit /b 1
)
echo Installation complete. StartWebUI uses this project's .venv.
pause
exit /b 0

:RUN
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\python_environment.py %*
    exit /b
)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 tools\python_environment.py %*
    exit /b
)
python tools\python_environment.py %*
exit /b %errorlevel%
