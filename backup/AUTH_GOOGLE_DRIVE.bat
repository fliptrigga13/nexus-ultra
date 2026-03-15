@echo off
title NEXUS — Google Drive Auth
set RCLONE=C:\Users\fyou1\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.73.2-windows-amd64\rclone.exe

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║  NEXUS — GOOGLE DRIVE SETUP                     ║
echo  ║  Your browser will open for Google login        ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Follow the wizard:
echo    Name: googledrive
echo    Storage type: Choose "Google Drive" (type 18 or search)
echo    client_id: [blank — press Enter]
echo    client_secret: [blank — press Enter]
echo    scope: 1 (Full access)
echo    root_folder_id: [blank — press Enter]
echo    service_account_file: [blank — press Enter]
echo    Edit advanced config? n
echo    Use auto config? y   ← browser opens HERE, sign in to Google
echo    Configure as team drive? n
echo    Keep this remote? y
echo    Quit with: q
echo.
pause
"%RCLONE%" config
echo.
echo Done! Now run MOUNT_GOOGLE_DRIVE.bat to mount as Z:
pause
