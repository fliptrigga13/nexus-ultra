$services = @(
    @{ Name = "Ollama LLM";        Url = "http://127.0.0.1:11434" },
    @{ Name = "COSMOS API";        Url = "http://127.0.0.1:9100"  },
    @{ Name = "PSO Swarm (Julia)"; Url = "http://127.0.0.1:7700"  },
    @{ Name = "Execution Hub";     Url = "http://127.0.0.1:7701"  },
    @{ Name = "Hub Server";        Url = "http://127.0.0.1:7702"  }
)

$processes = @(
    "nexus_swarm_loop",
    "nexus_cognitive_engine",
    "nexus_eh",
    "nexus_antennae",
    "nexus_evolution",
    "nexus_rogue_agents",
    "nexus_mycelium",
    "nexus_hub_server",
    "SELF_EVOLUTION_LOOP"
)

Write-Host "`n======================================" -ForegroundColor Cyan
Write-Host "  NEXUS HEALTH CHECK" -ForegroundColor Cyan
Write-Host "======================================`n" -ForegroundColor Cyan

Write-Host "[ HTTP ENDPOINTS ]" -ForegroundColor Yellow
foreach ($svc in $services) {
    try {
        $r = Invoke-WebRequest -Uri $svc.Url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        Write-Host "  [OK]   $($svc.Name) ($($svc.Url))" -ForegroundColor Green
    } catch {
        Write-Host "  [DOWN] $($svc.Name) ($($svc.Url))" -ForegroundColor Red
    }
}

Write-Host "`n[ PYTHON PROCESSES ]" -ForegroundColor Yellow
$running = Get-Process python -ErrorAction SilentlyContinue |
    ForEach-Object { (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine }

foreach ($proc in $processes) {
    $found = $running | Where-Object { $_ -match $proc }
    if ($found) {
        Write-Host "  [OK]   $proc" -ForegroundColor Green
    } else {
        Write-Host "  [DOWN] $proc" -ForegroundColor Red
    }
}

Write-Host "`n[ LOG TAIL (last 3 lines each) ]" -ForegroundColor Yellow
$logs = Get-ChildItem "C:\Users\fyou1\Desktop\New folder\nexus-ultra\*.log" -ErrorAction SilentlyContinue
foreach ($log in $logs) {
    $tail = Get-Content $log -Tail 3 -ErrorAction SilentlyContinue
    if ($tail) {
        Write-Host "  -- $($log.Name) --" -ForegroundColor DarkGray
        $tail | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
    }
}

Write-Host "`n======================================`n" -ForegroundColor Cyan
