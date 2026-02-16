@echo off
COLOR 0A
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║          COMPREHENSIVE DATA SYNC TO PYTHONANYWHERE             ║
echo ║                    Syncing ALL Data Now...                     ║
echo ╔════════════════════════════════════════════════════════════════╝
echo.
echo Started: %date% %time%
echo Target: https://asoniguguru.pythonanywhere.com
echo Method: API Push (Secure)
echo.
echo ────────────────────────────────────────────────────────────────
echo.
REM Change to the project directory (where your script is)
cd /d "C:\III"
echo Syncing ALL Data via API...
echo   → Products (all inventory)
echo   → Sales (last 90 days)
echo   → Receipts (last 90 days)
echo   → Payments (last 90 days)
echo.
REM Run the Python script using the correct Python path
"C:\III\.venv\Scripts\python.exe" sync_to_pythonanywhere.py
if %errorlevel% neq 0 (
    COLOR 0C
    echo.
    echo ❌ ERROR: Sync failed!
    echo    Check your internet connection and API credentials
    pause
    exit /b 1
)
echo.
echo ════════════════════════════════════════════════════════════════
COLOR 0B
echo.
echo           ✅ COMPREHENSIVE SYNC COMPLETED SUCCESSFULLY
echo.
echo ════════════════════════════════════════════════════════════════
echo.
echo Finished: %date% %time%
echo.
echo What was synced:
echo   ✓ All Products (inventory snapshot)
echo   ✓ Sales Data (last 90 days)
echo   ✓ Receipts (last 90 days)
echo   ✓ Payment Records (last 90 days)
echo.
echo ⚠️  Customer personal info NOT synced (by design)
echo.
echo Your reports are ready at:
echo https://asoniguguru.pythonanywhere.com/api/oem/reports/
echo.
echo ────────────────────────────────────────────────────────────────
COLOR 07
echo.
pause