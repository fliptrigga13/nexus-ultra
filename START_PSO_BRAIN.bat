@echo off
REM ══════════════════════════════════════════════════════════════
REM  NEXUS ULTRA — PSO Swarm Brain Launcher  v3
REM  Julia/CUDA GPU PSO engine  |  Port 7700
REM  Dashboard served BY the Julia server at http://localhost:7700/
REM  Offline-capable after first package install.
REM ══════════════════════════════════════════════════════════════

title NEXUS ULTRA — PSO Swarm Brain

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   NEXUS ULTRA  ^|  PSO SWARM BRAIN  ^|  Julia/CUDA    ║
echo  ║   Dashboard  →  http://localhost:7700/              ║
echo  ║   Offline: YES  ^|  GPU: auto-detect                 ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

REM ── 1. Verify Julia is installed ─────────────────────────
where julia >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Julia not found. Download: https://julialang.org/downloads/
    echo  Tick "Add Julia to PATH" during install, then rerun this launcher.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('julia --version 2^>nul') do echo  [OK] %%v

REM ── 2. Set paths ─────────────────────────────────────────
set "ROOT=%~dp0"
set "SCRIPTS=%ROOT%local-scripts"
set "SCRIPT=%SCRIPTS%\pso_swarm.jl"

REM ── 3. Instantiate packages (first run only, cached after) 
echo.
echo  [PSO] Resolving Julia packages (instant after first run)...
julia --project="%SCRIPTS%" -e "using Pkg; Pkg.instantiate()" 2>nul

REM ── 4. Start Julia engine in background window ───────────
echo  [PSO] Starting Julia/CUDA PSO engine on port 7700...
echo.
start "PSO Swarm Engine" julia --project="%SCRIPTS%" --threads=auto "%SCRIPT%"

REM ── 5. Wait for server to be ready, then open browser ────
echo  [PSO] Waiting for server to come online...
:wait_loop
timeout /t 2 /nobreak >nul
powershell -Command "try { (Invoke-WebRequest http://localhost:7700/health -TimeoutSec 1 -UseBasicParsing).StatusCode } catch { 0 }" 2>nul | find "200" >nul
if errorlevel 1 goto wait_loop

echo  [PSO] Server is up! Opening dashboard...
start "" "http://localhost:7700/"

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║  ✅ PSO Swarm Brain is LIVE                          ║
echo  ║  Dashboard: http://localhost:7700/                  ║
echo  ║  Close the "PSO Swarm Engine" window to stop.       ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
pause
