# watch-trigger.ps1 - Processes files dropped into the drop-zone directory
param([string]$FilePath)

if (-not $FilePath -or -not (Test-Path $FilePath)) {
    Write-Output "watch-trigger: no valid FilePath provided"
    exit 1
}

$filename = Split-Path $FilePath -Leaf
$ext = [System.IO.Path]::GetExtension($filename).ToLower()
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$size = (Get-Item $FilePath).Length

Write-Output "=== DROP ZONE TRIGGER ==="
Write-Output "File      : $filename"
Write-Output "Type      : $ext"
Write-Output "Size      : $size bytes"
Write-Output "Received  : $timestamp"
Write-Output ""

switch ($ext) {
    ".txt" {
        $content = Get-Content $FilePath -Raw -Encoding UTF8
        $preview = $content.Substring(0, [Math]::Min(300, $content.Length))
        Write-Output "Content preview:"
        Write-Output $preview
    }
    ".json" {
        try {
            $json = Get-Content $FilePath -Raw | ConvertFrom-Json
            $keys = $json.PSObject.Properties.Name -join ", "
            Write-Output "JSON keys    : $keys"
            $preview = ($json | ConvertTo-Json -Depth 2 -Compress)
            if ($preview.Length -gt 200) { $preview = $preview.Substring(0, 200) + "..." }
            Write-Output "JSON preview : $preview"
        }
        catch {
            Write-Output "Invalid JSON : $($_.Exception.Message)"
        }
    }
    ".csv" {
        $rows = Import-Csv $FilePath
        Write-Output "CSV rows     : $($rows.Count)"
        if ($rows.Count -gt 0) {
            Write-Output "CSV headers  : $($rows[0].PSObject.Properties.Name -join ', ')"
        }
    }
    ".ps1" {
        Write-Output "PowerShell script detected."
        Write-Output "NOT auto-executing for security. Review manually."
    }
    ".bat" {
        Write-Output "Batch script detected. NOT auto-executing."
    }
    ".html" {
        $sizeKb = [Math]::Round($size / 1024, 1)
        Write-Output "HTML file    : $sizeKb KB"
        Write-Output "Action       : Logged to drop-zone. No auto-execution."
    }
    default {
        Write-Output "Binary/Unknown file type ($ext) -- no preview available."
    }
}

Write-Output ""
Write-Output "=== TRIGGER COMPLETE ==="
