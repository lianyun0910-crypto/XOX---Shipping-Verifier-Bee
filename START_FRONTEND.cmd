@echo off
setlocal
cd /d %~dp0frontend
if not exist node_modules (
  echo [Shipping Verifier] Installing frontend dependencies...
  call npm.cmd install
  if errorlevel 1 exit /b 1
)
echo [Shipping Verifier] Starting frontend on http://localhost:5173
call npm.cmd run dev
endlocal
