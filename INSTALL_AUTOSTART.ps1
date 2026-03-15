# NEXUS ULTRA — Auto-Start Installation Script
# Registers the Master Watchdog to run at logon
# Run this as Administrator

$TaskName    = "NEXUS-MasterWatchdog"
$PSExe       = (Get-Command powershell.exe).Source
$ScriptPath  = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\MASTER_WATCHDOG.ps1"
$WorkDir     = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

Write-Host "`n NEXUS AUTO-START INSTALLER" -ForegroundColor Cyan
Write-Host " Script: $ScriptPath" -ForegroundColor Gray

# Create the action
$Argument = "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Action = New-ScheduledTaskAction -Execute $PSExe `
    -Argument $Argument `
    -WorkingDirectory $WorkDir

# Create the trigger (At logon)
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Settings: Ensure it runs even on battery, and allow it to wake the laptop (optional)
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -StartWhenAvailable

# Remove old task if exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

try {
    # Register the task
    Register-ScheduledTask -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -RunLevel Highest `
        -Force
    
    Write-Host "`n [SUCCESS] NEXUS Auto-Start registered!" -ForegroundColor Green
    Write-Host " The Master Watchdog will now start automatically whenever you log in." -ForegroundColor Gray
    Write-Host " It will monitor and restart all services (Ollama, Hub, COSMOS, etc.) if they crash." -ForegroundColor Gray
    Write-Host "`n Would you like to start it NOW? (y/n) " -NoNewline -ForegroundColor Cyan
    $ans = Read-Host
    if ($ans -eq 'y') {
        Start-ScheduledTask -TaskName $TaskName
        Write-Host " Started!" -ForegroundColor Green
    }
} catch {
    Write-Host "`n [ERROR] Failed to register task. Please run as Administrator." -ForegroundColor Red
    Write-Host " $($_.Exception.Message)" -ForegroundColor Red
}
