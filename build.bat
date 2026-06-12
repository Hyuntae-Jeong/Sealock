@echo off
rem ── Package AudViewer into a single Windows .exe (dist\AudViewer.exe) ──
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [build] Ensuring PyInstaller is installed...
"%PY%" -m pip install --upgrade pyinstaller >nul

echo [build] Building AudViewer.exe...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name AudViewer ^
  --icon icons\icon_win.ico ^
  --add-data "audviewer\assets;audviewer\assets" ^
  app.py

if errorlevel 1 (
  echo [build] FAILED.
  pause
  exit /b 1
)

echo.
echo [build] Done -^> dist\AudViewer.exe
pause
