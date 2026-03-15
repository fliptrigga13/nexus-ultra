@echo off
:: Check for Admin rights
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Admin rights confirmed.
) else (
    echo [ERROR] Please right-click this file and "Run as Administrator".
    pause
    exit /b 1
)

powershell -ExecutionPolicy Bypass -File "INSTALL_AUTOSTART.ps1"
pause
