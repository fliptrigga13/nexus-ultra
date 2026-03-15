@echo off
title NEXUS — Mount Google Drive as Z:
set RCLONE=C:\Users\fyou1\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.73.2-windows-amd64\rclone.exe

echo.
echo  Mounting Google Drive as Z:\ ...
echo  (Keep this window open — closing it unmounts the drive)
echo.

:: Install WinFsp if not present (required for rclone mount on Windows)
where winfsp-x64.dll >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing WinFsp (required for drive mounting)...
    winget install -e --id "WinFsp.WinFsp" --accept-source-agreements --accept-package-agreements
    echo  WinFsp installed. Continuing...
    echo.
)

:: Mount Google Drive as Z:
"%RCLONE%" mount googledrive: Z: ^
    --vfs-cache-mode full ^
    --vfs-cache-max-size 10G ^
    --vfs-read-chunk-size 32M ^
    --buffer-size 256M ^
    --dir-cache-time 30s ^
    --log-level INFO ^
    --volname "GoogleDrive-30TB"

echo.
echo  Drive unmounted.
pause
