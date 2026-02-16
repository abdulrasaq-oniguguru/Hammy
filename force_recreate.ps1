# Force stop the task
Write-Host "Stopping task..." -ForegroundColor Cyan
try {
    Stop-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -ErrorAction Stop
    Write-Host "Task stopped"
} catch {
    Write-Host "Task not running or already stopped"
}

Start-Sleep -Seconds 3

# Force unregister
Write-Host "Unregistering task..." -ForegroundColor Cyan
try {
    Unregister-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -Confirm:$false -ErrorAction Stop
    Write-Host "Task unregistered"
} catch {
    Write-Host "Error unregistering: $_"
}

Start-Sleep -Seconds 3

# Verify it's gone
$exists = Get-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -ErrorAction SilentlyContinue
if ($exists) {
    Write-Host "WARNING: Task still exists! Trying alternative method..." -ForegroundColor Red
    # Use schtasks as fallback
    & schtasks /delete /tn "Sync OEM Data Every 30 Minutes" /f
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "Creating new task with current time as start..." -ForegroundColor Cyan

# Get current time for start boundary
$now = Get-Date
$startTime = $now.ToString("yyyy-MM-dd'T'HH:mm:ss")
Write-Host "Start time will be: $startTime"

# Create components
$action = New-ScheduledTaskAction -Execute "C:\III\sync_incremental_30min.bat" -WorkingDirectory "C:\III"

# Create repetition pattern
$repClass = cimclass MSFT_TaskRepetitionPattern root/Microsoft/Windows/TaskScheduler
$repetition = New-CimInstance -CimClass $repClass -ClientOnly
$repetition.Interval = "PT30M"
$repetition.Duration = ""
$repetition.StopAtDurationEnd = $false

# Create time trigger
$trigClass = cimclass MSFT_TaskTimeTrigger root/Microsoft/Windows/TaskScheduler
$trigger = New-CimInstance -CimClass $trigClass -ClientOnly
$trigger.StartBoundary = $startTime
$trigger.Enabled = $true
$trigger.Repetition = $repetition

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

# Register
try {
    Register-ScheduledTask `
        -TaskName "Sync OEM Data Every 30 Minutes" `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Syncs OEM data every 30 minutes indefinitely" `
        -ErrorAction Stop | Out-Null

    Write-Host "Task registered successfully!" -ForegroundColor Green
} catch {
    Write-Host "Error registering task: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Starting first sync..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

Start-Sleep -Seconds 2

# Verify
$task = Get-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"
$info = Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"

Write-Host ""
Write-Host "=== VERIFICATION ===" -ForegroundColor Green
Write-Host "Trigger Start: $($task.Triggers[0].StartBoundary)"
Write-Host "Repetition: $($task.Triggers[0].Repetition.Interval) / $(if([string]::IsNullOrEmpty($task.Triggers[0].Repetition.Duration)){'Indefinite'}else{$task.Triggers[0].Repetition.Duration})"
Write-Host "Last Run: $($info.LastRunTime)"
Write-Host "Next Run: $($info.NextRunTime)"
