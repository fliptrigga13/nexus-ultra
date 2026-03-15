$tabsPath = Join-Path $PSScriptRoot "..\tabs.json"
$tabs = Get-Content $tabsPath -Raw | ConvertFrom-Json

$jotTab = $tabs.edge_all_open_tabs | Where-Object { $_.pageUrl -match "jotform.com" } | Select-Object -First 1

if (-not $jotTab) {
    Write-Output "No JotForm tab found."
    exit
}

$url = $jotTab.pageUrl

try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
    Write-Output "JotForm URL: $url"
    Write-Output "Status Code: $($response.StatusCode)"
    Write-Output "Page Title: $($response.ParsedHtml.title)"
}
catch {
    Write-Output "Failed to fetch JotForm URL: $url"
    Write-Output $_.Exception.Message
}
Write-Output "execute placeholder"
