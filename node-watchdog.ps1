# node-watchdog.ps1
# Auto-restarts node server.cjs on crash — survives Bitdefender kills
# v2: smart backoff, port-in-use detection, crash loop guard
$WorkDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
$LogFile  = "$WorkDir\node_watchdog.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [WATCHDOG] $msg"
    Write-Host $line
    Add-Content $LogFile $line -Encoding UTF8
}

function IsPortInUse([int]$port) {
    $connections = netstat -ano 2>$null | Select-String ":$port\s" | Select-String "LISTENING"
    return $connections.Count -gt 0
}

Log "Node watchdog started (v2 — smart backoff)"
$restarts      = 0
$quickExits    = 0  # count of exits within 10s (crash loop detector)
$maxQuickExits = 5  # if 5 quick exits in a row → long pause before retry

while ($true) {
    # If port 3000 is already in use, wait for it to free up instead of crash-looping
    if (IsPortInUse 3000) {
        Log "Port 3000 is already in use — waiting 30s for it to free..."
        Start-Sleep 30
        continue
    }

    Log "Starting node server.cjs (restart #$restarts)..."
    $startTime = Get-Date
    try {
        $p = Start-Process node -ArgumentList "server.cjs" `
            -WorkingDirectory $WorkDir `
            -Environment @{
                OLLAMA_MAX_LOADED_MODELS = "1"
                OLLAMA_NUM_PARALLEL      = "1"
                OLLAMA_GPU_OVERHEAD      = "0"
            } `
            -NoNewWindow -PassThru -Wait `
            -RedirectStandardError "$WorkDir\server_error.log"
        $elapsed = ((Get-Date) - $startTime).TotalSeconds
        Log "Node exited (code: $($p.ExitCode), ran ${elapsed}s) — restarting in 5s..."

        # Crash loop detection: if it died in under 10s, increment counter
        if ($elapsed -lt 10) {
            $quickExits++
            Log "Quick exit #$quickExits detected"
            if ($quickExits -ge $maxQuickExits) {
                Log "CRASH LOOP: $maxQuickExits quick exits in a row — pausing 60s to cool down"
                Start-Sleep 60
                $quickExits = 0  # reset counter after the long pause
            }
        } else {
            $quickExits = 0  # healthy run, reset the counter
        }
    } catch {
        Log "Failed to start node: $_"
    }
    $restarts++
    Start-Sleep 5
}
