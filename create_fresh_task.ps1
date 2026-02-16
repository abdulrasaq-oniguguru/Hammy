Write-Host "Creating fresh scheduled task..." -ForegroundColor Cyan
Write-Host ""

# Get current time for start boundary
$now = Get-Date
$startTime = $now.ToString("yyyy-MM-dd'T'HH:mm:ss")
Write-Host "Start time: $startTime" -ForegroundColor Yellow

# Create action
$action = New-ScheduledTaskAction -Execute "C:\III\sync_incremental_30min.bat" -WorkingDirectory "C:\III"

# Create repetition pattern (indefinite)
$repClass = cimclass MSFT_TaskRepetitionPattern root/Microsoft/Windows/TaskScheduler
$repetition = New-CimInstance -CimClass $repClass -ClientOnly
$repetition.Interval = "PT30M"  # Every 30 minutes
$repetition.Duration = ""  # Empty = runs indefinitely
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

# Register the task
Write-Host "Registering task..." -ForegroundColor Cyan
Register-ScheduledTask `
    -TaskName "Sync OEM Data Every 30 Minutes" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Syncs OEM data every 30 minutes indefinitely" | Out-Null

Write-Host "Task created successfully!" -ForegroundColor Green
Write-Host ""

# Verify configuration
$task = Get-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"
$info = Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"

Write-Host "=== TASK CONFIGURATION ===" -ForegroundColor Cyan
Write-Host "Trigger Start: $($task.Triggers[0].StartBoundary)" -ForegroundColor Yellow
Write-Host "Repetition Interval: $($task.Triggers[0].Repetition.Interval) (every 30 minutes)" -ForegroundColor Green
$dur = $task.Triggers[0].Repetition.Duration
Write-Host "Repetition Duration: $(if([string]::IsNullOrEmpty($dur)){'Indefinitely'}else{$dur})" -ForegroundColor Green
Write-Host "Stop at Duration End: $($task.Triggers[0].Repetition.StopAtDurationEnd)"
Write-Host ""

# Start first sync now
Write-Host "Starting first sync now..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

Start-Sleep -Seconds 2

$info = Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"
Write-Host ""
Write-Host "=== STATUS ===" -ForegroundColor Cyan
Write-Host "Current Time: $((Get-Date).ToString('HH:mm:ss'))"
Write-Host "Task Status: Running" -ForegroundColor Green
Write-Host "Last Run: $($info.LastRunTime.ToString('HH:mm:ss'))"
Write-Host "Next Run: $($info.NextRunTime.ToString('HH:mm:ss'))" -ForegroundColor Yellow
Write-Host ""
Write-Host "Task will now run every 30 minutes indefinitely!" -ForegroundColor Green
