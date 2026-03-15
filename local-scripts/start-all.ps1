# NEXUS ULTRA + ngrok Auto-Start Script
# Runs on Windows login via Task Scheduler

$appDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
$logFile = "$appDir\startup.log"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Add-Content $logFile
}

Log "=== NEXUS ULTRA STARTUP ==="

# Kill existing instances
Stop-Process -Name "node" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "ngrok" -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# Start NEXUS server
Log "Starting NEXUS server..."
$server = Start-Process "node" -ArgumentList "server.cjs" -WorkingDirectory $appDir -WindowStyle Hidden -PassThru
Log "NEXUS server PID: $($server.Id)"

Start-Sleep 2

# Start n8n
Log "Starting n8n..."
$n8n = Start-Process "n8n" -ArgumentList "start" -WorkingDirectory $appDir -WindowStyle Hidden -PassThru
Log "n8n PID: $($n8n.Id)"

Start-Sleep 3


# Start ngrok
Log "Starting ngrok..."
$ngrok = Start-Process "C:\ngrok\ngrok.exe" -ArgumentList "http 3000" -WorkingDirectory $appDir -WindowStyle Hidden -PassThru
Log "ngrok PID: $($ngrok.Id)"

Start-Sleep 4

# Get the public URL from ngrok API
$maxTries = 10
for ($i = 0; $i -lt $maxTries; $i++) {
    try {
        $tunnels = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
        $url = $tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -ExpandProperty public_url
        if ($url) {
            Log "PUBLIC URL: $url"
            Log "Sales page: $url/veilpiercer-pitch.html"
            # Write URL to easy-access file on Desktop
            "$url/veilpiercer-pitch.html" | Set-Content "$env:USERPROFILE\Desktop\VEILPIERCER-LIVE-URL.txt"
            Log "URL saved to Desktop: VEILPIERCER-LIVE-URL.txt"
            break
        }
    }
    catch {
        Start-Sleep 2
    }
}

Log "Startup complete."
