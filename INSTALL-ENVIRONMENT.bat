@echo off
title Bot - WebUI
echo.
echo ============================================================
echo   Installing dependencies...
echo ============================================================
echo.
py -m pip install -q opencv-python pystray pillow pywin32 flask flask-socketio 2>nul
echo.
echo ============================================================
echo.
pause