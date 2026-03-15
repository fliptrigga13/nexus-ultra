@echo off
title NEXUS SELF-EVOLUTION ENGINE
color 0B
echo.
echo  ╔════════════════════════════════════════════════════╗
echo  ║   NEXUS SELF-EVOLUTION LOOP — Overnight Learning  ║
echo  ║   Phases: Reflect → Synthesize → Update → Evolve ║
echo  ╚════════════════════════════════════════════════════╝
echo.
echo  Starting evolution with --once flag (single cycle test)
echo  For continuous overnight: pass --cycles 8 (8 cycles)
echo.
cd /d "%~dp0"
python SELF_EVOLUTION_LOOP.py --once
echo.
echo  ✓ Evolution cycle complete. Check evolution_report.md
echo.
pause
