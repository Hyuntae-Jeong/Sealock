@echo off
rem ── Sealock dev launcher (visible console: shows setup progress & errors) ──
setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
  echo [Sealock] Creating virtual environment...
  py -3 -m venv "%VENV%" 2>nul || python -m venv "%VENV%"
  if not exist "%PY%" (
    echo [Sealock] ERROR: Python 3 not found. Install it from https://www.python.org/ and retry.
    pause
    exit /b 1
  )
)

if not exist "%VENV%\.deps_installed" (
  echo [Sealock] Installing dependencies ^(first run only^)...
  "%PY%" -m pip install --upgrade pip >nul
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [Sealock] ERROR: dependency installation failed.
    pause
    exit /b 1
  )
  echo done> "%VENV%\.deps_installed"
)

echo [Sealock] Starting...
"%PY%" app.py
if errorlevel 1 pause
