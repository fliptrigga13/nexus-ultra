# REGISTER_BRAIN_SYNC.ps1
# Registers a Windows Scheduled Task to auto-sync brain + interactions to Google Drive.
# Run once: powershell -ExecutionPolicy Bypass -File REGISTER_BRAIN_SYNC.ps1
# Schedule: Every 2 hours + on system startup

$TaskName   = "NEXUS-BrainSyncGDrive"
$ScriptPath = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\SYNC_BRAIN_TO_GDRIVE.py"
$Python     = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $Python) {
    Write-Host "ERROR: python not found in PATH" -ForegroundColor Red
    exit 1
}

# Remove if already registered
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action  = New-ScheduledTaskAction -Execute $Python -Argument "`"$ScriptPath`"" -WorkingDirectory "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
$Trigger = @(
    # Run every 2 hours
    $(New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 2) -Once -At (Get-Date)),
    # Also run at startup (in case machine rebooted)
    $(New-ScheduledTaskTrigger -AtStartup)
)
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -RunLevel Highest -Force

Write-Host ""
Write-Host "✅ NEXUS Brain Sync registered:" -ForegroundColor Green
Write-Host "   Task: $TaskName" -ForegroundColor Cyan
Write-Host "   Schedule: Every 2 hours + at startup" -ForegroundColor Cyan
Write-Host "   Destination: googledrive:Nexus-Ultra-Backup/brain-sync/" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run now: python SYNC_BRAIN_TO_GDRIVE.py" -ForegroundColor Yellow
