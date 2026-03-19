param (
    [string]$ShortcutName = "ACTIVATE_GOD_MODE",
    [string]$TargetPath = "c:\Users\fyou1\Desktop\New folder\nexus-ultra\START_ULTIMATE_GOD_MODE.bat",
    [string]$IconPath = "C:\Windows\System32\shell32.dll",
    [int]$IconIndex = 238
)

$WScriptShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutFile = "$DesktopPath\$ShortcutName.lnk"

$Shortcut = $WScriptShell.CreateShortcut($ShortcutFile)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = (Split-Path $TargetPath)
$Shortcut.IconLocation = "$IconPath, $IconIndex"
$Shortcut.Save()

Write-Host "Created Desktop Shortcut: $ShortcutFile"
