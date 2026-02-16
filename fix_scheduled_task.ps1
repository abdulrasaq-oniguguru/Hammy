# Remove old task
Unregister-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -Confirm:$false -ErrorAction SilentlyContinue

# Create new task with proper settings
$action = New-ScheduledTaskAction -Execute "C:\III\sync_incremental_30min.bat"

# Create trigger that runs every 30 minutes indefinitely
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date
$trigger.Repetition = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 30)  | Select-Object -ExpandProperty Repetition
$trigger.Repetition.Duration = "" # Run indefinitely

# Alternative: use a simpler approach with daily trigger + repetition
$trigger = New-ScheduledTaskTrigger -Daily -At "12:00AM"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::FromDays(1))).Repetition

# Register the task
Register-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -Action $action -Trigger $trigger -Description "Syncs OEM data incrementally every 30 minutes"

Write-Host "Task recreated successfully!"
Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"
