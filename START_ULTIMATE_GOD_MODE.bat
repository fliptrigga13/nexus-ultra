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
echo  [1/10] Starting Ollama LLM Engine...
start "OLLAMA ENGINE" /min cmd /c "ollama serve"
timeout /t 4 /nobreak >nul

REM ── 2. COSMOS SERVER (Agent Orchestration API :9100)
echo  [2/10] Starting COSMOS Agent Orchestration (:9100)...
cd /d "C:\Users\fyou1\.gemini\antigravity\scratch\aistudio-agent"
start "COSMOS :9100" /min cmd /c "python cosmos_server.py 2>&1 | tee cosmos.log"
timeout /t 3 /nobreak >nul

REM ── 3. PSO SWARM BRAIN (Julia GPU :7700)
echo  [3/10] Starting PSO Swarm Brain (:7700)...
cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra\local-scripts"
start "PSO SWARM :7700" /min cmd /c "julia pso_swarm.jl 2>&1 | tee pso.log"
timeout /t 3 /nobreak >nul

cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

REM ── 4. TIER-2 MEMORY CORE (init SQLite DB, seed memories)
echo  [4/10] Initialising Tier-2 No-Wipe Memory Core...
python nexus_memory_core.py
timeout /t 2 /nobreak >nul

REM ── 5. NEXUS SWARM LOOP (6 Core Agents + Memory Injection)
echo  [5/10] Starting Autonomous Agent Swarm Loop (6 agents)...
start "SWARM LOOP" /min cmd /c "python nexus_swarm_loop.py 2>&1 | tee swarm_loop.log"
timeout /t 3 /nobreak >nul

REM ── 6. BACKDOOR API (Local Command Injection :7701)
echo  [6/10] Starting Backdoor API (:7701)...
start "BACKDOOR :7701" /min cmd /c "python nexus_backdoor.py 2>&1 | tee backdoor.log"
timeout /t 2 /nobreak >nul

REM ── 7. ANT COLONY ANTENNAE (pheromone comms, hive mind)
echo  [7/10] Starting Ant Colony Antennae Protocol...
start "ANTENNAE COLONY" /min cmd /c "python nexus_antennae.py 2>&1 | tee colony.log"
timeout /t 2 /nobreak >nul

REM ── 8. INFINITE EVOLUTION ENGINE (prompt mutation + crossover)
echo  [8/10] Starting Infinite Evolution Engine...
start "EVOLUTION ENGINE" /min cmd /c "python nexus_evolution.py 2>&1 | tee evolution.log"
timeout /t 2 /nobreak >nul

REM ── 9. ROGUE SQUAD (METACOG / ROGUE / HACKER_ENGINEER / ADVERSARY)
echo  [9/10] Starting Rogue Squad (METACOG / ROGUE / HACKER / ADVERSARY)...
start "ROGUE SQUAD" /min cmd /c "python nexus_rogue_agents.py 2>&1 | tee rogue.log"
timeout /t 2 /nobreak >nul

REM ── 10. MYCORRHIZAL THOUGHT WEB (bidirectional sink-pull hyphal network)
echo  [10/10] Starting Mycorrhizal Thought Web...
start "MYCELIUM WEB" /min cmd /c "python nexus_mycelium.py 2>&1 | tee mycelium.log"
timeout /t 2 /nobreak >nul

REM ── 11. PERMANENT HUB SERVER (reads disk directly, never loses connection)
echo  [11/11] Starting Permanent Hub Server (:7702)...
start "HUB SERVER :7702" /min cmd /c "python nexus_hub_server.py 2>&1 | tee hub.log"
timeout /t 2 /nobreak >nul

echo.
echo  ══════════════════════════════════════════════════════════════
echo   ALL 10 ENGINES LAUNCHING... waiting 10s for full boot
echo  ══════════════════════════════════════════════════════════════
timeout /t 10 /nobreak >nul

echo.
echo  OPENING ULTIMATE GOD MODE HUB (ALL-IN-ONE)...
start "" "C:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_ultimate_hub.html"

echo.
echo  OPENING BACKDOOR DASHBOARD...
start "" "http://127.0.0.1:7701"

echo.
echo  ══════════════════════════════════════════════════════════════
echo   NEXUS PRIME -- ULTIMATE GOD MODE -- FULLY ONLINE
echo.
echo   PORTS:
echo     OLLAMA:           http://127.0.0.1:11434
echo     COSMOS API:       http://127.0.0.1:9100
echo     PSO SWARM (GPU):  http://127.0.0.1:7700
echo     BACKDOOR API:     http://127.0.0.1:7701
echo.
echo   10 ENGINES RUNNING:
echo     [1]  Ollama LLM (9 models)
echo     [2]  COSMOS Orchestration
echo     [3]  Julia PSO GPU Optimizer
echo     [4]  Tier-2 Memory Core (nexus_mind.db -- no wipe)
echo     [5]  Swarm Loop (SUPERVISOR/PLANNER/RESEARCHER/DEVELOPER/VALIDATOR/REWARD)
echo     [6]  Backdoor API
echo     [7]  Ant Colony Antennae (pheromones)
echo     [8]  Evolution Engine (prompt mutation)
echo     [9]  Rogue Squad (METACOG/ROGUE/HACKER/ADVERSARY)
echo     [10] Mycorrhizal Thought Web (bidirectional hyphal flow)
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
pause
