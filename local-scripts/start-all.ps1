# NEXUS ULTRA — FULL STACK STARTUP (12 ENGINES + INFRASTRUCTURE)
# This script launches the entire Nexus Ultra intelligence engine and provides local/public access.

$appDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
$cosmosDir = "C:\Users\fyou1\.gemini\antigravity\scratch\aistudio-agent"
$logFile = "$appDir\startup_full.log"

function Log($msg, $color="Gray") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $color
    "[$ts] $msg" | Add-Content $logFile
}

Log "=== NEXUS ULTRA: THE 12-ENGINE POWER-UP ===" "Cyan"

# --- 1. CLEANUP ---
Log "System Cleanup: Terminating any stale processes..." "Yellow"
Stop-Process -Name "node", "python", "julia", "ngrok", "n8n", "ollama" -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# --- 2. START INTELLIGENCE STACK (THE 12 ENGINES) ---
Log "Launching 12 Intelligence Engines..." "Cyan"

# Engine 1: Ollama
Log "[1/12] Starting Ollama Engine..."
Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden

# Engine 2: COSMOS
Log "[2/12] Starting COSMOS Orchestration (:9100)..."
Start-Process "python" -ArgumentList "cosmos_server.py" -WorkingDirectory $cosmosDir -WindowStyle Hidden

# Engine 3: PSO Swarm (Julia)
Log "[3/12] Starting PSO Swarm GPU Brain..."
Start-Process "julia" -ArgumentList "local-scripts\pso_swarm.jl" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 4: Memory Core
Log "[4/12] Initializing Tier-2 Memory Core..."
Start-Process "python" -ArgumentList "nexus_memory_core.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 5: Swarm Loop
Log "[5/12] Launching Autonomous Swarm Loop..."
Start-Process "python" -ArgumentList "nexus_swarm_loop.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 6: EH API
Log "[6/12] Starting EH API (:7701)..."
Start-Process "python" -ArgumentList "nexus_eh.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 7: Antennae
Log "[7/12] Starting Antennae Protocol..."
Start-Process "python" -ArgumentList "nexus_antennae.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 8: Evolution
Log "[8/12] Starting Evolution Engine..."
Start-Process "python" -ArgumentList "nexus_evolution.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 9: Rogue Squad
Log "[9/12] Starting Rogue Squad..."
Start-Process "python" -ArgumentList "nexus_rogue_agents.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 10: Mycelium
Log "[10/12] Starting Mycorrhizal Thought Web..."
Start-Process "python" -ArgumentList "nexus_mycelium.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 11: Python Hub Server
Log "[11/12] Starting Internal Hub Server (:7702)..."
Start-Process "python" -ArgumentList "nexus_hub_server.py" -WorkingDirectory $appDir -WindowStyle Hidden

# Engine 12: Feed Ingestor
Log "[12/12] Starting Feed Ingestor..."
Start-Process "python" -ArgumentList "nexus_feed_ingestor.py" -WorkingDirectory $appDir -WindowStyle Hidden

# --- 3. START INFRASTRUCTURE LAYER ---
Log "Launching Infrastructure & Access Layer..." "Cyan"

# Node Command Center
Log "Starting Nexus Main Command Center (:3000)..."
Start-Process "node" -ArgumentList "server.cjs" -WorkingDirectory $appDir -WindowStyle Hidden

# n8n
Log "Starting n8n Automation Engine..."
Start-Process "n8n" -ArgumentList "start" -WorkingDirectory $appDir -WindowStyle Hidden

# ngrok
Log "Starting ngrok Tunnel..."
Start-Process "C:\ngrok\ngrok.exe" -ArgumentList "http 3000" -WorkingDirectory $appDir -WindowStyle Hidden

Start-Sleep 5

# --- 4. ACCESS SUMMARY ---
Log "=== STARTUP COMPLETE: ACCESS SUMMARY ===" "Green"

$localHub = "http://127.0.0.1:3000"
$ehDash = "http://127.0.0.1:7701"
$n8nUrl = "http://127.0.0.1:5678"

Log "LOCAL ACCESS:" "White"
Log "  - Main Command Center: $localHub"
Log "  - EH Dashboard (Inject): $ehDash"
Log "  - n8n Automation: $n8nUrl"
Log "  - Ultimate God Mode Hub: $appDir\nexus_ultimate_hub.html"

# Get Public URL from ngrok
$publicUrl = "Not Found (Waiting for ngrok...)"
for ($i=0; $i -lt 10; $i++) {
    try {
        $tunnels = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
        $url = $tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -ExpandProperty public_url
        if ($url) {
            $publicUrl = $url
            Log "PUBLIC ACCESS (NGROK):" "Magenta"
            Log "  - Live Hub: $publicUrl"
            Log "  - Sales Page: $publicUrl/veilpiercer-pitch.html"
            "$publicUrl/veilpiercer-pitch.html" | Set-Content "$env:USERPROFILE\Desktop\VEILPIERCER-LIVE-URL.txt"
            break
        }
    } catch { Start-Sleep 2 }
}

Log "Check Desktop for VEILPIERCER-LIVE-URL.txt" "Cyan"
Log "System is FULLY OPERATIONAL." "Green"

# --- 5. LAUNCH PREMIUM HUB ---
Log "Opening NEXUS HUB ULTIMATE (God Mode observatory)..." "Cyan"
Start-Process "http://127.0.0.1:3000/nexus_ultimate_hub.html"
