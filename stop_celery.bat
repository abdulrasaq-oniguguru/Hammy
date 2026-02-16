@echo off
COLOR 0E
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                 STOPPING CELERY WORKER...                      ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo Stopping: %date% %time%
echo.

REM Kill celery processes
echo Searching for Celery processes...
taskkill /F /IM celery.exe 2>nul

if %errorlevel% equ 0 (
    COLOR 0A
    echo.
    echo ✅ Celery worker stopped successfully
) else (
    COLOR 0C
    echo.
    echo ⚠️  No Celery processes found running
)

echo.
pause
