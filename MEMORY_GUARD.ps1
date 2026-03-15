# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  NEXUS MEMORY GUARD â€” Continuous Google Drive Memory Sync
#  Syncs ONLY the critical memory/state files (fast, <1MB usually)
#  Runs every 5 minutes as a background task
#  Google Drive path: Nexus-Ultra-Backup/MEMORY/
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

$RCLONE    = "C:\Users\fyou1\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.73.2-windows-amd64\rclone.exe"
$CFG       = "C:\Users\fyou1\AppData\Roaming\rclone\rclone.conf"
if (-not (Test-Path $CFG)) {
    $CFG = "$env:AppData\rclone\rclone.conf"
}
$ROOT      = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
$REMOTE    = "googledrive:Nexus-Ultra-Backup/MEMORY"
$INTERVAL  = 300   # 5 minutes
$LOG       = "$ROOT\memory_sync.log"

$MEMORY_FILES = @(
    "nexus_memory.json", "nexus_blackboard.json", "nexus_memory_core.py",
    "memory_core.log", "nexus.log", "tabs.json", "nexus_config.json", ".eh_token"
)
$MEMORY_DIRS = @(
    "chroma_db", "sessions", "backup\backup_logs"
)

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    try { Add-Content -Path $LOG -Value $line -ErrorAction SilentlyContinue } catch {}
}

function Sync-MemoryFiles {
    $ok = 0; $fail = 0
    foreach ($file in $MEMORY_FILES) {
        $src = Join-Path $ROOT $file
        if (Test-Path $src) {
            $err = & $RCLONE copyto "$src" "${REMOTE}/${file}" --config "$CFG" 2>&1
            if ($LASTEXITCODE -eq 0) { $ok++ }
            else { $fail++; Log "  FAIL: $file - $err" }
        }
    }
    foreach ($dir in $MEMORY_DIRS) {
        $src = Join-Path $ROOT $dir
        if (Test-Path $src) {
            $err = & $RCLONE sync "$src" "${REMOTE}/dirs/${dir}" --config "$CFG" --exclude "*.tmp" --exclude "__pycache__/**" --exclude "*.pyc" 2>&1
            if ($LASTEXITCODE -eq 0) { $ok++ }
            else { $fail++; Log "  FAIL DIR: $dir - $($err | Select-Object -First 1)" }
        }
    }
    return @{ ok=$ok; fail=$fail }
}

function Write-StatusFile($result, $elapsed) {
    $stat = "OK"
    if ($result.fail -gt 0) { $stat = "PARTIAL" }
    $status = @{
        last_sync  = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        files_ok   = $result.ok
        files_fail = $result.fail
        status     = $stat
        elapsed_ms = $elapsed
        remote     = $REMOTE
    }
    $status | ConvertTo-Json | Set-Content "$ROOT\backup\memory_sync_status.json" -Encoding UTF8
}

Log "=== NEXUS MEMORY GUARD STARTING ==="
if (-not (Test-Path "$RCLONE")) { Log "ERROR: rclone not found at $RCLONE"; exit 1 }

$syncCount = 0
while ($true) {
    $syncCount++
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Log "--- Sync #$syncCount ---"
    
    $result = Sync-MemoryFiles
    $sw.Stop()
    $elapsed = [int]$sw.ElapsedMilliseconds
    Write-StatusFile $result $elapsed

    if ($result.fail -eq 0) {
        Log "OK: $($result.ok) items synced in ${elapsed}ms"
    } else {
        Log "PARTIAL: $($result.ok) OK, $($result.fail) FAILED"
    }

    if (Test-Path $LOG) {
        if ((Get-Item $LOG).Length -gt 500KB) {
            $lines = Get-Content $LOG
            $lines | Select-Object -Last 200 | Set-Content $LOG
        }
    }
    Start-Sleep -Seconds $INTERVAL
}

