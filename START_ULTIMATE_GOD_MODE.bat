@echo off
chcp 65001 >nul
title NEXUS ULTIMATE GOD MODE -- RTX 4060 FULL STACK LAUNCH
color 02

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║  NEXUS PRIME -- ULTIMATE GOD MODE                           ║
echo  ║  RTX 4060 8GB -- 10 Agents -- 100%% Offline                 ║
echo  ║  No API Keys -- No Cloud -- Tier-2 No-Wipe Memory           ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

REM ── 1. OLLAMA (Local LLM Engine)
echo  [1/12] Checking Ollama LLM Engine...
netstat -ano | findstr ":11434" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo       Starting Ollama...
    start "OLLAMA ENGINE" /min cmd /c "ollama serve"
    echo       Waiting for Ollama to load nexus-prime 5.2GB...
    timeout /t 10 /nobreak >nul
) else (
    echo       Ollama already active
)
echo  Pre-warming nexus-prime into VRAM...
REM curl -s -X POST http://127.0.0.1:11434/api/generate -d "{\"model\":\"nexus-prime:latest\",\"prompt\":\"ready\",\"stream\":false}" >nul 2>&1
echo  Ollama engine ready.

REM ── 2. COSMOS SERVER (Agent Orchestration API :9100)
echo  [2/12] Checking COSMOS (:9100)...
netstat -ano | findstr ":9100" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo       Starting COSMOS...
    cd /d "C:\Users\fyou1\.gemini\antigravity\scratch\aistudio-agent"
    start "COSMOS :9100" /min cmd /c "python cosmos_server.py > cosmos.log 2>&1"
    timeout /t 3 /nobreak >nul
) else (
    echo       COSMOS already active
)

REM ── 3. PSO SWARM BRAIN (Julia GPU :7700)
echo  [3/12] Checking PSO Swarm Brain (:7700)...
netstat -ano | findstr ":7700" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo       Starting PSO Swarm...
    cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra\local-scripts"
    start "PSO SWARM :7700" /min cmd /c "julia pso_swarm.jl > pso.log 2>&1"
    timeout /t 3 /nobreak >nul
) else (
    echo       PSO Swarm already active
)

cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

REM ── 4. TIER-2 MEMORY CORE (init SQLite DB, seed memories)
echo  [4/12] Initialising Tier-2 No-Wipe Memory Core...
python nexus_memory_core.py
timeout /t 2 /nobreak >nul

REM ── 5. NEXUS SWARM LOOP (6 Core Agents + Memory Injection)
echo  [5/12] Checking Autonomous Swarm Loop...
powershell -Command "if (!(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nexus_swarm_loop.py*' })) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
    echo       Starting Swarm Loop...
    start "SWARM LOOP" /min cmd /c "python nexus_swarm_loop.py > swarm_loop.log 2>&1"
    timeout /t 3 /nobreak >nul
) else (
    echo       Swarm Loop already active
)

REM ── 6. EH API (Local Command Injection :7701)
echo  [6/12] Checking EH API (:7701)...
netstat -ano | findstr ":7701" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo       Starting EH API...
    start "EH :7701" /min cmd /c "python nexus_eh.py > nexus_eh.log 2>&1"
    timeout /t 2 /nobreak >nul
) else (
    echo       EH API already active
)

REM ── 7. ANT COLONY ANTENNAE (pheromone comms, hive mind)
echo  [7/12] Checking Antennae Protocol...
powershell -Command "if (!(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nexus_antennae.py*' })) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
    echo       Starting Antennae...
    start "ANTENNAE COLONY" /min cmd /c "python nexus_antennae.py > colony.log 2>&1"
    timeout /t 2 /nobreak >nul
) else (
    echo       Antennae Protocol active
)

REM ── 8. INFINITE EVOLUTION ENGINE (prompt mutation + crossover)
echo  [8/12] Checking Evolution Engine...
powershell -Command "if (!(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nexus_evolution.py*' })) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
    echo       Starting Evolution...
    start "EVOLUTION ENGINE" /min cmd /c "python nexus_evolution.py > evolution.log 2>&1"
    timeout /t 2 /nobreak >nul
) else (
    echo       Evolution Engine active
)

REM ── 9. ROGUE SQUAD (METACOG / ROGUE / HACKER_ENGINEER / ADVERSARY)
echo  [9/12] Checking Rogue Squad...
powershell -Command "if (!(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nexus_rogue_agents.py*' })) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
    echo       Starting Rogue Squad...
    start "ROGUE SQUAD" /min cmd /c "python nexus_rogue_agents.py > rogue.log 2>&1"
    timeout /t 2 /nobreak >nul
) else (
    echo       Rogue Squad active
)

REM ── 10. MYCORRHIZAL THOUGHT WEB (bidirectional sink-pull hyphal network)
echo  [10/12] Checking Mycorrhizal Thought Web...
powershell -Command "if (!(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nexus_mycelium.py*' })) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
    echo       Starting Mycelium...
    start "MYCELIUM WEB" /min cmd /c "python nexus_mycelium.py > mycelium.log 2>&1"
    timeout /t 2 /nobreak >nul
) else (
    echo       Thought Web active
)

