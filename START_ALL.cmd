@echo off
setlocal
cd /d %~dp0
start "Shipping Verifier Backend" cmd /k "%~dp0START_BACKEND.cmd"
timeout /t 2 /nobreak >nul
start "Shipping Verifier Frontend" cmd /k "%~dp0START_FRONTEND.cmd"
endlocal
