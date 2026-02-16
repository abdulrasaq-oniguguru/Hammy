# Celery Auto-Start Setup Guide

## Overview
This guide sets up Celery to automatically start with Windows and run background tasks:
- ✅ **Database Backup**: Daily at 11:00 AM
- ✅ **PythonAnywhere Sync**: Every 30 minutes

Both tasks run independently - if backup fails, sync continues!

---

## Prerequisites

### 1. Install Redis (Required for Celery)

**Download and Install:**
1. Download Redis for Windows: https://github.com/microsoftarchive/redis/releases
2. Get: `Redis-x64-3.0.504.msi`
3. Install to default location: `C:\Program Files\Redis`
4. During install, check: ✅ "Add Redis to PATH"

**OR use Memurai (Redis alternative for Windows):**
1. Download from: https://www.memurai.com/get-memurai
2. Install and start the service

### 2. Verify Redis is Running

Open Command Prompt and run:
```batch
redis-cli ping
```

Should return: `PONG`

If not, start Redis:
```batch
redis-server
```

---

## Method 1: Windows Task Scheduler (RECOMMENDED)

### Step 1: Create VBS Launcher (Hidden Window)

Create a new file: `C:\III\start_celery_hidden.vbs`

```vbscript
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "C:\III\start_celery.bat", 0, False
Set WshShell = Nothing
```

This runs Celery in the background without showing a window.

### Step 2: Add to Task Scheduler

1. **Press** `Win + R`
2. **Type**: `taskschd.msc` and press Enter
3. **Click**: "Create Basic Task..." (right panel)

**Task Name**: `Celery Background Tasks`
**Description**: `Runs database backup and PythonAnywhere sync automatically`

**Trigger**: `When the computer starts`

**Action**: `Start a program`
   - **Program**: `C:\III\start_celery_hidden.vbs`
   - **Start in**: `C:\III`

**Finish**: Check ✅ "Open Properties dialog when I click Finish"

### Step 3: Configure Advanced Settings

In the Properties dialog:

**General Tab:**
- ✅ Run whether user is logged on or not
- ✅ Run with highest privileges
- Configure for: `Windows 10`

**Triggers Tab:**
- Click "Edit"
- ✅ Delay task for: `1 minute` (gives Windows time to start)
- ✅ Enabled

**Conditions Tab:**
- ❌ Uncheck: "Start the task only if the computer is on AC power"
- ❌ Uncheck: "Stop if the computer switches to battery power"

**Settings Tab:**
- ✅ Allow task to be run on demand
- ✅ Run task as soon as possible after a scheduled start is missed
- ❌ Uncheck: "Stop the task if it runs longer than"

**Click OK** and enter your Windows password if prompted.

### Step 4: Test the Task

1. In Task Scheduler, find "Celery Background Tasks"
2. Right-click → **Run**
3. Check if it's running:
   ```batch
   tasklist | findstr celery
   ```
   Should show: `celery.exe`

---

## Method 2: Windows Startup Folder (Visible Window)

If you prefer to see Celery running:

1. **Press** `Win + R`
2. **Type**: `shell:startup` and press Enter
3. **Create shortcut** to `C:\III\start_celery.bat`
4. **Restart** computer

Celery will start with a visible window on login.

---

## Method 3: Windows Service (Advanced)

For running as a Windows Service (even when not logged in):

### Install NSSM (Non-Sucking Service Manager)

1. Download from: https://nssm.cc/download
2. Extract `nssm.exe` to `C:\III\`

### Create Service

Open Command Prompt **as Administrator**:

```batch
cd C:\III
nssm install CeleryService "C:\III\.venv\Scripts\celery.exe" "-A mystore worker -l info --pool=solo -B"
nssm set CeleryService AppDirectory "C:\III\mystore"
nssm set CeleryService DisplayName "Celery Background Tasks"
nssm set CeleryService Description "Runs database backup and PythonAnywhere sync"
nssm set CeleryService Start SERVICE_AUTO_START
nssm start CeleryService
```

### Manage Service

```batch
# Check status
nssm status CeleryService

