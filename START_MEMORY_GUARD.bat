@echo off
title NEXUS MEMORY GUARD — Google Drive Sync
color 0A
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║  NEXUS MEMORY GUARD — Active                ║
echo  ║  Syncing memory to Google Drive every 5min  ║
echo  ║  Files: nexus_memory.json, blackboard,      ║
echo  ║         chroma_db, sessions, config         ║
echo  ╚══════════════════════════════════════════════╝
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MEMORY_GUARD.ps1"
pause
