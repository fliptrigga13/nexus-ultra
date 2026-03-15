# capture.ps1 - Clipboard Text + Full Screenshot Capture
# Saves timestamped files to the captures/ directory

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$captureDir = Join-Path $PSScriptRoot "..\captures"

if (-not (Test-Path $captureDir)) {
    New-Item -ItemType Directory -Path $captureDir | Out-Null
}

Write-Output "=== NEXUS CAPTURE: $timestamp ==="

# ── Clipboard ─────────────────────────────
try {
    Add-Type -AssemblyName System.Windows.Forms
    $clipText = [System.Windows.Forms.Clipboard]::GetText()
    if ($clipText -and $clipText.Length -gt 0) {
        $clipFile = Join-Path $captureDir "clip_$timestamp.txt"
        $clipText | Out-File -FilePath $clipFile -Encoding UTF8
        Write-Output "Clipboard saved  : clip_$timestamp.txt ($($clipText.Length) chars)"
    }
    else {
        Write-Output "Clipboard        : empty / non-text"
    }
}
catch {
    Write-Output "Clipboard error  : $($_.Exception.Message)"
}

# ── Screenshot ────────────────────────────
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)

    $screenFile = Join-Path $captureDir "screen_$timestamp.png"
    $bitmap.Save($screenFile, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose(); $bitmap.Dispose()

    $sizeMB = [math]::Round((Get-Item $screenFile).Length / 1MB, 2)
    Write-Output "Screenshot saved : screen_$timestamp.png ($sizeMB MB)"
}
catch {
    Write-Output "Screenshot error : $($_.Exception.Message)"
}

Write-Output "=== CAPTURE COMPLETE ==="