# Stop service
nssm stop CeleryService

# Start service
nssm start CeleryService

# Remove service
nssm remove CeleryService confirm
```

---

## Verify Celery is Running

### Check Process
```batch
tasklist | findstr celery
```

Should show: `celery.exe` running

### Check Logs

**Celery creates logs in:**
`C:\III\mystore\celery.log`

**View last 20 lines:**
```batch
powershell -command "Get-Content C:\III\mystore\celery.log -Tail 20"
```

### Check Task Execution

**In Django shell:**
```batch
cd C:\III\mystore
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult

# Check scheduled tasks
for task in PeriodicTask.objects.all():
    print(f"{task.name}: {task.enabled} - {task.last_run_at}")

# Check recent task results
for result in TaskResult.objects.order_by('-date_done')[:5]:
    print(f"{result.task_name}: {result.status} - {result.date_done}")
```

---

## Task Schedule Configuration

Both tasks are configured in: `C:\III\mystore\mystore\settings.py`

### Current Schedule:

```python
CELERY_BEAT_SCHEDULE = {
    # Database backup - Daily at 11:00 AM
    'run-daily-backup': {
        'task': 'store.tasks.run_daily_backup_task',
        'schedule': crontab(hour=11, minute=0),
        'options': {'expires': 7200}
    },

    # PythonAnywhere sync - Every 30 minutes
    'sync-to-pythonanywhere-every-30-minutes': {
        'task': 'store.tasks.sync_to_pythonanywhere_task',
        'schedule': crontab(minute='*/30'),
        'options': {'expires': 1800}
    },
}
```

### Task Independence

✅ **Tasks run independently**:
- If backup fails (flash drive not found) → Sync continues ✅
- If sync fails (no internet) → Backup continues ✅
- Each task has its own error handling
- Failures are logged but don't stop other tasks

---

## Troubleshooting

### Celery Won't Start

**Check Redis:**
```batch
redis-cli ping
```

If no response:
```batch
redis-server
```

**Check Virtual Environment:**
```batch
"C:\III\.venv\Scripts\python.exe" --version
```

**Check Celery Installation:**
```batch
"C:\III\.venv\Scripts\celery.exe" --version
```

### Tasks Not Running

**Check Beat Scheduler:**
```batch
cd C:\III\mystore
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask
print(PeriodicTask.objects.all())
```

**Reset Beat Schedule:**
```batch
cd C:\III\mystore
python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask
PeriodicTask.objects.all().delete()
```

Then restart Celery - tasks will be recreated from settings.

### View Real-Time Logs

**Start Celery in foreground (for debugging):**
```batch
cd C:\III\mystore
"C:\III\.venv\Scripts\celery.exe" -A mystore worker -l debug --pool=solo -B
```

This shows all task execution in real-time.

---

## Recommended Setup

**For automatic startup with best reliability:**

1. ✅ Use **Method 1** (Task Scheduler with VBS)
2. ✅ Set Redis to start automatically:
   - `Win + R` → `services.msc`
   - Find "Redis" service
   - Right-click → Properties
   - Startup type: **Automatic**
3. ✅ Test by restarting computer
4. ✅ Check logs after 30 minutes to verify sync ran

---

## Summary

After setup, your system will:
- ✅ Start Celery automatically on boot
- ✅ Run PythonAnywhere sync every 30 minutes
- ✅ Run database backup daily at 11:00 AM
- ✅ Continue working even if one task fails
- ✅ Log all operations for monitoring

**Next Steps:**
1. Choose setup method (Task Scheduler recommended)
2. Test the setup
3. Monitor logs for first few syncs
4. Verify data is syncing to PythonAnywhere

---

## Quick Commands Reference

```batch
# Start Celery manually
C:\III\start_celery.bat

# Check if running
tasklist | findstr celery

# Stop Celery (if started manually)
# Press Ctrl+C in the Celery window

# View logs
type C:\III\mystore\celery.log

# Test sync manually
"C:\III\.venv\Scripts\python.exe" C:\III\sync_to_pythonanywhere_robust.py --incremental
```
