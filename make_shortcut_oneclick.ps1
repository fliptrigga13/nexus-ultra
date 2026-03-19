$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\fyou1\Desktop\ONE CLICK START.lnk")
$Shortcut.TargetPath = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\START_ULTIMATE_GOD_MODE.bat"
$Shortcut.Save()
