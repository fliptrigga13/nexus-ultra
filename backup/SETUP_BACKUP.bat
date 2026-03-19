@echo off
title NEXUS ULTRA — Backup Setup (Google Drive)
color 0A
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   NEXUS ULTRA — CLOUD BACKUP SETUP      ║
echo  ║   Target: Google One (10 TB)             ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ── Step 1: Install rclone ──────────────────────────────────────
echo [1/3] Installing rclone...
winget install --id Rclone.Rclone -e --accept-source-agreements --accept-package-agreements
if %errorlevel% neq 0 (
    echo  rclone already installed or winget failed — trying choco...
    where rclone >nul 2>&1
    if %errorlevel% neq 0 (
        echo  Downloading rclone manually...
        powershell -Command "& { Invoke-WebRequest 'https://downloads.rclone.org/rclone-current-windows-amd64.zip' -OutFile '$env:TEMP\rclone.zip'; Expand-Archive '$env:TEMP\rclone.zip' -DestinationPath '$env:TEMP\rclone_extract' -Force; $exe = Get-ChildItem '$env:TEMP\rclone_extract' -Recurse -Filter rclone.exe | Select-Object -First 1; Copy-Item $exe.FullName 'C:\Windows\System32\rclone.exe' }"
    )
)
echo  [OK] rclone ready.
echo.

:: ── Step 2: Configure Google Drive ─────────────────────────────
echo [2/3] Configuring Google Drive connection...
echo.
echo  A browser window will open to log into your Google account.
echo  Follow the steps:
echo    1. Type: n  (new remote)
echo    2. Name:  googledrive
echo    3. Type:  drive  (Google Drive — option 18 or search "drive")
echo    4. Press Enter to skip client_id and client_secret
echo    5. Scope: 1  (full access)
echo    6. Press Enter for root_folder_id
echo    7. Press Enter for service_account_file
echo    8. Auto config: y
echo    9. Team drive: n
echo    10. OK: y
echo    11. Type: q  (quit config)
echo.
pause
rclone config
echo.
echo  [OK] Google Drive configured.

:: ── Step 3: Install Scheduled Task ─────────────────────────────
echo [3/3] Installing nightly backup schedule (2:00 AM daily)...
set SCRIPT_PATH=%~dp0RUN_BACKUP.ps1
set TASK_CMD=powershell -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "%SCRIPT_PATH%"

schtasks /delete /tn "NexusUltraBackup" /f >nul 2>&1
schtasks /create ^
  /tn "NexusUltraBackup" ^
  /tr "%TASK_CMD%" ^
  /sc DAILY ^
  /st 02:00 ^
  /ru "%USERNAME%" ^
  /rl HIGHEST ^
  /f

if %errorlevel% equ 0 (
    echo  [OK] Scheduled task created — runs daily at 2:00 AM
) else (
    echo  [WARN] Could not create scheduled task — run SETUP_BACKUP.bat as Administrator
)

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║  SETUP COMPLETE                          ║
echo  ║  Run RUN_BACKUP.bat to test now          ║
echo  ╚══════════════════════════════════════════╝
echo.
pause
