# ═══════════════════════════════════════════════════════════════════
#  NEXUS ULTRA — Security Monitor (runs every 15 min via Task Scheduler)
#  Checks: failed logins, new processes, disk space, service health
#  Writes: monitor_status.json (readable by Nexus Hub dashboard)
#  Alerts: Windows toast notifications for critical events
# ═══════════════════════════════════════════════════════════════════

$BKDIR      = $PSScriptRoot
$STATUS_FILE = "$BKDIR\monitor_status.json"
$ALERT_LOG   = "$BKDIR\backup_logs\alerts_$(Get-Date -Format 'yyyy-MM').log"
$THRESHOLD_DISK_GB = 50       # warn if free disk < 50GB
$FAILED_LOGIN_LIMIT = 3       # alert if >3 failed logins in last 15 min
$CHECK_WINDOW_MIN   = 15      # look back 15 minutes

New-Item -ItemType Directory -Force -Path "$BKDIR\backup_logs" | Out-Null

function Write-NexusAlert($level, $msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$level] $msg"
    Add-Content $ALERT_LOG $line
    # Windows toast notification for CRITICAL/WARN
    if ($level -in @("CRITICAL","WARN")) {
        $title = "NEXUS ULTRA — $level"
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
        $xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
        $xml.LoadXml("<toast><visual><binding template='ToastText02'><text id='1'>$title</text><text id='2'>$msg</text></binding></visual></toast>")
        $notif = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Nexus Ultra").Show($notif)
    }
}

$alerts   = @()
$warnings = @()
$info     = @()
$since    = (Get-Date).AddMinutes(-$CHECK_WINDOW_MIN)

# ─────────────────────────────────────────────────────────────────
# 1. FAILED LOGIN ATTEMPTS (Event ID 4625)
# ─────────────────────────────────────────────────────────────────
try {
    $failedLogins = Get-WinEvent -FilterHashtable @{
        LogName   = 'Security'
        Id        = 4625
        StartTime = $since
    } -ErrorAction SilentlyContinue

    $count = ($failedLogins | Measure-Object).Count
    if ($count -ge $FAILED_LOGIN_LIMIT) {
        $msg = "$count failed login attempts in last ${CHECK_WINDOW_MIN}min"
        $alerts += $msg
        Write-NexusAlert "CRITICAL" $msg
    } elseif ($count -gt 0) {
        $warnings += "$count failed login attempt(s)"
    }
    $info += "Failed logins (${CHECK_WINDOW_MIN}min): $count"
} catch {
    $info += "Failed login check: insufficient permissions (run as Admin for full audit)"
}

# ─────────────────────────────────────────────────────────────────
# 2. NEW PROCESSES CREATED (Event ID 4688 — Suspicious Executables)
# ─────────────────────────────────────────────────────────────────
$suspiciousNames = @('nc.exe','ncat.exe','mimikatz','psexec','wce.exe','ftp.exe','tftp.exe','certutil','powersploit')
try {
    $procEvents = Get-WinEvent -FilterHashtable @{
        LogName   = 'Security'
        Id        = 4688
        StartTime = $since
    } -ErrorAction SilentlyContinue

    foreach ($evt in $procEvents) {
        $procName = ($evt.Properties[5].Value -split '\\')[-1].ToLower()
        if ($suspiciousNames -contains $procName) {
            $msg = "Suspicious process detected: $procName"
            $alerts += $msg
            Write-NexusAlert "CRITICAL" $msg
        }
    }
    $info += "New processes (${CHECK_WINDOW_MIN}min): $(($procEvents|Measure-Object).Count)"
} catch {
    $info += "Process audit: skipped (run as Admin)"
}

# ─────────────────────────────────────────────────────────────────
# 3. DISK SPACE CHECK
# ─────────────────────────────────────────────────────────────────
$drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -gt 0 }
$diskStatus = @()
foreach ($d in $drives) {
    $freeGB  = [math]::Round($d.Free  / 1GB, 1)
    $totalGB = [math]::Round(($d.Free + $d.Used) / 1GB, 1)
    $usedPct = [math]::Round($d.Used / ($d.Free + $d.Used) * 100, 0)
    $diskStatus += "$($d.Name): ${freeGB}GB free / ${totalGB}GB (${usedPct}% used)"
    if ($freeGB -lt $THRESHOLD_DISK_GB) {
        $msg = "LOW DISK: Drive $($d.Name) only ${freeGB}GB free"
        $warnings += $msg
        Write-NexusAlert "WARN" $msg
    }
}

# ─────────────────────────────────────────────────────────────────
# 4. NEXUS SERVICE HEALTH CHECK
# ─────────────────────────────────────────────────────────────────
function PortUp($port) {
    try { $t=[System.Net.Sockets.TcpClient]::new(); $t.Connect('127.0.0.1',$port); $t.Close(); return $true }
    catch { return $false }
}

$services = @(
    @{name="NexusHub";    port=3000},
    @{name="COSMOS";      port=9100},
    @{name="Ollama";      port=11434},
    @{name="PSO Brain";   port=8080},
    @{name="OpenClaw";    port=18789}
)
$svcStatus = @{}
foreach ($svc in $services) {
    $up = PortUp $svc.port
    $svcStatus[$svc.name] = $up
    if (-not $up) { $info += "$($svc.name) (:$($svc.port)): OFFLINE" }
    else          { $info += "$($svc.name) (:$($svc.port)): OK" }
}

# ─────────────────────────────────────────────────────────────────
# 5. MEMORY PRESSURE
# ─────────────────────────────────────────────────────────────────
$os = Get-CimInstance Win32_OperatingSystem
$ramFreeGB  = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
$ramTotalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$ramUsedPct = [math]::Round(($ramTotalGB - $ramFreeGB) / $ramTotalGB * 100, 0)
if ($ramUsedPct -gt 90) {
    $warnings += "HIGH RAM: ${ramUsedPct}% used (${ramFreeGB}GB free)"
    Write-NexusAlert "WARN" "Memory pressure: ${ramUsedPct}% used"
}
$info += "RAM: ${ramUsedPct}% used (${ramFreeGB}GB free / ${ramTotalGB}GB)"

# ─────────────────────────────────────────────────────────────────
# 6. LAST BACKUP STATUS
# ─────────────────────────────────────────────────────────────────
$backupStatus = $null
if (Test-Path "$BKDIR\backup_status.json") {
    try { $backupStatus = Get-Content "$BKDIR\backup_status.json" | ConvertFrom-Json } catch {}
}

# ─────────────────────────────────────────────────────────────────
# 7. WRITE STATUS JSON (hub dashboard reads this)
# ─────────────────────────────────────────────────────────────────
$overallHealth = if ($alerts.Count -gt 0) { "CRITICAL" }
                 elseif ($warnings.Count -gt 0) { "WARNING" }
                 else { "OK" }

$status = @{
    timestamp    = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    health       = $overallHealth
    alerts       = $alerts
    warnings     = $warnings
    info         = $info
    disk         = $diskStatus
    services     = $svcStatus
    ram_used_pct = $ramUsedPct
    ram_free_gb  = $ramFreeGB
    last_backup  = if ($backupStatus) { $backupStatus.last_run } else { "Never" }
    backup_ok    = if ($backupStatus) { $backupStatus.ok } else { $false }
} | ConvertTo-Json -Depth 4

Set-Content $STATUS_FILE $status

# Log summary to alerts log if anything notable
if ($alerts.Count -gt 0 -or $warnings.Count -gt 0) {
    Log-Alert "SUMMARY" "Health=$overallHealth | Alerts=$($alerts.Count) | Warnings=$($warnings.Count)"
}
