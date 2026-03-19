# ╔══════════════════════════════════════════════════════════════════════╗
# ║  NEXUS MASTER WATCHDOG — 24/7 Service Supervisor                   ║
# ║  Monitors and auto-restarts every service every 30 seconds          ║
# ║  Services: Ollama, Nexus Hub, COSMOS, EH, Swarm Loop     ║
# ╚══════════════════════════════════════════════════════════════════════╝
# Run: powershell -ExecutionPolicy Bypass -File MASTER_WATCHDOG.ps1

$ROOT     = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
$COSMOS   = "C:\Users\fyou1\.gemini\antigravity\scratch\aistudio-agent"
$PYTHON   = "C:\Python314\python.exe"
$NODE     = (Get-Command node -ErrorAction SilentlyContinue)?.Source ?? "node"
$LOG      = "$ROOT\watchdog.log"

# ── Force Ollama to GPU VRAM only — prevents RAM competition with node ──────
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_NUM_PARALLEL      = "1"
$env:OLLAMA_GPU_OVERHEAD      = "0"

# ── Logging ────────────────────────────────────────────────────────────────
function WLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $LOG -Value $line -ErrorAction SilentlyContinue
}

# ── Port check ─────────────────────────────────────────────────────────────
function PortUp($port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $conn = $tcp.BeginConnect("127.0.0.1", $port, $null, $null)
        $ok = $conn.AsyncWaitHandle.WaitOne(1500, $false)
        $tcp.Close()
        return $ok
    } catch { return $false }
}

# ── Start a service (fire & forget minimized window) ───────────────────────
function StartService($name, $exe, $svc_args, $workDir) {
    WLog "STARTING: $name"
    Start-Process $exe -ArgumentList $svc_args -WorkingDirectory $workDir `
        -WindowStyle Minimized -ErrorAction SilentlyContinue
}

# ── SERVICE DEFINITIONS ───────────────────────────────────────────────────
$services = @(
    @{
        Name    = "OLLAMA :11434"
        Port    = 11434
        Check   = { PortUp 11434 }
        Start   = { StartService "Ollama" "ollama" "serve" $ROOT }
        Critical = $true
    },
    @{
        Name    = "NEXUS HUB :3000"
        Port    = 3000
        Check   = { PortUp 3000 }
        Start   = { StartService "Nexus Hub" $NODE "server.cjs" $ROOT }
        Critical = $true
    },
    @{
        Name    = "COSMOS :9100"
        Port    = 9100
        Check   = { PortUp 9100 }
        Start   = { StartService "COSMOS" $PYTHON "cosmos_server.py" $COSMOS }
        Critical = $true
    },
    @{
        Name    = "EH :7701"
        Port    = 7701
        Check   = { PortUp 7701 }
        Start   = { StartService "EH" $PYTHON "nexus_eh.py" $ROOT }
        Critical = $true
    },
    @{
        Name    = "COG ENGINE :7702"
        Port    = 7702
        Check   = { PortUp 7702 }
        Start   = { StartService "Cognitive Engine" $PYTHON "nexus_cognitive_engine.py" $ROOT }
        Critical = $true
    },
    @{
        Name    = "MEMORY GUARD"
        Port    = $null
        Check   = {
            $p = Get-Process powershell -ErrorAction SilentlyContinue |
                 Where-Object { (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine -match "MEMORY_GUARD" }
            return ($p -ne $null)
        }
        Start   = { StartService "Memory Guard" "powershell" "-ExecutionPolicy Bypass -File MEMORY_GUARD.ps1" $ROOT }
        Critical = $true
    },
    @{
        Name    = "SWARM LOOP"
        Port    = $null
        Check   = {
            $p = Get-Process python -ErrorAction SilentlyContinue |
                 Where-Object { (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine -match "swarm_loop" }
            return ($p -ne $null)
        }
        Start   = { StartService "Swarm Loop" $PYTHON "nexus_swarm_loop.py" $ROOT }
        Critical = $false
    },
        Start   = {
            WLog "STARTING: Cloudflare Tunnel → veilpiercer.com"
            Start-Process "cloudflared" -ArgumentList "tunnel run veilpiercer" `
                -WindowStyle Minimized -ErrorAction SilentlyContinue
        }
        Critical = $false
    },
    @{
        Name    = "HIVE SENTINEL"
        Port    = $null
        Check   = {
            $p = Get-Process python -ErrorAction SilentlyContinue |
                 Where-Object { (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine -match "internal_sentinel" }
            return ($p -ne $null)
        }
        Start   = { StartService "Hive Sentinel" $PYTHON "nexus_internal_sentinel.py" $ROOT }
        Critical = $true
    }
)

# ── MAIN LOOP ─────────────────────────────────────────────────────────────
WLog "═══════════════════════════════════════════════════"
WLog " NEXUS MASTER WATCHDOG STARTED"
WLog " Monitoring: $($services.Count) services every 30s"
WLog " Log: $LOG"
WLog "═══════════════════════════════════════════════════"

# Initial startup — wait 2s between each to avoid crashes
foreach ($svc in $services) {
    $up = & $svc.Check
    if (-not $up) {
        & $svc.Start
        WLog "  LAUNCHED: $($svc.Name)"
        Start-Sleep 2
    } else {
        WLog "  ALREADY UP: $($svc.Name)"
    }
}

$cycle = 0
while ($true) {
    Start-Sleep 30
    $cycle++

    foreach ($svc in $services) {
        $up = & $svc.Check
        if (-not $up) {
            WLog "DOWN → RESTARTING: $($svc.Name)"
            & $svc.Start
            Start-Sleep 3
        }
    }

    # Status pulse every 10 cycles (5 minutes)
    if ($cycle % 10 -eq 0) {
        $statuses = $services | ForEach-Object {
            $up = & $_.Check
            "$($_.Name.Split(':')[0].Trim()):" + $(if ($up) {"✓"} else {"✗"})
        }
        WLog "PULSE: $($statuses -join ' | ')"

        # Rotate log if > 5MB
        if ((Get-Item $LOG -ErrorAction SilentlyContinue).Length -gt 5MB) {
            $archived = $LOG -replace "\.log$", "_$(Get-Date -Format 'yyyyMMdd').log"
            Move-Item $LOG $archived -Force
            WLog "Log rotated → $archived"
        }
    }
}
