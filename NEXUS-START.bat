@echo off
title NEXUS ULTRA — AUTO-START
cd /d "c:\Users\fyou1\Desktop\New folder\nexus-ultra"
echo [NEXUS] Resurrecting PM2 processes...
pm2 resurrect
timeout /t 3
pm2 status
echo [NEXUS] All systems online.
pause
