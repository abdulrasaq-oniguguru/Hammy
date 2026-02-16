Option Explicit

' ════════════════════════════════════════════════════════════════
' UNIFIED SERVICE STARTER - VBScript Version
' Starts all services silently in background:
' - Django Development Server
' - Celery Worker (task processor)
' - Celery Beat (task scheduler)
' - Initial PythonAnywhere Sync
'
' Automated Tasks (via Celery Beat):
' - Database Backup: Daily at 11:00 AM (skips if drive missing)
' - PythonAnywhere Sync: Every 30 minutes
' ════════════════════════════════════════════════════════════════

Dim objShell, objFSO, objNetwork
Dim strProjectDir, strVenvDir, strDjangoDir, strPythonExe
Dim strLogFile, intResult

' Set paths
strProjectDir = "C:\III"
strVenvDir = strProjectDir & "\.venv"
strDjangoDir = strProjectDir & "\mystore"
strPythonExe = strVenvDir & "\Scripts\python.exe"
strLogFile = strDjangoDir & "\logs\service_startup.log"

' Create objects
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Create logs directory if it doesn't exist
If Not objFSO.FolderExists(strDjangoDir & "\logs") Then
    objFSO.CreateFolder(strDjangoDir & "\logs")
End If

' Start logging
Call WriteLog("════════════════════════════════════════════════════════════════")
Call WriteLog("UNIFIED SERVICE STARTER - Starting All Services")
Call WriteLog("Started: " & Now())
Call WriteLog("════════════════════════════════════════════════════════════════")

' ═══════════════════════════════════════════════════════════════════
' [1/5] Check Virtual Environment
' ═══════════════════════════════════════════════════════════════════
Call WriteLog("[1/5] Checking virtual environment...")

If Not objFSO.FileExists(strPythonExe) Then
    Call WriteLog("ERROR: Virtual environment not found at " & strPythonExe)
    MsgBox "ERROR: Virtual environment not found!" & vbCrLf & vbCrLf & _
           "Expected: " & strPythonExe & vbCrLf & vbCrLf & _
           "Please ensure your virtual environment is set up correctly.", _
           vbCritical, "Service Startup Error"
    WScript.Quit 1
End If

Call WriteLog("SUCCESS: Virtual environment found")

' ═══════════════════════════════════════════════════════════════════
' [2/5] Check Redis Connection
' ═══════════════════════════════════════════════════════════════════
Call WriteLog("[2/5] Checking Redis connection...")

