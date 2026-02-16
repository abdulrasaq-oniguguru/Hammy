@echo off
REM ============================================================================
REM Celery Service Starter - Optimized for Windows Task Scheduler
REM ============================================================================
REM This script is designed to run as a scheduled task with auto-restart
REM ============================================================================

COLOR 0A
echo.
echo ════════════════════════════════════════════════════════════════
echo    CELERY SERVICE STARTING (Task Scheduler Mode)
echo ════════════════════════════════════════════════════════════════
echo.
echo Starting: %date% %time%
echo.

REM Set working directory
cd /d "C:\Users\asoniguguru\PycharmProjects\III\mystore"

REM Create logs directory if it doesn't exist
if not exist "logs" mkdir logs

REM Check if virtual environment exists
if not exist "C:\Users\asoniguguru\PycharmProjects\III\.venv\Scripts\activate" (
    echo ERROR: Virtual environment not found! >> logs\celery_service.log
    echo %date% %time% - ERROR: Virtual environment not found! >> logs\celery_service.log
    exit /b 1
)

REM Check if Redis is running (required for Celery)
echo Checking Redis connection...
"C:\Users\asoniguguru\PycharmProjects\III\.venv\Scripts\python.exe" -c "import redis; r = redis.Redis(host='localhost', port=6379); r.ping()" 2>nul
if %errorlevel% neq 0 (
    echo WARNING: Redis not detected. Waiting 30 seconds and retrying...
    echo %date% %time% - WARNING: Redis not detected, retrying... >> logs\celery_service.log
    timeout /t 30 /nobreak >nul

    REM Retry Redis check
    "C:\Users\asoniguguru\PycharmProjects\III\.venv\Scripts\python.exe" -c "import redis; r = redis.Redis(host='localhost', port=6379); r.ping()" 2>nul
    if %errorlevel% neq 0 (
        echo ERROR: Redis still not available after retry! >> logs\celery_service.log
        echo %date% %time% - ERROR: Redis not available >> logs\celery_service.log
        exit /b 1
    )
)

echo Redis connection OK
echo %date% %time% - Redis connection OK >> logs\celery_service.log

REM Activate virtual environment
call "C:\Users\asoniguguru\PycharmProjects\III\.venv\Scripts\activate"

REM Kill any existing Celery processes (cleanup)
taskkill /F /IM celery.exe 2>nul >nul

REM Wait a moment for processes to fully terminate
timeout /t 2 /nobreak >nul

echo.
echo ════════════════════════════════════════════════════════════════
echo    Starting Celery Worker + Beat
echo ════════════════════════════════════════════════════════════════
echo.

REM Start Celery Worker in a new window (persistent)
start "Celery Worker - Auto Service" /MIN cmd /k "cd /d "C:\Users\asoniguguru\PycharmProjects\III\mystore" && call "C:\Users\asoniguguru\PycharmProjects\III\.venv\Scripts\activate" && color 0A && echo ════════════════════════════════════════ && echo    CELERY WORKER (Auto-Start Service) && echo    Started: %date% %time% && echo ════════════════════════════════════════ && echo. && celery -A mystore worker --loglevel=info --pool=solo 2>&1 | tee logs\celery_worker.log"

REM Wait before starting Beat
timeout /t 3 /nobreak >nul

REM Start Celery Beat in a new window (persistent)
start "Celery Beat - Auto Service" /MIN cmd /k "cd /d "C:\Users\asoniguguru\PycharmProjects\III\mystore" && call "C:\Users\asoniguguru\PycharmProjects\III\.venv\Scripts\activate" && color 0B && echo ════════════════════════════════════════ && echo    CELERY BEAT SCHEDULER (Auto-Start) && echo    Started: %date% %time% && echo ════════════════════════════════════════ && echo. && celery -A mystore beat --loglevel=info 2>&1 | tee logs\celery_beat.log"

echo.
echo ════════════════════════════════════════════════════════════════
echo    Celery Service Started Successfully
echo ════════════════════════════════════════════════════════════════
echo.
echo %date% %time% - Celery Worker and Beat started successfully >> logs\celery_service.log
echo.
echo Two windows opened (minimized):
echo   1. Celery Worker (GREEN)
echo   2. Celery Beat (CYAN)
echo.
echo Logs are being written to:
echo   - logs\celery_worker.log
echo   - logs\celery_beat.log
echo   - logs\celery_service.log
echo.
echo Task Scheduler will restart this service if it fails.
echo.
echo Press any key to close this launcher window...
pause >nul
