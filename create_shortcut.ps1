$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("$env:USERPROFILE\Desktop\NEXUS GOD MODE.lnk")
$s.TargetPath = "$env:USERPROFILE\Desktop\New folder\nexus-ultra\START_ULTIMATE_GOD_MODE.bat"
$s.WorkingDirectory = "$env:USERPROFILE\Desktop\New folder\nexus-ultra"
$s.Save()
Write-Host "Shortcut created on desktop."
