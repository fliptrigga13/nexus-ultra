@echo off
REM ══════════════════════════════════════════════════════════════
REM  NEXUS ULTRA — PSO Swarm Brain Launcher  v2
REM  Julia/CUDA GPU PSO engine  |  Port 7700
REM  Offline-capable: packages auto-install on first run only.
REM  After that: 100% local, zero internet required.
REM ══════════════════════════════════════════════════════════════

title NEXUS ULTRA — PSO Swarm Brain

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   NEXUS ULTRA  ^|  PSO SWARM BRAIN  ^|  Julia/CUDA    ║
echo  ║   GPU-accelerated Particle Swarm Optimization       ║
echo  ║   Offline mode: YES  ^|  Port: 7700                  ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

REM ── 1. Verify Julia is installed ─────────────────────────
where julia >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Julia is not installed or not in PATH.
    echo.
    echo  Download Julia from:  https://julialang.org/downloads/
    echo  During install: make sure to tick "Add Julia to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('julia --version 2^>nul') do echo  [OK] %%v found.

REM ── 2. Set paths ─────────────────────────────────────────
set "ROOT=%~dp0"
set "SCRIPTS=%ROOT%local-scripts"
set "SCRIPT=%SCRIPTS%\pso_swarm.jl"
set "DASHBOARD=%ROOT%pso-trainer.html"

REM ── 3. First-run: instantiate packages into the project env
echo.
echo  [PSO] Checking Julia package environment...
echo  [PSO] (First run installs CUDA.jl, HTTP.jl, JSON3.jl — ~3 min)
echo  [PSO] Subsequent runs are instant (fully offline).
echo.
julia --project="%SCRIPTS%" -e "using Pkg; Pkg.instantiate()" 2>nul

REM ── 4. Open dashboard immediately (Julia compiles in background)
echo  [PSO] Opening dashboard in browser...
start "" "%DASHBOARD%"

REM ── 5. Launch the PSO engine (stays in this window)
echo  [PSO] Starting Julia/CUDA PSO engine on port 7700...
echo  [PSO] CTRL+C to stop the engine.
echo.
julia --project="%SCRIPTS%" --threads=auto "%SCRIPT%"

echo.
echo  [PSO] Engine stopped.
pause