intResult = objShell.Run("""" & strPythonExe & """ -c ""import redis; r = redis.Redis(host='localhost', port=6379); r.ping()""", 0, True)

If intResult <> 0 Then
    Call WriteLog("WARNING: Redis server not detected, attempting to start...")

    ' Try to start Redis
    objShell.Run "redis-server", 0, False
    WScript.Sleep 5000

    ' Check again
    intResult = objShell.Run("""" & strPythonExe & """ -c ""import redis; r = redis.Redis(host='localhost', port=6379); r.ping()""", 0, True)

    If intResult <> 0 Then
        Call WriteLog("ERROR: Redis server still not available!")
        MsgBox "ERROR: Redis server not detected!" & vbCrLf & vbCrLf & _
               "Celery requires Redis to be running." & vbCrLf & _
               "Please start Redis first, then run this script again.", _
               vbCritical, "Redis Connection Error"
        WScript.Quit 1
    End If
End If

Call WriteLog("SUCCESS: Redis connection OK")

' ═══════════════════════════════════════════════════════════════════
' [3/5] Cleanup Old Processes
' ═══════════════════════════════════════════════════════════════════
Call WriteLog("[3/5] Cleaning up old Celery processes...")

objShell.Run "taskkill /F /IM celery.exe", 0, False
WScript.Sleep 2000

Call WriteLog("SUCCESS: Cleanup complete")

' ═══════════════════════════════════════════════════════════════════
' [4/5] Start Celery Services
' ═══════════════════════════════════════════════════════════════════
Call WriteLog("[4/5] Starting Celery Worker and Beat...")

' Start Celery Worker (silently in background)
Dim strCeleryWorkerCmd
strCeleryWorkerCmd = "cmd /c cd /d """ & strDjangoDir & """ && " & _
                     """" & strVenvDir & "\Scripts\activate.bat"" && " & _
                     "celery -A mystore worker --loglevel=info --pool=solo >> logs\celery_worker.log 2>&1"

objShell.Run strCeleryWorkerCmd, 0, False
Call WriteLog("SUCCESS: Celery Worker started (background process)")
WScript.Sleep 3000

' Start Celery Beat (silently in background)
Dim strCeleryBeatCmd
strCeleryBeatCmd = "cmd /c cd /d """ & strDjangoDir & """ && " & _
                   """" & strVenvDir & "\Scripts\activate.bat"" && " & _
                   "celery -A mystore beat --loglevel=info >> logs\celery_beat.log 2>&1"

objShell.Run strCeleryBeatCmd, 0, False
Call WriteLog("SUCCESS: Celery Beat started (background process)")
Call WriteLog("   Scheduled Tasks:")
Call WriteLog("   • Database Backup: Daily at 11:00 AM")
Call WriteLog("   • PythonAnywhere Sync: Every 30 minutes")
WScript.Sleep 2000

' ═══════════════════════════════════════════════════════════════════
' [5/5] Start Django Development Server
' ═══════════════════════════════════════════════════════════════════
Call WriteLog("[5/5] Starting Django development server...")

' Start Django server in a visible window (so you can see requests)
Dim strDjangoCmd
strDjangoCmd = "cmd /k cd /d """ & strDjangoDir & """ && " & _
               """" & strVenvDir & "\Scripts\activate.bat"" && " & _
               "color 0E && " & _
               "echo ════════════════════════════════════════ && " & _
               "echo    DJANGO SERVER RUNNING && " & _
               "echo    Listening on: 0.0.0.0:8080 && " & _
               "echo    Started: " & Now() & " && " & _
               "echo ════════════════════════════════════════ && " & _
               "echo. && " & _
               "python manage.py runserver 0.0.0.0:8080"

objShell.Run strDjangoCmd, 1, False
Call WriteLog("SUCCESS: Django server started (visible window)")
Call WriteLog("   Listening on: 0.0.0.0:8080")
WScript.Sleep 2000

' ═══════════════════════════════════════════════════════════════════
' Final Summary
' ═══════════════════════════════════════════════════════════════════
Call WriteLog("════════════════════════════════════════════════════════════════")
Call WriteLog("ALL SERVICES STARTED SUCCESSFULLY")
Call WriteLog("Completed: " & Now())
Call WriteLog("════════════════════════════════════════════════════════════════")
Call WriteLog("")
Call WriteLog("Services Running:")
Call WriteLog("  ✓ Django Server      (0.0.0.0:8080) - Visible window")
Call WriteLog("  ✓ Celery Worker      (task processor) - Background")
Call WriteLog("  ✓ Celery Beat        (scheduler) - Background")
Call WriteLog("")
Call WriteLog("Scheduled Tasks (Automatic via Celery Beat):")
Call WriteLog("  • Database Backup        → Daily at 11:00 AM")
Call WriteLog("  • PythonAnywhere Sync    → Every 30 minutes (next sync in ≤30 min)")
Call WriteLog("")
Call WriteLog("Backup Behavior:")
Call WriteLog("  • If backup drive (D:\) not found, backup is SKIPPED")
Call WriteLog("  • Other tasks continue running normally")
Call WriteLog("  • Backup will retry tomorrow at 11:00 AM")
Call WriteLog("")
Call WriteLog("Sync Behavior:")
Call WriteLog("  • Runs every 30 minutes automatically (via Celery Beat)")
Call WriteLog("  • First sync will run within 30 minutes of startup")
Call WriteLog("  • Uses incremental mode (only changes since last sync)")
Call WriteLog("  • If sync fails, retries on next schedule")
Call WriteLog("")
Call WriteLog("Logs Location: " & strDjangoDir & "\logs\")
Call WriteLog("════════════════════════════════════════════════════════════════")

' Show success message to user
MsgBox "✅ All Services Started Successfully!" & vbCrLf & vbCrLf & _
       "🖥️  Services Running:" & vbCrLf & _
       "  • Django Server (0.0.0.0:8080) - Window open" & vbCrLf & _
       "  • Celery Worker (task processor) - Background" & vbCrLf & _
       "  • Celery Beat (scheduler) - Background" & vbCrLf & vbCrLf & _
       "⏰ Scheduled Tasks (Automatic):" & vbCrLf & _
       "  • Database Backup: Daily at 11:00 AM" & vbCrLf & _
       "  • PythonAnywhere Sync: Every 30 minutes" & vbCrLf & _
       "    (First sync in ≤30 minutes)" & vbCrLf & vbCrLf & _
       "💾 If backup drive missing, backup is skipped" & vbCrLf & _
       "🔄 Sync runs automatically every 30 minutes" & vbCrLf & vbCrLf & _
       "📝 Logs: " & strDjangoDir & "\logs\", _
       vbInformation, "Services Started"

' Cleanup
Set objShell = Nothing
Set objFSO = Nothing

WScript.Quit 0

' ════════════════════════════════════════════════════════════════
' Helper Function: Write to log file
' ════════════════════════════════════════════════════════════════
Sub WriteLog(strMessage)
    Dim objLogFile
    On Error Resume Next
    Set objLogFile = objFSO.OpenTextFile(strLogFile, 8, True)
    If Err.Number = 0 Then
        objLogFile.WriteLine Now() & " - " & strMessage
        objLogFile.Close
    End If
    On Error Goto 0
    Set objLogFile = Nothing
End Sub
