# sync_sessions.ps1 — Auto-sync OpenClaw sessions to SQLite brain
# Run manually or register as a scheduled task for auto-sync every 5 min

$scriptPath = "$env:USERPROFILE\.openclaw\workspace\session_writer.py"

if (Test-Path $scriptPath) {
    python $scriptPath --all 2>&1 | Out-Null
}
else {
    Write-Host "session_writer.py not found at $scriptPath"
}
