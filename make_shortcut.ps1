$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\fyou1\Desktop\NEXUS CONTROL CENTER.lnk")
$Shortcut.TargetPath = "C:\Users\fyou1\Desktop\New folder\nexus-ultra\NEXUS_CONTROL_CENTER.hta"
$Shortcut.Save()
