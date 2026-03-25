# NEXUS Profit Autopilot — Task Scheduler Registration (run as Admin)
# Right-click this file → Run with PowerShell as Administrator

$TaskName    = "NEXUS-ProfitAutopilot"
$CmdExe      = (Get-Command cmd.exe).Source
$RunnerBat   = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\RUN_DAILY_PROFIT_OPERATIONS.bat"
$WorkDir     = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

Write-Host "`n NEXUS PROFIT AUTOPILOT SETUP" -ForegroundColor Cyan
Write-Host " Runner Script: $RunnerBat" -ForegroundColor Gray

# Remove old task if exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Execute hidden to prevent popups interrupting
$Argument = "/c `"$RunnerBat`""
$Action   = New-ScheduledTaskAction -Execute $CmdExe -Argument $Argument -WorkingDirectory $WorkDir

# Daily trigger at 9:00 AM
$Trigger  = New-ScheduledTaskTrigger -Daily -At "9:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action `
        -Trigger $Trigger -Settings $Settings -RunLevel Highest -Force
        
    Write-Host "`n [SUCCESS] SCHEDULED TASK REGISTERED:" -ForegroundColor Green
    Write-Host "   Name:    $TaskName" -ForegroundColor Green
    Write-Host "   Runs:    Daily at 9:00 AM" -ForegroundColor Green
    Write-Host "   Action:  Feeds the swarm and runs the SEO Agent automatically." -ForegroundColor Gray
} catch {
    Write-Host "`n [ERROR] Could not auto-register. Please run this script as Administrator." -ForegroundColor Red
}
