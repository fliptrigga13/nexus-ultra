# VEILPIERCER — NEXUS CONNECTION KIT
# Use this to verify your connection to the NEXUS ULTRA control plane.

$API = "http://127.0.0.1:3000"
Write-Host "◈ VEILPIERCER: Verifying connection to NEXUS..." -ForegroundColor Cyan

try {
    $res = Invoke-RestMethod "$API/status" -ErrorAction Stop
    if ($res.ok) {
        Write-Host "✅ CONNECTED: NEXUS ULTRA v2 is Online." -ForegroundColor Green
        Write-Host "   Node: $($res.port)"
        Write-Host "   Uptime: $($res.uptime)"
    }
} catch {
    Write-Host "❌ CONNECTION ERROR: Could not reach NEXUS." -ForegroundColor Red
    Write-Host "   Ensure your ngrok tunnel or local server is active."
}

Write-Host "`nPress any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
