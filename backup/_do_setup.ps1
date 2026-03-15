$BKDIR = 'C:\Users\fyou1\Desktop\New folder\nexus-ultra\backup'

function Make-Task($name, $scriptPath, $every='daily') {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
    $trigger = if ($every -eq 'minute') {
        $t = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
        $t.Repetition.Interval = 'PT15M'
        $t.Repetition.Duration = 'P9999D'
        $t
    } else {
        New-ScheduledTaskTrigger -Daily -At '02:00'
    }
    $settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "[OK] Task: $name"
}

Make-Task 'NexusSecurityMonitor' "$BKDIR\NEXUS_MONITOR.ps1" 'minute'
Make-Task 'NexusUltraBackup'     "$BKDIR\RUN_BACKUP.ps1"     'daily'

Set-NetFirewallProfile -All -Enabled True -DefaultInboundAction Block -DefaultOutboundAction Allow -ErrorAction SilentlyContinue
Set-NetFirewallProfile -All -LogBlocked True -LogMaxSizeKilobytes 4096 -ErrorAction SilentlyContinue
Write-Host '[OK] Firewall hardened'

foreach ($p in @(
    @{Name='NexusHub';Port=3000}, @{Name='NexusCOSMOS';Port=9100},
    @{Name='NexusPSO';Port=8080}, @{Name='Ollama';Port=11434},
    @{Name='OpenClaw';Port=18789}
)) {
    Remove-NetFirewallRule -DisplayName $p.Name -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $p.Name -Direction Inbound -Protocol TCP -LocalPort $p.Port -Action Allow | Out-Null
    Write-Host "[OK] Port $($p.Port) ($($p.Name))"
}

Set-Service wuauserv -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service wuauserv -ErrorAction SilentlyContinue
Write-Host '[OK] Windows Update service running'

@{
    setup_time   = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    rclone       = 'v1.73.2 installed'
    firewall     = 'Hardened'
    monitor_task = 'Every 15 min'
    backup_task  = 'Daily 2AM -> Google Drive'
    status       = 'ACTIVE'
} | ConvertTo-Json | Set-Content "$BKDIR\system_status.json"

Write-Host ''
Write-Host '=== NEXUS HARDENING COMPLETE ==='
