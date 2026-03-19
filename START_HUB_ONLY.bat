@echo off
title NEXUS HUB (NO EVOLUTION)
color 03
cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra"

:: ── 1. OLLAMA ─────────────────────────────────────
netstat -ano | findstr ":11434" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo [OK] Starting Ollama...
    start "OLLAMA" /min cmd /c "ollama serve"
)

:: ── 2. NEXUS HUB (NODE) ───────────────────────────
netstat -ano | findstr ":3000" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo [OK] Starting Nexus Hub...
    start "HUB_NODE" /min cmd /c "node server.cjs"
)

:: ── 3. OPEN DASHBOARD ──────────────────────────────
echo [OK] Opening Dashboard...
start "" "http://127.0.0.1:3000/nexus_hub.html"

exit

