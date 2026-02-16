# Check Task Scheduler for active tasks
# This script verifies VBScript tasks are enabled and shows their status

Write-Host "=== Checking Task Scheduler Status ===" -ForegroundColor Cyan
Write-Host ""

# Get all tasks from Task Scheduler
$tasks = Get-ScheduledTask | Where-Object {
    $_.Actions.Execute -like "*.vbs" -or
    $_.Actions.Arguments -like "*.vbs" -or
    $_.TaskName -like "*strall*"
}

if ($tasks.Count -eq 0) {
    Write-Host "No VBScript tasks found in Task Scheduler" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Searching for ALL tasks with startup triggers..." -ForegroundColor Yellow
    $tasks = Get-ScheduledTask | Where-Object {
        $_.Triggers.CimClass.CimClassName -like "*Boot*" -or
        $_.Triggers.CimClass.CimClassName -like "*Logon*"
    }
}

if ($tasks.Count -eq 0) {
    Write-Host "No startup tasks found!" -ForegroundColor Red
    exit
}

foreach ($task in $tasks) {
    Write-Host "Task Name: $($task.TaskName)" -ForegroundColor Green
    Write-Host "  Path: $($task.TaskPath)"

    # Check if enabled
    if ($task.State -eq "Ready") {
        Write-Host "  Status: ACTIVE [OK]" -ForegroundColor Green
    } elseif ($task.State -eq "Disabled") {
        Write-Host "  Status: DISABLED [!!]" -ForegroundColor Red
    } else {
        Write-Host "  Status: $($task.State)" -ForegroundColor Yellow
    }

    # Show trigger info
    foreach ($trigger in $task.Triggers) {
        $triggerType = $trigger.CimClass.CimClassName -replace "MSFT_TaskTrigger", ""
        Write-Host "  Trigger: $triggerType"
    }

    # Show action
    foreach ($action in $task.Actions) {
        Write-Host "  Execute: $($action.Execute) $($action.Arguments)"
    }

    # Get last run info
    $taskInfo = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath -ErrorAction SilentlyContinue
    if ($taskInfo) {
        Write-Host "  Last Run: $($taskInfo.LastRunTime)"
        if ($taskInfo.LastTaskResult -eq 0) {
            Write-Host "  Last Result: $($taskInfo.LastTaskResult) (Success)" -ForegroundColor Green
        } else {
            Write-Host "  Last Result: $($taskInfo.LastTaskResult) (Failed)" -ForegroundColor Red
        }
        Write-Host "  Next Run: $($taskInfo.NextRunTime)"
    }

    Write-Host ""
}

Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total tasks found: $($tasks.Count)"
$activeCount = ($tasks | Where-Object { $_.State -eq "Ready" }).Count
$disabledCount = ($tasks | Where-Object { $_.State -eq "Disabled" }).Count
Write-Host "Active tasks: $activeCount" -ForegroundColor Green
if ($disabledCount -gt 0) {
    Write-Host "Disabled tasks: $disabledCount" -ForegroundColor Red
} else {
    Write-Host "Disabled tasks: $disabledCount" -ForegroundColor Gray
}
