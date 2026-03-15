@echo off
title NEXUS ULTRA — System Hardening (Run as Admin)
echo.
echo  Run this as ADMINISTRATOR to apply all hardening settings.
echo.
powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File ""%~dp0NEXUS_HARDENING.ps1""' -Verb RunAs"
