# Clean BACKDOOR references from active code files

$files = @(
    "nexus_ultimate_hub.html",
    "nexus_hub.html",
    "nexus_personal.html",
    "server.cjs",
    "nexus_memory_core.py",
    "run_diagnostics.py"
)

$replacements = @(
    @{ From = "BACKDOOR API";      To = "EH API" },
    @{ From = "BACKDOOR";          To = "EH API" },
    @{ From = "backdoor-pill";     To = "eh-pill" },
    @{ From = "backdoorOk";        To = "ehOk" },
    @{ From = "_backdoorProc";     To = "_ehProc" },
    @{ From = "BACKDOOR_PY";       To = "EH_PY" },
    @{ From = "backdoor API";      To = "EH API" },
    @{ From = "Backdoor spawned";  To = "EH spawned" },
    @{ From = "BD-ERR:";           To = "EH-ERR:" },
    @{ From = "BD: ";              To = "EH: " },
    @{ From = "WATCHDOG: Backdoor"; To = "WATCHDOG: EH" },
    @{ From = ".backdoor_token";   To = ".eh_token" },
    @{ From = "backdoor_token";    To = "eh_token" },
    @{ From = "SINGLETON INSTANCE (import this in swarm_loop + backdoor)"; To = "SINGLETON INSTANCE (import this in swarm_loop + eh)" }
)

$base = "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

foreach ($file in $files) {
    $path = Join-Path $base $file
    if (-not (Test-Path $path)) { Write-Host "SKIP (not found): $file"; continue }
    $content = Get-Content $path -Raw -Encoding UTF8
    $original = $content
    foreach ($r in $replacements) {
        $content = $content -replace [regex]::Escape($r.From), $r.To
    }
    if ($content -ne $original) {
        Set-Content $path $content -Encoding UTF8
        Write-Host "CLEANED: $file"
    } else {
        Write-Host "NO CHANGE: $file"
    }
}

# Rename .backdoor_token to .eh_token if it exists
$oldTok = Join-Path $base ".backdoor_token"
$newTok = Join-Path $base ".eh_token"
if (Test-Path $oldTok) {
    Rename-Item $oldTok $newTok -Force
    Write-Host "RENAMED: .backdoor_token -> .eh_token"
}

Write-Host "`nCleanup complete."
