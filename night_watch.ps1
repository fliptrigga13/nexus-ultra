
# ═══════════════════════════════════════════════════════════════
#  VEILPIERCER — STARLIGHT NIGHT-WATCH
#  Monitors DNS, Warms Stats, and Guards Memory while you sleep.
# ═══════════════════════════════════════════════════════════════

$DOMAIN = "veilpiercer.com"
$API = "http://127.0.0.1:3000"
$LOG = "c:\Users\fyou1\Desktop\New folder\nexus-ultra\night_watch.log"

function Log($msg) {
    $timestamp = Get-Date -Format "HH:mm:ss"
    $line = "[$timestamp] $msg"
    Write-Host $line -ForegroundColor Cyan
    $line | Out-File $LOG -Append
}

Log "STALIGHT NIGHT-WATCH INITIATED. Go get some rest, I've got the bridge."
Log "Monitoring: $DOMAIN | Protecting: $API"

$dnsFound = $false

while ($true) {
    # 1. DNS WATCHER
    if (-not $dnsFound) {
        try {
            $addr = [System.Net.Dns]::GetHostAddresses($DOMAIN)
            if ($addr) {
                Log "🚀 ALERT: $DOMAIN IS LIVE! Propagation complete."
                $dnsFound = $true
            }
        }
        catch {}
    }

    # 2. SOCIAL PROOF WARMER
    # Simulates a harmless 'System Heartbeat' to keep the live counter active
    try {
        Invoke-RestMethod "$API/status" -ErrorAction SilentlyContinue | Out-Null
        Log "Warming Stats... NEXUS is healthy."
    }
    catch {}

    # 3. MEMORY GUARDIAN
    # Restart if node exceeds 1.5GB to ensure fresh performance for morning traffic
    try {
        $proc = Get-Process node -ErrorAction Stop | Where-Object { $_.CommandLine -like "*server.cjs*" } | Select-Object -First 1
        if ($proc -and $proc.WorkingSet64 -gt 1500MB) {
            Log "RAM PRESSURE: Restarting NEXUS for optimization..."
            pm2 restart nexus-ultra | Out-Null
        }
    } catch {}

    # Wait 15 minutes before next sweep
    Start-Sleep -Seconds 900
}