REM ── 11. PERMANENT HUB SERVER (:7702)
echo  [11/12] Checking Hub Server (:7702)...
netstat -ano | findstr ":7702" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo       Starting Hub Server...
    start "HUB SERVER :7702" /min cmd /c "python nexus_hub_server.py > hub.log 2>&1"
    timeout /t 2 /nobreak >nul
) else (
    echo       Hub Server already active
)

REM ── 12. FEED INGESTOR (HackerNews + ArXiv → swarm task queue, every hour)
echo  [12/14] Checking Feed Ingestor...
powershell -Command "if (!(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nexus_feed_ingestor.py*' })) { exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
    echo       Starting Feed Ingestor...
    start "FEED INGESTOR" /min cmd /c "python nexus_feed_ingestor.py > feed.log 2>&1"
    timeout /t 2 /nobreak >nul
) else (
    echo       Feed Ingestor active
)

REM ── 13. OPENCLAW GATEWAY (:18789)
echo  [13/14] Checking OpenClaw Gateway (:18789)...
netstat -ano | findstr ":18789" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo       Starting OpenClaw...
    start "OPENCLAW :18789" /min cmd /c "%USERPROFILE%\.openclaw\gateway.cmd"
    timeout /t 3 /nobreak >nul
) else (
    echo       OpenClaw active
)

REM ── 14. n8n AUTOMATION (:5678)
echo  [14/14] Checking n8n Automation (:5678)...
netstat -ano | findstr ":5678" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo       Starting n8n...
    start "n8n :5678" /min cmd /c "n8n start"
    timeout /t 5 /nobreak >nul
) else (
    echo       n8n active
)

echo.
echo  ══════════════════════════════════════════════════════════════
echo   ALL 12 ENGINES LAUNCHING... waiting 10s for full boot
echo  ══════════════════════════════════════════════════════════════
timeout /t 10 /nobreak >nul

echo.
echo  STARTING NODE JS SERVER (Port 3000)...
start "NEXUS WEB SERVER" /min cmd /c "node server.cjs > server_error.log 2>&1"
echo       Node API Active.

echo.
echo  STARTING CLOUDFLARE TUNNEL (veil-piercer.com)...
tasklist /fi "imagename eq cloudflared.exe" | find "cloudflared.exe" >nul
if %errorlevel% neq 0 (
    start "VEILPIERCER TUNNEL" /min cmd /c "cloudflared tunnel run veilpiercer"
    echo       Tunnel started.
) else (
    echo       Tunnel already running.
)

echo.
echo  OPENING NEXUS LAUNCHER...
start chrome "C:\Users\fyou1\Desktop\New folder\nexus-ultra\NEXUS-LAUNCHER.html"

echo.
echo  ══════════════════════════════════════════════════════════════
echo   NEXUS PRIME -- ULTIMATE GOD MODE -- FULLY ONLINE
echo.
echo   PORTS:
echo     OLLAMA:           http://127.0.0.1:11434
echo     COSMOS API:       http://127.0.0.1:9100
echo     PSO SWARM (GPU):  http://127.0.0.1:7700
echo     EH API:           http://127.0.0.1:7701
echo.
echo   12 ENGINES RUNNING:
echo     [1]  Ollama LLM (9 models)
echo     [2]  COSMOS Orchestration
echo     [3]  Julia PSO GPU Optimizer
echo     [4]  Tier-2 Memory Core (nexus_mind.db -- no wipe)
echo     [5]  Swarm Loop (SUPERVISOR/PLANNER/RESEARCHER/DEVELOPER/VALIDATOR/REWARD)
echo     [6]  EH API (nexus_eh.py)
echo     [7]  Ant Colony Antennae (pheromones)
echo     [8]  Evolution Engine (prompt mutation)
echo     [9]  Rogue Squad (METACOG/ROGUE/HACKER/ADVERSARY)
echo     [10] Mycorrhizal Thought Web (bidirectional hyphal flow)
echo     [11] Permanent Hub Server (:7702)
echo     [12] Feed Ingestor (HN + ArXiv)
echo.
echo   MODELS (RTX 4060 8GB):
echo     nexus-prime:latest  deepseek-r1:8b  qwen2.5-coder:7b
echo     qwen3:8b  llava:7b  llama3.1:8b  gemma3:4b  llama3.2:1b
echo.
echo   INJECT A TASK:
echo     curl -X POST http://127.0.0.1:7701/inject
echo     -d "{\"task\":\"YOUR COMMAND\"}"
echo  ══════════════════════════════════════════════════════════════
echo.
echo   [STATION] Ignition complete. Launching God Mode Hub...
start chrome "http://127.0.0.1:3000/nexus_ultimate_hub.html"
echo.
echo   [FRONTEND] Launching Live Public Domain Wrapper...
start chrome "https://veil-piercer.com/"
timeout /t 5
exit
