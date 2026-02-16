@echo off
COLOR 0A
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║              CELERY WORKER + BEAT STARTING...                  ║
echo ║        Automated Tasks: Backup + PythonAnywhere Sync          ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo Starting: %date% %time%
echo.
echo ────────────────────────────────────────────────────────────────
echo.
echo Tasks Scheduled:
echo   • Database Backup    → Daily at 11:00 AM
echo   • PythonAnywhere Sync → Every 30 minutes
echo.
echo ────────────────────────────────────────────────────────────────
echo.

REM Change to mystore directory
cd /d "C:\III\mystore"

REM Check if virtual environment exists
if not exist "C:\III\.venv\Scripts\activate" (
    COLOR 0C
    echo ❌ ERROR: Virtual environment not found!
    echo    Expected: C:\III\.venv\Scripts\activate
    pause
    exit /b 1
)

REM Check if Redis is running (required for Celery)
echo Checking Redis connection...
"C:\III\.venv\Scripts\python.exe" -c "import redis; r = redis.Redis(host='localhost', port=6379); r.ping()" 2>nul
if %errorlevel% neq 0 (
    COLOR 0E
    echo.
    echo ⚠️  WARNING: Redis server not detected!
    echo    Celery requires Redis to be running.
    echo    Please start Redis first, then run this script again.
    echo.
    pause
    exit /b 1
)

echo ✅ Redis connection OK
echo.
COLOR 0B
echo ════════════════════════════════════════════════════════════════
echo           🚀 STARTING CELERY WORKER + BEAT (2 Windows)
echo ════════════════════════════════════════════════════════════════
echo.
echo ⚠️  NOTE: On Windows, Celery Worker and Beat run in separate windows
echo.
echo    Window 1: Celery Worker (task processor)
echo    Window 2: Celery Beat (task scheduler)
echo.
echo Both windows will open now...
echo.
timeout /t 3 /nobreak >nul

REM Start Celery Worker in a new window
start "Celery Worker" cmd /k "cd /d "C:\III\mystore" && call "C:\III\.venv\Scripts\activate" && color 0A && echo ════════════════════════════════════════ && echo    CELERY WORKER RUNNING && echo ════════════════════════════════════════ && echo. && celery -A mystore worker --loglevel=info --pool=solo"

REM Wait 2 seconds before starting Beat
timeout /t 2 /nobreak >nul

REM Start Celery Beat in a new window
start "Celery Beat" cmd /k "cd /d "C:\III\mystore" && call "C:\III\.venv\Scripts\activate" && color 0B && echo ════════════════════════════════════════ && echo    CELERY BEAT SCHEDULER RUNNING && echo ════════════════════════════════════════ && echo. && celery -A mystore beat --loglevel=info"

echo.
COLOR 0A
echo ════════════════════════════════════════════════════════════════
echo ✅ CELERY STARTED SUCCESSFULLY
echo ════════════════════════════════════════════════════════════════
echo.
echo Two windows have opened:
echo   1. Celery Worker (GREEN) - Processes tasks
echo   2. Celery Beat (CYAN) - Schedules tasks
echo.
echo Keep both windows open for Celery to work.
echo Close this window now - the other windows will continue running.
echo.
echo To stop Celery: Close both windows or run stop_celery.bat
echo.
pause