@echo off
title NEXUS HUBS LAUNCHER
echo [==============================================]
echo   LAUNCHING ALL NEXUS HUBS AND CORE OBSERVATORY
echo [==============================================]
echo.

echo Launching VEILPIERCER Observatory (Main Site)...
start "" "index.html"

echo Launching NEXUS CONTROL CENTER...
start "" "NEXUS_CONTROL_CENTER.hta"

echo Launching ULTIMATE HUB...
start "" "nexus_ultimate_hub.html"

echo Launching PRIME COMMAND...
start "" "nexus_prime_command.html"

echo Launching GOD MODE HUB...
start "" "god-mode-hub.html"

echo.
echo [System] All Nexus interface layers have been deployed to separate browser windows.
timeout /t 3 > nul
