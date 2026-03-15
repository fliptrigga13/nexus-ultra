Write-Output "AUTO-FIX DEEP STARTED"
Write-Output "----------------------------------------"

# Load tabs
$tabsPath = Join-Path $PSScriptRoot "..\tabs.json"
$tabs = Get-Content $tabsPath -Raw | ConvertFrom-Json

$jotTab = $tabs.edge_all_open_tabs | Where-Object { $_.pageUrl -match "jotform.com" } | Select-Object -First 1

if (-not $jotTab) {
    Write-Output "❌ No JotForm tab found. Cannot auto-fix."
    exit
}

$jotUrl = $jotTab.pageUrl
if ($jotUrl -match "^http://") {
    $jotUrl = $jotUrl -replace "^http://", "https://"
}

Write-Output "Using JotForm URL: $jotUrl"

# Target directory
$siteDir = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\site"

if (-not (Test-Path $siteDir)) {
    Write-Output "❌ Site directory not found:"
    Write-Output $siteDir
    exit
}

Write-Output "Scanning directory:"
Write-Output $siteDir

# Clean iframe embed
$cleanIframe = @"
<iframe
    src="$jotUrl"
    style="width: 100%; height: 100vh; border: none;"
    allow="fullscreen; geolocation; microphone; camera; clipboard-read; clipboard-write"
    loading="lazy">
</iframe>
"@

# Process all HTML files
Get-ChildItem -Path $siteDir -Filter *.html -Recurse | ForEach-Object {

    Write-Output "Processing: $($_.FullName)"
    $html = Get-Content $_.FullName -Raw

    # Ensure viewport
    if ($html -notmatch "name=['""]viewport['""]") {
        Write-Output " • Adding viewport meta"
        $viewport = "<meta name=""viewport"" content=""width=device-width, initial-scale=1"">"
        if ($html -match "<head>") {
            $html = $html -replace "<head>", "<head>`r`n    $viewport"
        } else {
            $html = $viewport + "`r`n" + $html
        }
    }

    # Replace or insert iframe
    $iframePattern = "<iframe[^>]*jotform[^>]*></iframe>"
    if ($html -match $iframePattern