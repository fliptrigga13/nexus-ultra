@echo off
setlocal enabledelayedexpansion
title NEXUS PRIME — FULL STACK LAUNCHER
color 0A
cls

echo.
echo  ======================================================
echo   NEXUS PRIME FULL STACK LAUNCHER
echo   Ollama  *  OpenClaw  *  COSMOS  *  Nemotron  *  Free
echo  ======================================================
echo.

:: ── OLLAMA CORS (required for browser fetch) ────────────────────────────────
set OLLAMA_ORIGINS=*
set OLLAMA_HOST=127.0.0.1:11434

:: ── OLLAMA GPU-ONLY (forces models into RTX 4060 VRAM, not system RAM) ──────
:: Prevents deepseek-r1:8b from OOM-killing the node server
set OLLAMA_MAX_LOADED_MODELS=1
set OLLAMA_NUM_PARALLEL=1
set OLLAMA_GPU_OVERHEAD=0

:: ── 1. OLLAMA ─────────────────────────────────────────────────────────────────
echo [1/5] Checking Ollama...
netstat -ano 2>nul | findstr ":11434" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo       Ollama already up on :11434 [OK]
) else (
    echo       Starting Ollama...
    start "OLLAMA" /min cmd /k "set OLLAMA_ORIGINS=* && ollama serve"
    ping -n 4 127.0.0.1 >nul
    echo       Ollama started [OK]
)

:: ── 2. NEMOTRON pull (background, first run only) ────────────────────────────
echo [2/5] Checking Nemotron model...
ollama list 2>nul | findstr "nemotron" >nul
if %errorlevel%==0 (
    echo       nemotron model present [OK]
) else (
    echo       Pulling nemotron:latest in background (~7GB, one-time)...
    start "NEMOTRON_PULL" /min cmd /c "ollama pull nemotron:latest"
    echo       Pulling... chat available after download completes.
)

:: ── 3. OPENCLAW GATEWAY ───────────────────────────────────────────────────────
echo [3/5] Checking OpenClaw...
netstat -ano 2>nul | findstr ":18789" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo       OpenClaw already up on :18789 [OK]
) else (
    if exist "%USERPROFILE%\.openclaw\gateway.cmd" (
        echo       Starting OpenClaw gateway...
        start "OPENCLAW" /min cmd /c "%USERPROFILE%\.openclaw\gateway.cmd"
        ping -n 4 127.0.0.1 >nul
        echo       OpenClaw started [OK]
    ) else (
        echo       gateway.cmd not found - run: npm install -g openclaw
    )
)

:: ── 4. COSMOS ─────────────────────────────────────────────────────────────────
echo [4/5] Checking COSMOS...
netstat -ano 2>nul | findstr ":9100" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo       COSMOS already up on :9100 [OK]
) else (
    set "COSMOS=%USERPROFILE%\.gemini\antigravity\scratch\aistudio-agent\cosmos_server.py"
    if exist "!COSMOS!" (
        echo       Starting COSMOS...
        start "COSMOS" /min cmd /c "python \"!COSMOS!\""
        ping -n 3 127.0.0.1 >nul
        echo       COSMOS started [OK]
    ) else (
        echo       cosmos_server.py not found, skip
    )
)

:: ── 5. NEXUS NODE SERVER (:3000) ──────────────────────────────────────────────
echo [5/5] Checking Nexus Node server...
netstat -ano 2>nul | findstr ":3000" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo       Node already up on :3000 [OK]
) else (
    echo       Starting Node server...
    start "NEXUS_NODE" /min cmd /k "cd /d \"%~dp0\" && node server.cjs"
    ping -n 4 127.0.0.1 >nul
    echo       Node started on :3000 [OK]
)

:: ── STATUS ────────────────────────────────────────────────────────────────────
echo.
echo  ── STACK STATUS ──────────────────────────────────────
ping -n 3 127.0.0.1 >nul

set ports=11434 18789 9100 3000
for %%P in (%ports%) do (
    netstat -ano 2>nul | findstr ":%%P " | findstr "LISTENING" >nul
    if !errorlevel!==0 (
        echo   :%%P   [UP]
    ) else (
        echo   :%%P   [DOWN]
    )
)
echo  ──────────────────────────────────────────────────────
echo.

:: ── OPEN DASHBOARD ────────────────────────────────────────────────────────────
echo  Opening Nexus Prime Command Hub...
start "" "http://127.0.0.1:3000/nexus_prime_command.html"

echo.
echo  NEXUS PRIME LIVE - 100%% local - zero API cost - free
echo.
echo  Models:
echo    nexus-prime:latest  (GOD MODE)
echo    nemotron:latest     (NVIDIA - GPU/CUDA expert)
echo    deepseek-r1:8b      (Reasoning)
echo    qwen2.5-coder:7b    (Code)
echo    llama3.1:8b         (General)
echo.
echo  All AI runs on your machine. Nothing leaves localhost.
echo.
pause
endlocal
