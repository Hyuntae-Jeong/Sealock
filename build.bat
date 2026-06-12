@echo off
rem ── Package Sealock into a single Windows .exe (dist\Sealock.exe) ──
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [build] Ensuring PyInstaller is installed...
"%PY%" -m pip install --upgrade pyinstaller >nul

echo [build] Building Sealock.exe...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name Sealock ^
  --icon icons\icon_win.ico ^
  --add-data "sealock\assets;sealock\assets" ^
  app.py

if errorlevel 1 (
  echo [build] FAILED.
  pause
  exit /b 1
)

echo.
echo [build] Done -^> dist\Sealock.exe
pause
