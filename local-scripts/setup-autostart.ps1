# setup-autostart.ps1 - Register NEXUS FULL STACK to auto-start at Windows login
# via Task Scheduler (no admin rights required for AtLogon per-user tasks)
# Launches: Node server, Julia GPU, OpenClaw, Cosmos, Ollama, SSH

$oldTaskName = "NexusUltraServer"
$taskName = "NexusFullStack"
$stackScript = Join-Path $PSScriptRoot "start-full-stack.ps1"

# Find PowerShell 7 (pwsh) — required for start-full-stack.ps1 syntax
$pwshPath = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $pwshPath) {
    Write-Output "ERROR: pwsh (PowerShell 7) not found. Install from https://aka.ms/powershell"
    exit 1
}
if (-not $pwshPath) {
    Write-Output "ERROR: PowerShell not found."
    exit 1
}

if (-not (Test-Path $stackScript)) {
    Write-Output "ERROR: start-full-stack.ps1 not found at $stackScript"
    exit 1
}

Write-Output "=== NEXUS FULL STACK AUTO-START SETUP ==="
Write-Output "PowerShell       : $pwshPath"
Write-Output "Stack script     : $stackScript"
Write-Output ""

# Remove old node-only task if present
$existing = Get-ScheduledTask -TaskName $oldTaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $oldTaskName -Confirm:$false
    Write-Output "Removed old task : $oldTaskName (node-only)"
}

# Remove existing full-stack task if present
$existing2 = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing2) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Output "Removed old task : $taskName"
}

# Build the task — runs start-full-stack.ps1 at login
$action = New-ScheduledTaskAction `
    -Execute $pwshPath `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$stackScript`"" `
    -WorkingDirectory (Split-Path $stackScript)

$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId   $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName    $taskName `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Principal   $principal `
    -Description "NEXUS Full Stack - starts Node, Julia GPU, OpenClaw, Cosmos, Ollama, SSH at login" `
    -Force | Out-Null

# Verify
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Output "[OK] Task registered  : $taskName"
    Write-Output "     Status           : $($task.State)"
    Write-Output "     Run as           : $env:USERNAME"
    Write-Output "     Trigger          : At logon"
    Write-Output "     Auto-restarts    : 3x (1 min interval)"
    Write-Output "     Services         : Node, Julia GPU, OpenClaw, Cosmos, Ollama, SSH"
    Write-Output ""
    Write-Output "ALL services will now start automatically each time you log in."
    Write-Output "To remove: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
}
else {
    Write-Output "[FAILED] Task registration failed. Try running as Administrator."
}
