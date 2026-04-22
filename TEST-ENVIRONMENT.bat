@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

echo ============================================
echo   BOT ENVIRONMENT CHECK
echo ============================================
echo.
echo NOTE:
echo   Missing paths are OK. This script only checks what exists. [cite: 2]
echo.

REM ============================================================
REM 1) Find working Python with OpenCV (cv2) — avoid Python 3.14
REM ============================================================
echo [1/5] Finding a working Python with OpenCV (cv2)... [cite: 3]

set "PYSEL="

for %%V in (3.13 3.12 3.11 3.10 3.9 3.8) do (
    py -%%V -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        py -%%V -c "import cv2" >nul 2>&1
        if not errorlevel 1 (
            set "PYSEL=py -%%V"
            goto :PY_FOUND [cite: 4]
        )
    )
)

REM Fallback: python.exe on PATH (reject 3.14)
python -c "import sys; exit(0)" >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; exit(0 if sys.version_info[:2]!=(3,14) else 1)" >nul 2>&1
    if not errorlevel 1 (
        python -c "import cv2" >nul 2>&1
        if not errorlevel 1 (
            set "PYSEL=python"
            goto :PY_FOUND [cite: 5]
        )
    )
)

echo [FAIL] No working Python with cv2 found. [cite: 6]
echo        Install OpenCV, e.g.:
echo          py -3.13 -m pip install opencv-python
echo          py -3.11 -m pip install opencv-python
goto :END

:PY_FOUND
echo [OK] Using: %PYSEL%
echo.

REM ============================================================
REM 2) Show OpenCV version
REM ============================================================
echo [2/5] Checking OpenCV (cv2) details... [cite: 7]
for /f "delims=" %%l in ('%PYSEL% -c "import cv2; print(\"cv2 OK\", cv2.__version__)" 2^>^&1') do echo [OK] %%l
echo.

REM ============================================================
REM 3) Check Additional Requirements (Existence only)
REM ============================================================
echo [3/5] Checking additional Python requirements...

set "REQ_ERR="

REM Flask
%PYSEL% -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] flask missing.
    set REQ_ERR=1
) else (
    echo [OK] flask found
)

REM Flask-SocketIO
%PYSEL% -c "import flask_socketio" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] flask-socketio missing.
    set REQ_ERR=1
) else (
    echo [OK] flask-socketio found
)

REM pystray
%PYSEL% -c "import pystray" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] pystray missing.
    set REQ_ERR=1
) else (
    echo [OK] pystray found
)

REM pillow (PIL)
%PYSEL% -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] pillow missing.
    set REQ_ERR=1
) else (
    echo [OK] pillow found
)

REM pywin32 (win32api)
%PYSEL% -c "import win32api" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] pywin32 missing.
    set REQ_ERR=1
) else (
    echo [OK] pywin32 found
)

if defined REQ_ERR (
    echo.
    echo [FAIL] Some requirements are missing.
    echo        Install them via:
    echo        %PYSEL% -m pip install flask flask-socketio pystray pillow pywin32
    goto :END
)
echo.

REM ============================================================
REM 4) Search for adb.exe installations (list + warn if >2)
REM ============================================================
echo [4/5] Searching for adb.exe installations... [cite: 8]

set "ADB_PATH="
set /a FOUND_COUNT=0
set "WARNED="

call :CHECK_ADB "..\adb.exe" [cite: 8]
call :CHECK_ADB "D:\Program Files\MuMuPlayerGlobal\nx_device\12.0\shell\adb.exe" [cite: 8]
call :CHECK_ADB "C:\Program Files\MuMuPlayerGlobal\nx_device\12.0\shell\adb.exe" [cite: 8]
call :CHECK_ADB "C:\Program Files\Netease\MuMuPlayerGlobal\nx_device\12.0\shell\adb.exe" [cite: 8]
call :CHECK_ADB "C:\Program Files\Netease\MuMuPlayer\nx_device\12.0\shell\adb.exe" [cite: 8]
call :CHECK_ADB "C:\Program Files\Microvirt\MEmu\adb.exe" [cite: 8]
call :CHECK_ADB "D:\Program Files\Microvirt\MEmu\adb.exe" [cite: 8]
call :CHECK_ADB "C:\Program Files\Nox\bin\adb.exe" [cite: 8]

if defined ADB_PATH (
    echo.
    echo [OK] Using adb:
    echo      %ADB_PATH%
) else (
    echo.
    echo [WARN] No adb.exe found in configured locations.
    echo        Falling back to system PATH adb. [cite: 9]
    set "ADB_PATH=adb"
)

echo.

REM ============================================================
REM 5) Check ADB device connection + hint only if NOT 127.0.0.1:*
REM ============================================================
echo [5/5] Checking ADB device connection... [cite: 10]

if /I "%ADB_PATH%"=="adb" goto :RUN_ADB_PATH
goto :RUN_ADB_FILE

:RUN_ADB_PATH
adb devices > "%TEMP%\adb_devices.txt" 2>&1
goto :AFTER_ADB

:RUN_ADB_FILE
"%ADB_PATH%" devices > "%TEMP%\adb_devices.txt" 2>&1

:AFTER_ADB
type "%TEMP%\adb_devices.txt"

set "NEED_HINT="
for /f "tokens=1" %%D in ('findstr /R /C:"device$" "%TEMP%\adb_devices.txt"') do (
    echo %%D | findstr /B "127.0.0.1:" >nul
    if errorlevel 1 set "NEED_HINT=1"
)

if defined NEED_HINT (
    echo.
    echo [INFO] Device ID is maybe NOT 127.0.0.1:PORT.
    echo        Your bot hardcodes 127.0.0.1, so you may need to [cite: 11]
    echo        update DEVICE in config/settings.py to match what "adb devices" shows.
)

del "%TEMP%\adb_devices.txt" >nul 2>&1

echo.
echo ============================================
echo   CHECK COMPLETE [cite: 12]
echo ============================================

goto :END

:CHECK_ADB
set "P=%~1"
if not exist "%P%" exit /b

echo [FOUND] %P% [cite: 13]
set /a FOUND_COUNT+=1

if not defined ADB_PATH set "ADB_PATH=%P%"

REM Warn exactly once when we detect the 3rd adb.exe (meaning >2)
if %FOUND_COUNT% NEQ 3 exit /b
if defined WARNED exit /b
echo.
echo [WARNING] More than 2 ADB installations detected (3+). [cite: 13]
echo           Double-check which adb.exe is being used.
set "WARNED=1" [cite: 14]
exit /b

:END
echo.
pause
endlocal