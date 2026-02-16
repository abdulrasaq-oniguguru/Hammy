# Try to modify the existing task instead of recreating it
Write-Host "Modifying existing task trigger..." -ForegroundColor Cyan

try {
    # Get the existing task
    $task = Get-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

    # Stop it first
    Stop-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    # Create new trigger with current time
    $now = Get-Date
    $startTime = $now.ToString("yyyy-MM-dd'T'HH:mm:ss")
    Write-Host "New start time: $startTime"

    # Create repetition pattern
    $repClass = cimclass MSFT_TaskRepetitionPattern root/Microsoft/Windows/TaskScheduler
    $repetition = New-CimInstance -CimClass $repClass -ClientOnly
    $repetition.Interval = "PT30M"
    $repetition.Duration = ""  # Empty = indefinite
    $repetition.StopAtDurationEnd = $false

    # Create time trigger
    $trigClass = cimclass MSFT_TaskTimeTrigger root/Microsoft/Windows/TaskScheduler
    $trigger = New-CimInstance -CimClass $trigClass -ClientOnly
    $trigger.StartBoundary = $startTime
    $trigger.Enabled = $true
    $trigger.Repetition = $repetition

    # Update the task with new trigger
    Set-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes" -Trigger $trigger -ErrorAction Stop | Out-Null

    Write-Host "Trigger updated successfully!" -ForegroundColor Green

    # Start it
    Write-Host "Starting task..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

    Start-Sleep -Seconds 2

    # Verify
    $task = Get-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"
    $info = Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"

    Write-Host ""
    Write-Host "=== UPDATED CONFIGURATION ===" -ForegroundColor Green
    Write-Host "Trigger Start: $($task.Triggers[0].StartBoundary)" -ForegroundColor Yellow
    Write-Host "Repetition Interval: $($task.Triggers[0].Repetition.Interval)"
    Write-Host "Repetition Duration: $(if([string]::IsNullOrEmpty($task.Triggers[0].Repetition.Duration)){'Indefinite'}else{$task.Triggers[0].Repetition.Duration})"
    Write-Host ""
    Write-Host "Last Run: $($info.LastRunTime)"
    Write-Host "Next Run: $($info.NextRunTime)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Task is now configured to run every 30 minutes indefinitely!" -ForegroundColor Green

} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "You may need to run this as Administrator or manually update the task in Task Scheduler." -ForegroundColor Yellow
    exit 1
}
