Write-Output "AUTO-FIX LIVE STARTED"
Write-Output "Watching for changes..."
Write-Output "----------------------------------------"

# Load tabs
$tabsPath = Join-Path $PSScriptRoot "..\tabs.json"
$tabs = Get-Content $tabsPath -Raw | ConvertFrom-Json

$jotTab = $tabs.edge_all_open_tabs | Where-Object { $_.pageUrl -match "jotform.com" } | Select-Object -First 1

if (-not $jotTab) {
    Write-Output "❌ No JotForm tab found. Cannot start live watcher."
    exit
}

$jotUrl = $jotTab.pageUrl
if ($jotUrl -match "^http://") {
    $jotUrl = $jotUrl -replace "^http://", "https://"
}

$siteDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\site"

if (-not (Test-Path $siteDir)) {
    Write-Output "❌ Site directory not found."
    exit
}

# Clean iframe embed
$cleanIframe = @"
<iframe
    src="$jotUrl"
    style="width: 100%; height: 100vh; border: none;"
    allow="fullscreen; geolocation; microphone; camera; clipboard-read; clipboard-write"
    loading="lazy">
</iframe>
"@

# Define repair function
function Repair-File {
    param($path)

    Write-Output "Change detected: $path"
    $html = Get-Content $path -Raw

    # Ensure viewport
    if ($html -notmatch "name=['""]viewport['""]") {
        Write-Output " • Adding viewport"
        $viewport = "<meta name=""viewport"" content=""width=device-width, initial-scale=1"">"
        if ($html -match "<head>") {
            $html = $html -replace "<head>", "<head>`r`n    $viewport"
        } else {
            $html = $viewport + "`r`n" + $html
        }
    }

    # Replace or insert iframe
    $iframePattern = "<iframe[^>]*jotform[^>]*></iframe>"
    if ($html -match $iframePattern) {
        Write-Output " • Replacing iframe"
        $html = [System.Text.RegularExpressions.Regex]::Replace(
            $html,
            $iframePattern,
            [System.Text.RegularExpressions.Regex]::Escape($cleanIframe).Replace("\r\n", "`r`n")
        )
    } else {
        Write-Output " • Inserting iframe"
        if ($html -match "<body[^>]*>") {
            $html = $html -replace "<body([^>]*)>", "<body`$1>`r`n$cleanIframe"
        } else {
            $html += "`r`n$cleanIframe"
        }
    }

    # Add fallback
    if ($html -notmatch "id=['""]jotform-fallback['""]") {
        Write-Output " • Adding fallback"
        $fallback = @"
<div id=""jotform-fallback"" style=""display:none; padding:1rem; background:#220000; color:#ffcccc; font-family:system-ui;"">
    Cognitive Mint is temporarily unavailable. Check JotForm publish status and account quota.
</div>
"@
        if ($html -match "</body>") {
            $html = $html -replace "</body>", "$fallback`r`n</body>"
        } else {
            $html += "`r`n$fallback"
        }
    }

    Set-Content -Path $path -Value $html -Encoding UTF8
    Write-Output " • File repaired"
}

# FileSystemWatcher
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $siteDir
$watcher.Filter = "*.html"
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

Register-ObjectEvent $watcher Changed -Action { Repair-File $Event.SourceEventArgs.FullPath }
Register-ObjectEvent $watcher Created -Action { Repair-File $Event.SourceEventArgs.FullPath }
Register-ObjectEvent $watcher Renamed -Action { Repair-File $Event.SourceEventArgs.FullPath }

while ($true) {
    Start-Sleep -Seconds 1
}
