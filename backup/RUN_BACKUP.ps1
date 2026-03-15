# ═══════════════════════════════════════════════════════════════
#  NEXUS ULTRA — Automated Google Drive Backup
#  Runs nightly at 2:00 AM via Windows Task Scheduler
#  Uses rclone sync → Google Drive / Nexus-Ultra-Backup/
# ═══════════════════════════════════════════════════════════════

$REMOTE      = "googledrive"
$DRIVE_ROOT  = "Nexus-Ultra-Backup"
$RCLONE      = "C:\Users\fyou1\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.73.2-windows-amd64\rclone.exe"
$LOG_DIR     = "$PSScriptRoot\backup_logs"
$LOG_FILE    = "$LOG_DIR\backup_$(Get-Date -Format 'yyyy-MM-dd').log"
$MAX_LOGS    = 30

# ── Sources to back up ──────────────────────────────────────────
$SOURCES = @(
    @{ local = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"; remote = "nexus-ultra" },
    @{ local = "C:\Users\fyou1\Desktop";                         remote = "desktop" },
    @{ local = "C:\Users\fyou1\Documents";                       remote = "documents" },
    @{ local = "C:\Users\fyou1\.gemini";                         remote = "ai-brain" }
)

# ── Exclusions (large/temp files) ───────────────────────────────
$EXCLUDES = @(
    "--exclude", "node_modules/**",
    "--exclude", "*.tmp",
    "--exclude", "*.log",
    "--exclude", ".git/**",
    "--exclude", "__pycache__/**",
    "--exclude", "*.pyc",
    "--exclude", "Thumbs.db",
    "--exclude", "desktop.ini",
    "--exclude", "*.gguf",           # AI model weights are huge — skip
    "--exclude", "*.bin",
    "--exclude", "*.safetensors"
)

# ── Helpers ──────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line
}

function Test-RcloneRemote {
    & $RCLONE lsd "${REMOTE}:" 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

# ── Main ─────────────────────────────────────────────────────────
Log "══════════════════════════════════════════"
Log " NEXUS ULTRA BACKUP STARTED"
Log " Target: $REMOTE`:$DRIVE_ROOT"
Log "══════════════════════════════════════════"

# Check rclone is installed
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    Log "ERROR: rclone not found. Run SETUP_BACKUP.bat first."
    exit 1
}

# Check remote is reachable
Log "Checking Google Drive connection..."
if (-not (Test-RcloneRemote)) {
    Log "ERROR: Cannot reach '$REMOTE' remote. Run SETUP_BACKUP.bat to reconfigure."
    exit 1
}
Log "Google Drive: CONNECTED"

$failed     = @()
$startTime  = Get-Date

foreach ($src in $SOURCES) {
    $local  = $src.local
    $dest   = "${REMOTE}:${DRIVE_ROOT}/$($src.remote)"

    if (-not (Test-Path $local)) {
        Log "SKIP: $local (not found)"
        continue
    }

    Log ""
    Log "SYNCING: $local  →  $dest"

    $rcloneArgs = @(
        "sync", "$local", "$dest",
        "--progress",
        "--transfers", "8",
        "--checkers", "16",
        "--fast-list",
        "--retries", "3",
        "--low-level-retries", "10",
        "--stats", "30s",
        "--log-level", "INFO",
        "--log-file", "$LOG_FILE"
    ) + $EXCLUDES

    # Use call operator (&) with splatting for better argument handling
    & $RCLONE $rcloneArgs
    if ($LASTEXITCODE -eq 0) {
        Log "OK: $($src.remote) synced successfully"
    } else {
        Log "WARN: $($src.remote) finished with exit code $LASTEXITCODE"
        $failed += $src.remote
    }
}

$elapsed = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 1)

Log ""
Log "══════════════════════════════════════════"
Log " BACKUP COMPLETE in ${elapsed} minutes"
if ($failed.Count -gt 0) {
    Log " FAILED sources: $($failed -join ', ')"
} else {
    Log " ALL SOURCES: OK"
}
Log "══════════════════════════════════════════"

# Clean up old logs (keep last 30)
Get-ChildItem $LOG_DIR -Filter "backup_*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $MAX_LOGS |
    Remove-Item -Force

# Write a quick status file the hub can read
$status = @{
    last_run    = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    elapsed_min = $elapsed
    failed      = $failed
    ok          = ($failed.Count -eq 0)
} | ConvertTo-Json
Set-Content "$PSScriptRoot\backup_status.json" $status

Log "Status written to backup_status.json"
