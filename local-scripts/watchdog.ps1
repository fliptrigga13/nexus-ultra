# watchdog.ps1 - Auto-restarts dead NEXUS services every 30 seconds
# Run this in a visible PowerShell window and leave it open

$nexusDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
$cosmosDir = "C:\Users\fyou1\.gemini\antigravity\scratch\aistudio-agent"
$ocDir = "C:\Users\fyou1\.openclaw"

function IsListening($port) {
    $r = netstat -ano | Select-String ":$port " | Select-String "LISTENING"
    return ($null -ne $r)
}

Write-Host "NEXUS WATCHDOG ACTIVE - Ctrl+C to stop" -ForegroundColor Cyan
Write-Host "Checking services every 30 seconds..." -ForegroundColor Cyan
Write-Host ""

while ($true) {
    $ts = Get-Date -Format "HH:mm:ss"

    # NEXUS ULTRA :3000
    if (-not (IsListening 3000)) {
        Write-Host "[$ts] NEXUS ULTRA down - restarting..." -ForegroundColor Yellow
        Start-Process "node" -ArgumentList "server.cjs" -WorkingDirectory $nexusDir -WindowStyle Hidden
    }
    else {
        Write-Host "[$ts] :3000 OK" -ForegroundColor Green
    }

    # COSMOS :9100
    if (-not (IsListening 9100)) {
        Write-Host "[$ts] COSMOS down - restarting..." -ForegroundColor Yellow
        Start-Process "python" -ArgumentList "cosmos_kernel.py" -WorkingDirectory $cosmosDir -WindowStyle Hidden
    }
    else {
        Write-Host "[$ts] :9100 OK" -ForegroundColor Green
    }

    # OpenClaw :18789
    if (-not (IsListening 18789)) {
        Write-Host "[$ts] OpenClaw down - restarting..." -ForegroundColor Yellow
        Start-Process "cmd.exe" -ArgumentList "/c `"$ocDir\gateway.cmd`"" -WorkingDirectory $ocDir -WindowStyle Hidden
    }
    else {
        Write-Host "[$ts] :18789 OK" -ForegroundColor Green
    }

    Write-Host ""
    Start-Sleep 30
}
