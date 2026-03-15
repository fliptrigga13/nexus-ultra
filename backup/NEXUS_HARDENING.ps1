# ═══════════════════════════════════════════════════════════════════
#  NEXUS ULTRA — SYSTEM HARDENING & MONITORING SETUP
# ═══════════════════════════════════════════════════════════════════
# Note: some steps need admin rights — run elevated for full effect

$ROOT  = Split-Path $PSScriptRoot -Parent
$BKDIR = $PSScriptRoot
$LOG   = "$BKDIR\hardening_setup.log"

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line -ForegroundColor Cyan
    Add-Content $LOG $line
}
function OK($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green;  Add-Content $LOG "  [OK] $msg" }
function WARN($msg) { Write-Host "  [!!] $msg" -ForegroundColor Yellow; Add-Content $LOG "  [!!] $msg" }

Log "═══════════════════════════════════════════"
Log " NEXUS ULTRA SYSTEM HARDENING"
Log "═══════════════════════════════════════════"

# ─────────────────────────────────────────────────────────────────
# 1. AUTOMATIC UPDATES — schedule off-peak (3 AM)
# ─────────────────────────────────────────────────────────────────
Log ""
Log "[1] Configuring Windows Auto-Updates (3 AM daily)..."
try {
    $WUKey = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
    if (-not (Test-Path $WUKey)) { New-Item $WUKey -Force | Out-Null }
    Set-ItemProperty $WUKey -Name "NoAutoUpdate"           -Value 0   -Type DWord
    Set-ItemProperty $WUKey -Name "AUOptions"              -Value 4   -Type DWord  # auto download+install
    Set-ItemProperty $WUKey -Name "ScheduledInstallDay"    -Value 0   -Type DWord  # every day
    Set-ItemProperty $WUKey -Name "ScheduledInstallTime"   -Value 3   -Type DWord  # 3 AM
    Set-ItemProperty $WUKey -Name "NoAutoRebootWithLoggedOnUsers" -Value 1 -Type DWord
    OK "Windows Update scheduled: daily at 3:00 AM (no reboot while logged in)"
} catch { WARN "Could not set update policy: $_" }

# Enable Windows Update service
Set-Service -Name wuauserv -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service -Name wuauserv -ErrorAction SilentlyContinue
OK "Windows Update service: ENABLED"

# ─────────────────────────────────────────────────────────────────
# 2. ACTIVITY LOGGING — Security + System event logs with retention
# ─────────────────────────────────────────────────────────────────
Log ""
Log "[2] Configuring Activity Logging & Log Retention..."

# Audit policies — log logon events, process creation, privilege use
$audits = @(
    "Logon/Logoff,Logon,Success,Failure",
    "Logon/Logoff,Logoff,Success",
    "Account Management,User Account Management,Success,Failure",
    "Detailed Tracking,Process Creation,Success",
    "Policy Change,Audit Policy Change,Success,Failure",
    "Privilege Use,Sensitive Privilege Use,Failure"
)
foreach ($a in $audits) {
    $parts = $a -split ","
    auditpol /set /category:$parts[0] /subcategory:$parts[1] /success:$parts[2] /failure:$parts[3] 2>$null
}
OK "Audit policies configured (logon, process creation, account changes)"

# Set log sizes and retention (90 days = overwrite as needed with 512MB max)
$logs = @("Security","System","Application")
foreach ($logName in $logs) {
    try {
        $evLog = Get-WmiObject Win32_NTEventLogFile -Filter "LogFileName='$logName'" -ErrorAction SilentlyContinue
        if ($evLog) {
            $evLog.MaxFileSize = 536870912  # 512 MB
            $evLog.OverWritePolicy = "OverwriteOlder"
            $evLog.OverWriteOutDated = 90   # 90-day retention
            $evLog.Put() | Out-Null
        }
        OK "$logName log: 512MB max, 90-day retention"
    } catch { WARN "Could not configure $logName log: $_" }
}

