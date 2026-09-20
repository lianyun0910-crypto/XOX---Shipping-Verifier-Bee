@echo off
setlocal
cd /d %~dp0

if not exist backend\venv\Scripts\python.exe (
  echo [Shipping Verifier] Creating Python virtual environment...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv backend\venv
  ) else (
    python -m venv backend\venv
  )
  if errorlevel 1 (
    echo Failed to create backend\venv. Make sure Python 3 is installed and available in PATH.
    pause
    exit /b 1
  )
)

if not exist backend\venv\.deps-installed (
  echo [Shipping Verifier] Installing backend dependencies...
  backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
  if errorlevel 1 (
    echo Failed to install backend dependencies.
    pause
    exit /b 1
  )
  type nul > backend\venv\.deps-installed
)

echo [Shipping Verifier] Starting backend on http://127.0.0.1:8000
backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
endlocal
