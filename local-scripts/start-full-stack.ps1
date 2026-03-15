# start-full-stack.ps1
# Launch the entire NEXUS + COSMOS + OpenClaw stack

$logFile = "$env:USERPROFILE\.nexus-stack.log"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -Append -FilePath $logFile | Write-Host
}

Log "=== NEXUS FULL STACK STARTUP ==="

# 1. SSHD
$sshd = Get-Service sshd -ErrorAction SilentlyContinue
if ($sshd -and $sshd.Status -ne "Running") {
    Start-Service sshd -ErrorAction SilentlyContinue
    Log "[SSHD] Started"
}
elseif ($sshd) {
    Log "[SSHD] Already running"
}
else {
    Log "[SSHD] Not installed, skip"
}

# 2. NEXUS ULTRA - Node.js on port 3000
$nexusDir = "$env:USERPROFILE\Desktop\New folder\nexus-ultra"
$nexusProc = Get-Process -Name node -ErrorAction SilentlyContinue
if (-not $nexusProc) {
    $p = @{
        FilePath         = "node"
        ArgumentList     = "server.cjs"
        WorkingDirectory = $nexusDir
        WindowStyle      = "Hidden"
    }
    Start-Process @p
    Log "[NEXUS] Started on :3000"
}
else {
    Log "[NEXUS] Already running"
}

# 3. OpenClaw Gateway - port 18789
$ocDir = "$env:USERPROFILE\.openclaw"
$ocGateway = "$ocDir\gateway.cmd"
$ocRunning = netstat -ano | Select-String ":18789" | Select-String "LISTENING"
if ((-not $ocRunning) -and (Test-Path $ocGateway)) {
    $p = @{
        FilePath         = "cmd.exe"
        ArgumentList     = "/c `"$ocGateway`""
        WorkingDirectory = $ocDir
        WindowStyle      = "Hidden"
    }
    Start-Process @p
    Log "[OPENCLAW] Started on :18789"
}
elseif ($ocRunning) {
    Log "[OPENCLAW] Already running on :18789"
}
else {
    Log "[OPENCLAW] gateway.cmd not found, skip"
}

# 4. COSMOS Swarm Server - Python on port 9100
$cosmosScript = "$env:USERPROFILE\.gemini\antigravity\scratch\aistudio-agent\cosmos_server.py"
$cosmosDir = Split-Path $cosmosScript
$cosmosRunning = netstat -ano | Select-String ":9100" | Select-String "LISTENING"
if ((-not $cosmosRunning) -and (Test-Path $cosmosScript)) {
    $p = @{
        FilePath         = "python"
        ArgumentList     = $cosmosScript
        WorkingDirectory = $cosmosDir
        WindowStyle      = "Hidden"
    }
    Start-Process @p
    Log "[COSMOS] Started on :9100"
}
elseif ($cosmosRunning) {
    Log "[COSMOS] Already running on :9100"
}
else {
    Log "[COSMOS] cosmos_server.py not found, skip"
}

# 5. Ollama - LLM server on port 11434
$ollamaRunning = netstat -ano | Select-String ":11434" | Select-String "LISTENING"
if (-not $ollamaRunning) {
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCmd) {
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle "Hidden"
        Log "[OLLAMA] Started on :11434"
    }
    else {
        Log "[OLLAMA] Not installed, skip"
    }
}
else {
    Log "[OLLAMA] Already running on :11434"
}

# 6. Julia GPU Sentinel - port 8080
$juliaScript = "$env:USERPROFILE\Desktop\server.jl"
$juliaDir = Split-Path $juliaScript
$juliaRunning = netstat -ano | Select-String ":8080" | Select-String "LISTENING"
if ((-not $juliaRunning) -and (Test-Path $juliaScript)) {
    $juliaCmd = Get-Command julia -ErrorAction SilentlyContinue
    if ($juliaCmd) {
        $p = @{
            FilePath         = "julia"
            ArgumentList     = $juliaScript
            WorkingDirectory = $juliaDir
            WindowStyle      = "Hidden"
        }
        Start-Process @p
        Log "[JULIA] Started on :8080"
    }
    else {
        Log "[JULIA] julia.exe not found, skip"
    }
}
elseif ($juliaRunning) {
    Log "[JULIA] Already running on :8080"
}
else {
    Log "[JULIA] server.jl not found, skip"
}

# Summary - wait for processes to bind their ports
Start-Sleep -Seconds 3
Log ""
Log "=== STACK STATUS ==="

$ports = @{
    "NEXUS ULTRA" = 3000
    "COSMOS"      = 9100
    "Julia GPU"   = 8080
    "OpenClaw"    = 18789
    "Ollama"      = 11434
    "SSH"         = 22
}

foreach ($name in $ports.Keys) {
    $port = $ports[$name]
    $listening = netstat -ano | Select-String ":$port " | Select-String "LISTENING"
    $status = if ($listening) { "UP" } else { "DOWN" }
    Log "  $($name.PadRight(14)) :$port  [$status]"
}

Log ""
Log "Full stack startup complete."
