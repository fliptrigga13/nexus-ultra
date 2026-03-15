<#
.SYNOPSIS
    Nexus-Ultra local setup & stabilization script
.DESCRIPTION
    Patches index.html, starts Node backend, injects fake tabs, runs requested action.
.PARAMETER ProjectDir
    Folder containing index.html and server.cjs
.PARAMETER BotSecret
    x-api-key value for localhost:3000 endpoints (default: Burton)
.PARAMETER Action
    Action to send to /run (default: force-stabilize)
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateScript({ Test-Path $_ -PathType Container })]
    [string]$ProjectDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra",

    [Parameter(Mandatory = $false)]
    [string]$BotSecret = "Burton",

    [Parameter(Mandatory = $false)]
    [string]$Action = "force-stabilize"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "$(Get-Date -Format 'HH:mm:ss') $Message" -ForegroundColor $Color
}

# Change directory
try {
    Set-Location $ProjectDir -ErrorAction Stop
    Write-Log "Working directory: $ProjectDir"
} catch {
    Write-Log "Failed to change directory: $($_.Exception.Message)" "Red"
    exit 1
}

# Patch index.html
$indexPath = Join-Path $ProjectDir "index.html"
if (-not (Test-Path $indexPath -PathType Leaf)) {
    Write-Log "index.html not found in $ProjectDir" "Red"
    exit 1
}

Write-Log "Patching index.html..."

$content = Get-Content -Path $indexPath -Raw -Encoding UTF8

$content = $content -replace '(?i)<button\s+[^>]*onclick\s*=\s*"execute\(\)"[^>]*>[\s\S]*?Execute</button>',
                           '<button onclick="triggerN8n()">Trigger n8n</button>'

$content = $content -replace '(?i)function\s+execute\s*\(\)\s*\{\s*sendAction\s*\(\s*"execute"\s*,\s*"EXECUTE"\s*\)\s*;\s*\}',
                           'function triggerN8n() { sendAction("trigger-n8n", "TRIGGER N8N"); }'

Set-Content -Path $indexPath -Value $content -Encoding UTF8 -NoNewline
Write-Log "index.html patched"

# Kill old node processes
Write-Log "Killing existing node processes..."
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Start server.cjs
Write-Log "Launching node server.cjs ..."
Start-Process -FilePath "node" `
              -ArgumentList "server.cjs" `
              -WorkingDirectory $ProjectDir `
              -WindowStyle Hidden

Start-Sleep -Seconds 1.5

# Wait for port 3000
Write-Log "Waiting for port 3000 (max 20s)..."

$maxWait = 20; $elapsed = 0; $ready = $false
while ($elapsed -lt $maxWait) {
    $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 3000 -WarningAction SilentlyContinue
    if ($tcp.TcpTestSucceeded) { $ready = $true; break }
    Write-Host "." -NoNewline -ForegroundColor Gray
    Start-Sleep -Seconds 1; $elapsed++
}
Write-Host ""

if (-not $ready) {
    Write-Log "Port 3000 not reachable after ${maxWait}s" "Red"
    exit 1
}

Write-Log "Port 3000 ready ✓" "Green"

# Send tabs
$tabs = @(
    @{ tabId = 1822238194; pageTitle = "NEXUS | ULTRA Tier Stable"; pageUrl = "http://127.0.0.1"; isCurrent = $true },
    @{ tabId = 1822238174; pageTitle = "index.html"; pageUrl = "file:///C:/Users/fyou1/Desktop/veil la/New folder/nexus-ultra/index.html"; isCurrent = $false }
)

$payload = @{ edge_all_open_tabs = $tabs } | ConvertTo-Json -Depth 6 -Compress

Write-Log "Sending tabs (secret: $BotSecret)..."

try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:3000/tabs" `
                              -Method Post `
                              -Headers @{ "x-api-key" = $BotSecret } `
                              -Body $payload `
                              -ContentType "application/json" `
                              -TimeoutSec 10
    Write-Log "POST /tabs OK: $($resp | ConvertTo-Json -Depth 2 -Compress)" "Green"
} catch {
    Write-Log "POST /tabs failed: $($_.Exception.Message)" "Red"
}

# Send action
$body = @{ action = $Action } | ConvertTo-Json -Compress

Write-Log "Sending action: $Action (secret: $BotSecret)..."

try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:3000/run" `
                              -Method Post `
                              -Headers @{ "x-api-key" = "Burton" }  
                              -Body $body `
                              -ContentType "application/json" `
                              -TimeoutSec 15
    Write-Log "POST /run OK: $($resp | ConvertTo-Json -Depth 2 -Compress)" "Green"
} catch {
    Write-Log "POST /run failed: $($_.Exception.Message)" "Red"
}

Write-Host ""
Write-Host "Setup finished (secret: $BotSecret). Press Enter to close..." -ForegroundColor Green
Read-Host