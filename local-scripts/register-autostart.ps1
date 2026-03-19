# NEXUS AUTO-START — Task Scheduler Registration (run as Admin)
# Registers start-all.ps1 to run on Windows Login

$taskName = "NEXUS-Ultra-AutoStart"
$script = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\local-scripts\start-all.ps1"
$workDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

Write-Host "`n NEXUS AUTO-START SCHEDULER SETUP" -ForegroundColor Cyan
Write-Host " Script: $script" -ForegroundColor Gray

# Remove old task if exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $workDir

# Run when user logs on
$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

try {
    # Register the task to run with Highest privileges (Admin)
    Register-ScheduledTask -TaskName $taskName -Action $action `
        -Trigger $trigger -Settings $settings -RunLevel Highest -Force
    Write-Host "`n SCHEDULED TASK REGISTERED:" -ForegroundColor Green
    Write-Host "   Name:    $taskName" -ForegroundColor Green
    Write-Host "   Runs:    At logon" -ForegroundColor Green
} catch {
    Write-Host "`n Could not auto-register (need admin). Manual setup:" -ForegroundColor Yellow
    Write-Host "   1. Open Task Scheduler" -ForegroundColor Gray
    Write-Host "   2. Create Task → Trigger: At Logon" -ForegroundColor Gray
    Write-Host "   3. Action: powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" -ForegroundColor Gray
}

Write-Host "`n Run NOW to verify? (y/n) " -NoNewline -ForegroundColor Cyan
# In an agentic context, we might not want to wait for user input if we can just finish the task.
# But I'll leave the script as a utility for the user.
