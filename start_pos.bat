@echo off
REM ============================================================
REM  Zaviyar POS - Windows launcher
REM  - Use from Task Scheduler ("At startup") or double-click.
REM  - Path is resolved from this .bat file (%~dp0), so the
REM    folder can live anywhere on the machine.
REM ============================================================

setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Python venv not found at "%~dp0venv".
    echo Create it first:
    echo     python -m venv venv
    echo     venv\Scripts\activate
    echo     pip install -r requirements.txt
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"

if not exist "logs" mkdir "logs"

set FLASK_ENV=production

REM Append stdout + stderr to logs\startup.log so Task Scheduler runs stay debuggable.
python serve_windows.py >> "logs\startup.log" 2>&1

REM If we got here, the server exited. Keep window open when double-clicked.
echo.
echo Server exited. See logs\startup.log for details.
pause
