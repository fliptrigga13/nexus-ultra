@echo off
title NEXUS ULTRA — Manual Backup
color 0B
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   NEXUS ULTRA — RUNNING BACKUP NOW      ║
echo  ║   Syncing to Google Drive (10 TB)        ║
echo  ╚══════════════════════════════════════════╝
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0RUN_BACKUP.ps1"
echo.
echo  Done! Check backup_logs\ for details.
pause
