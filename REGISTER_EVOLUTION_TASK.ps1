# NEXUS Evolution — Task Scheduler Registration (run as Admin)
# Right-click this file → Run with PowerShell as Administrator

$taskName    = "NEXUS-SelfEvolution"
$python      = (Get-Command python -ErrorAction SilentlyContinue).Source
if (!$python) { $python = "C:\Python314\python.exe" }
$script      = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\SELF_EVOLUTION_LOOP.py"
$workDir     = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

Write-Host "`n NEXUS SELF-EVOLUTION SCHEDULER SETUP" -ForegroundColor Cyan
Write-Host " Python: $python" -ForegroundColor Gray
Write-Host " Script: $script" -ForegroundColor Gray

# Remove old task if exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Nightly 2 AM — 8 cycles (1 hour apart = 8 hours of learning)
$action   = New-ScheduledTaskAction -Execute $python `
              -Argument "`"$script`" --cycles 8 --interval 3600" `
              -WorkingDirectory $workDir
$trigger  = New-ScheduledTaskTrigger -Daily -At "2:00AM"
$settings = New-ScheduledTaskSettingsSet `
              -ExecutionTimeLimit (New-TimeSpan -Hours 10) `
              -StartWhenAvailable `
              -DontStopOnIdleEnd

try {
    Register-ScheduledTask -TaskName $taskName -Action $action `
        -Trigger $trigger -Settings $settings -RunLevel Highest -Force
    Write-Host "`n SCHEDULED TASK REGISTERED:" -ForegroundColor Green
    Write-Host "   Name:    $taskName" -ForegroundColor Green
    Write-Host "   Runs:    Daily at 2:00 AM" -ForegroundColor Green
    Write-Host "   Cycles:  8 x 1-hour (8 hours of learning)" -ForegroundColor Green
    Write-Host "   Model:   nexus-prime:latest → evolves each cycle" -ForegroundColor Green
} catch {
    Write-Host "`n Could not auto-register (need admin). Manual setup:" -ForegroundColor Yellow
    Write-Host "   1. Open Task Scheduler" -ForegroundColor Gray
    Write-Host "   2. Create Basic Task → Daily at 2:00 AM" -ForegroundColor Gray
    Write-Host "   3. Run: $python `"$script`" --cycles 8 --interval 3600" -ForegroundColor Gray
}

Write-Host "`n Run NOW for first evolution cycle? (y/n) " -NoNewline -ForegroundColor Cyan
$ans = Read-Host
if ($ans -eq 'y') {
    Write-Host " Starting first evolution cycle..." -ForegroundColor Cyan
    & $python $script --once
}
