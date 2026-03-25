@echo off
title NEXUS PROFIT AUTOPILOT
color 0A

echo ===================================================
echo   NEXUS PROFIT AUTOPILOT - DAILY OPERATIONS RUNNER 
echo ===================================================
echo.
echo [1/2] Initiating Sensory Swarm Feed...
cd /d "C:\Users\fyou1\Desktop\New folder\nexus-ultra"
call FEED-AUTOPILOT.bat

echo.
echo [2/2] Initiating SEO Fix Agent...
python seo_agent.py --fix

echo.
echo ===================================================
echo   [SUCCESS] Daily Profit Operations Complete
echo ===================================================
timeout /t 5 >nul
exit
