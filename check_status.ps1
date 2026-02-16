Start-Sleep -Seconds 5

$info = Get-ScheduledTaskInfo -TaskName "Sync OEM Data Every 30 Minutes"
$task = Get-ScheduledTask -TaskName "Sync OEM Data Every 30 Minutes"

Write-Host ""
Write-Host "=== CURRENT STATUS ===" -ForegroundColor Cyan
Write-Host "Current Time: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host ""

Write-Host "Task Execution:" -ForegroundColor Yellow
Write-Host "  Last Run: $($info.LastRunTime)"
Write-Host "  Last Result: $($info.LastTaskResult) $(if($info.LastTaskResult -eq 0){'(Success)'}elseif($info.LastTaskResult -eq 267009){'(Running)'}else{'(Error)'})"
Write-Host "  Next Run: $($info.NextRunTime)" -ForegroundColor Green
Write-Host ""

Write-Host "Task Configuration:" -ForegroundColor Yellow
Write-Host "  Trigger Start: $($task.Triggers[0].StartBoundary)"
Write-Host "  Repetition Interval: $($task.Triggers[0].Repetition.Interval) (30 minutes)"
$dur = $task.Triggers[0].Repetition.Duration
Write-Host "  Repetition Duration: $(if([string]::IsNullOrEmpty($dur)){'(Indefinite) ✓'}else{$dur})"
Write-Host "  Stop at Duration End: $($task.Triggers[0].Repetition.StopAtDurationEnd)"
Write-Host ""

# Calculate when next run SHOULD be
$lastRun = [DateTime]$info.LastRunTime
$expectedNext = $lastRun.AddMinutes(30)
Write-Host "Expected next run (Last + 30min): $($expectedNext.ToString('yyyy-MM-dd HH:mm:ss'))"

if ($expectedNext -ne $info.NextRunTime) {
    Write-Host ""
    Write-Host "WARNING: Next run time doesn't match expected!" -ForegroundColor Red
    Write-Host "This may correct itself after the current run completes." -ForegroundColor Yellow
}
