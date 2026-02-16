# Stop and delete existing task
Stop-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "Creating new task with proper 30-minute repetition..."

# Create the action
$action = New-ScheduledTaskAction -Execute "C:\III\sync_incremental_30min.bat" -WorkingDirectory "C:\III"

# Create a time trigger that starts now and repeats every 30 minutes for 10 years
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)

# Create settings
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Register the task
$task = Register-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -Action $action -Trigger $trigger -Settings $settings -Description "Syncs OEM data incrementally every 30 minutes" -Force

Write-Host "Task created successfully!"
Write-Host ""

# Verify the configuration
$taskInfo = Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"
$taskConfig = Get-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

Write-Host "Task Configuration:"
Write-Host "  Interval: $($taskConfig.Triggers[0].Repetition.Interval)"
Write-Host "  Duration: $($taskConfig.Triggers[0].Repetition.Duration)"
Write-Host "  Start: $($taskConfig.Triggers[0].StartBoundary)"
Write-Host ""

Write-Host "Starting first sync now..."
Start-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

Start-Sleep -Seconds 3
$info = Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"
Write-Host ""
Write-Host "Current Status:"
Write-Host "  Last Run: $($info.LastRunTime)"
Write-Host "  Next Run: $($info.NextRunTime)"
Write-Host "  Status: Running" -ForegroundColor Green
