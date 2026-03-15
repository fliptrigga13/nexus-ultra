@echo off
title NEXUS ULTRA — PHONE ACCESS LAUNCHER
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║     NEXUS ULTRA — PHONE ACCESS LAUNCHER             ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: Kill old instances
echo [1/4] Stopping old processes...
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Start Nexus Hub server
echo [2/4] Starting Nexus Hub on port 3000...
start "NEXUS_HUB" /MIN cmd /c "cd /d ""C:\Users\fyou1\Desktop\New folder\nexus-ultra"" && node server.cjs"
timeout /t 3 /nobreak >nul

:: Start Cloudflare tunnel and capture URL
echo [3/4] Opening Cloudflare tunnel...
set CFLOG=%TEMP%\cf_tunnel.log
start "CF_TUNNEL" /MIN cmd /c "cloudflared tunnel --url http://localhost:3000 > %CFLOG% 2>&1"

:: Wait for URL to appear
echo [4/4] Waiting for public URL...
set /a tries=0
:wait_loop
timeout /t 2 /nobreak >nul
set /a tries+=1
findstr /C:"trycloudflare.com" "%CFLOG%" >nul 2>&1
if %errorlevel%==0 goto got_url
if %tries% lss 20 goto wait_loop
echo ERROR: Cloudflare tunnel failed to start.
goto done

:got_url
:: Extract the URL
for /f "tokens=*" %%i in ('findstr /C:"trycloudflare.com" "%CFLOG%"') do (
    set LINE=%%i
)

:: Write URL to Desktop
powershell -Command ^
  "$log = Get-Content '%CFLOG%' -Raw; " ^
  "$m = [regex]::Match($log, 'https://[^\s|]+\.trycloudflare\.com'); " ^
  "$url = $m.Value; " ^
  "$hubUrl = $url + '/nexus_hub.html'; " ^
  "Write-Host ''; " ^
  "Write-Host '  ╔══════════════════════════════════════════════════════╗'; " ^
  "Write-Host '  ║  NEXUS HUB IS LIVE — OPEN ON YOUR PHONE:           ║'; " ^
  "Write-Host '  ║'; " ^
  "Write-Host ('  ║  HUB : ' + $hubUrl); " ^
  "Write-Host '  ║'; " ^
  "Write-Host ('  ║  ROOT: ' + $url); " ^
  "Write-Host '  ╚══════════════════════════════════════════════════════╝'; " ^
  "$hubUrl | Set-Clipboard; " ^
  "Write-Host '  (URL copied to clipboard!)'; " ^
  "Set-Content -Path 'C:\Users\fyou1\Desktop\NEXUS_PHONE_URL.txt' -Value ('Hub URL: ' + $hubUrl + [Environment]::NewLine + 'Root: ' + $url + [Environment]::NewLine + 'Generated: ' + (Get-Date));"

echo.
echo  Local access always works at:
echo    http://127.0.0.1:3000/nexus_hub.html
echo.
echo  Keep this window open to maintain phone access.
echo  URL saved to Desktop as NEXUS_PHONE_URL.txt
echo.

:done
pause
