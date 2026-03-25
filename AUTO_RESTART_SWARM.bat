@echo off
title NEXUS SWARM — AUTO-RESTART GUARDIAN
color 0A
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   NEXUS SWARM — AUTO-RESTART GUARDIAN       ║
echo  ║   Watches swarm loop — restarts on crash    ║
echo  ║   Ctrl+C to stop                            ║
echo  ╚══════════════════════════════════════════════╝
echo.

cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

:LOOP
echo [%time%] Starting swarm loop...
python nexus_swarm_loop.py >> swarm_loop.log 2>&1

echo.
echo [%time%] ⚠️  Swarm loop exited. Restarting in 10 seconds...
echo [%time%] SWARM RESTART - Exit detected >> swarm_loop.log
timeout /t 10 /nobreak

goto LOOP
