# force-stabilize.ps1
# Nexus Ultra - Force Stabilize Script
Write-Output "=== FORCE STABILIZE INITIATED ==="
Write-Output "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output "Scanning system processes..."

$nodeProcs = Get-Process -Name "node" -ErrorAction SilentlyContinue
if ($nodeProcs) {
    Write-Output "Node.js processes detected: $($nodeProcs.Count)"
    foreach ($p in $nodeProcs) {
        Write-Output "  PID $($p.Id) | CPU: $($p.CPU)s | Mem: $([math]::Round($p.WorkingSet/1MB, 1)) MB"
    }
} else {
    Write-Output "No Node.js processes currently running."
}

Write-Output "System memory snapshot:"
$mem = Get-CimInstance Win32_OperatingSystem
$free = [math]::Round($mem.FreePhysicalMemory / 1MB, 1)
$total = [math]::Round($mem.TotalVisibleMemorySize / 1MB, 1)
Write-Output "  Free: ${free} GB / Total: ${total} GB"

Write-Output "=== FORCE STABILIZE COMPLETE ==="
