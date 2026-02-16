# Delete old task
schtasks /delete /tn "Sync OEM Data Every 30 Minutes" /f 2>$null

# Create the action
$action = New-ScheduledTaskAction -Execute "C:\III\sync_incremental_30min.bat" -WorkingDirectory "C:\III"

# Create a trigger that repeats every 30 minutes for 24 hours, and repeats daily
$trigger = New-ScheduledTaskTrigger -Daily -At "12:00AM"
$repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 59)).Repetition
$trigger.Repetition = $repetition

# Create settings
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable:$false

# Register the task
Register-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -Action $action -Trigger $trigger -Settings $settings -Description "Syncs OEM data incrementally every 30 minutes"

Write-Host "Task fixed! Running first sync now..."

# Run it immediately once
Start-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

# Show status
Start-Sleep -Seconds 2
Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes" | Format-List LastRunTime, NextRunTime, LastTaskResult, NumberOfMissedRuns
