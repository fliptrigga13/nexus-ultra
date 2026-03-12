@echo off
REM ============================================================
REM  START_GOD_MODE_TIER2.bat
REM  Launches the full stack WITH Tier 2 God Mode additions
REM  NEW FILE — adds to your stack, modifies nothing existing
REM ============================================================

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   NEXUS ULTRA — STARTING GOD MODE TIER 2            ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

REM ── Step 1: Start PSO Swarm Brain (CUDA GPU)
echo  [1/3] Starting PSO Swarm Brain on port 7700...
start "PSO SWARM BRAIN" /min cmd /c "julia --threads=auto ""%~dp0local-scripts\pso_swarm.jl"""
timeout /t 3 /nobreak >nul

REM ── Step 2: Start Tier 2 Auto-Learner
echo  [2/3] Starting Tier 2 Auto-Learner...
start "TIER2 GOD MODE" /min cmd /c "python ""%~dp0..\..\.openclaw\workspace\tier2_god_mode.py"""
timeout /t 2 /nobreak >nul

REM ── Step 3: Open dashboards
echo  [3/3] Opening dashboards...
start "" "http://localhost:7700/"
start "" "http://127.0.0.1:9100/hub"

echo.
echo  ✅ GOD MODE TIER 2 ACTIVE
echo  PSO Swarm   : http://localhost:7700/
echo  COSMOS Hub  : http://127.0.0.1:9100/hub
echo  Auto-Learner: running in background (scores every 5min)
echo.
pause
