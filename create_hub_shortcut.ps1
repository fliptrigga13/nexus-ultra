param (
    [string]$ShortcutName = "NEXUS_ULTIMATE_HUB",
    [string]$TargetUrl = "http://127.0.0.1:3000/nexus_ultimate_hub.html",
    [string]$IconPath = ""
)

$WScriptShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutFile = "$DesktopPath\$ShortcutName.url"

# Create the .url file content
$Content = @"
[InternetShortcut]
URL=$TargetUrl
"@

if ($IconPath -and (Test-Path $IconPath)) {
    $Content += "`nIconIndex=0`nIconFile=$IconPath"
}

set-content -Path $ShortcutFile -Value $Content
Write-Host "Created Desktop Shortcut: $ShortcutFile"