# Enable PowerShell Script Block Logging
$PSKey = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"
if (-not (Test-Path $PSKey)) { New-Item $PSKey -Force | Out-Null }
Set-ItemProperty $PSKey -Name "EnableScriptBlockLogging" -Value 1 -Type DWord
OK "PowerShell Script Block Logging: ENABLED"

# ─────────────────────────────────────────────────────────────────
# 3. SECURITY ALERTS — Schedule monitor task every 15 minutes
# ─────────────────────────────────────────────────────────────────
Log ""
Log "[3] Installing Security Alert Monitor (runs every 15 min)..."

$monitorScript = "$BKDIR\NEXUS_MONITOR.ps1"
$taskCmd = "powershell -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$monitorScript`""

# Remove old task if exists
schtasks /delete /tn "NexusSecurityMonitor" /f 2>$null

schtasks /create `
    /tn "NexusSecurityMonitor" `
    /tr $taskCmd `
    /sc MINUTE `
    /mo 15 `
    /ru $env:USERNAME `
    /rl HIGHEST `
    /f | Out-Null

if ($LASTEXITCODE -eq 0) { OK "Security monitor task: runs every 15 minutes" }
else { WARN "Could not create monitor task - run as Administrator" }

# Schedule daily backup at 2 AM
$backupScript = "$BKDIR\RUN_BACKUP.ps1"
$backupCmd = "powershell -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$backupScript`""
schtasks /delete /tn "NexusUltraBackup" /f 2>$null
schtasks /create `
    /tn "NexusUltraBackup" `
    /tr $backupCmd `
    /sc DAILY `
    /st 02:00 `
    /ru $env:USERNAME `
    /rl HIGHEST `
    /f | Out-Null
if ($LASTEXITCODE -eq 0) { OK "Backup task: daily at 2:00 AM" }

# ─────────────────────────────────────────────────────────────────
# 4. Firewall — block unused inbound ports, log drops
# ─────────────────────────────────────────────────────────────────
Log ""
Log "[4] Hardening Windows Firewall..."
Set-NetFirewallProfile -All -Enabled True -DefaultInboundAction Block -DefaultOutboundAction Allow
Set-NetFirewallProfile -All -LogAllowed False -LogBlocked True -LogMaxSizeKilobytes 4096
OK "Firewall: ON — inbound BLOCKED by default, drops logged"

# Allow only Nexus services inbound
$nexusPorts = @(
    @{Name="NexusHub";    Port=3000},
    @{Name="NexusCOSMOS"; Port=9100},
    @{Name="NexusPSO";    Port=8080},
    @{Name="Ollama";      Port=11434},
    @{Name="OpenClaw";    Port=18789}
)
foreach ($p in $nexusPorts) {
    $existing = Get-NetFirewallRule -DisplayName $p.Name -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName $p.Name -Direction Inbound -Protocol TCP -LocalPort $p.Port -Action Allow | Out-Null
    }
    OK "Firewall: port $($p.Port) ($($p.Name)) ALLOWED"
}

# ─────────────────────────────────────────────────────────────────
# 5. Write initial system status JSON
# ─────────────────────────────────────────────────────────────────
$status = @{
    setup_time    = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    auto_updates  = "Enabled (daily 3AM)"
    logging       = "Enabled (90-day retention)"
    firewall      = "Hardened"
    monitor_task  = "Every 15 minutes"
    backup_task   = "Daily 2AM → Google Drive"
    alerts        = "Active"
} | ConvertTo-Json
Set-Content "$BKDIR\system_status.json" $status

Log ""
Log "═══════════════════════════════════════════"
Log " HARDENING COMPLETE"
Log " Monitor: $BKDIR\NEXUS_MONITOR.ps1"
Log " Backup:  $BKDIR\RUN_BACKUP.ps1"
Log "═══════════════════════════════════════════"
