@echo off
title ⚡ NEXUS DAILY COMMANDER
color 0A
cls

echo.
echo   ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
echo   ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
echo   ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
echo   ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
echo   ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║
echo   ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
echo.
echo   DAILY COMMANDER — NEXUS ULTRA
echo   ================================================
echo.

:: ── STEP 1: LAUNCH ALL HUBS ──────────────────────────────────────────────────
echo   [1/4] Launching all hubs and services...
call "C:\Users\fyou1\Desktop\New folder\nexus-ultra\OPEN_ALL_HUBS.bat"
timeout /t 3 /nobreak >nul

:: ── STEP 2: FEED THE SWARM ────────────────────────────────────────────────────
echo.
echo   [2/4] Feeding the swarm with fresh market intelligence...
call "C:\Users\fyou1\Desktop\New folder\nexus-ultra\FEED-AUTOPILOT.bat"
timeout /t 2 /nobreak >nul

:: ── STEP 3: RUN SEO AGENT ────────────────────────────────────────────────────
echo.
echo   [3/4] Running SEO Agent to optimize sales funnel...
cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
python seo_agent.py --fix
timeout /t 2 /nobreak >nul

:: ── STEP 4: OPEN CONTROL SURFACES ────────────────────────────────────────────
echo.
echo   [4/4] Opening Observatory and Stripe Dashboard...
start "" "http://localhost:3000"
start "" "https://dashboard.stripe.com/payments"
start "" "http://127.0.0.1:7701/pending"

echo.
echo   ================================================
echo   ✅ NEXUS DAILY COMMANDER — ALL SYSTEMS GO
echo   ================================================
echo.
echo   Stripe Dashboard — check for new sales
echo   Pending Approvals — review any agent code requests
echo   Observatory — monitor swarm health live
echo.
echo   YOUR PROMOTION TASK TODAY:
echo   Post 1 video of the Observatory on X/Twitter.
echo   Caption: "100%% offline AI swarm. 0 cloud cost."
echo.
pause
