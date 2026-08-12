@echo off
rem ── Package Sealock into a single Windows .exe (dist\Sealock.exe) ──
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

rem 로컬과 CI 의 파이썬이 갈리면 결과물도 갈린다 — 버전은 .python-version 하나로
rem 관리하고, CI(release.yml)도 같은 값을 쓴다. 경고문은 ASCII 로만 쓴다:
rem 콘솔 코드페이지가 한글을 깨뜨릴 수 있다.
"%PY%" -c "import pathlib,sys; want=pathlib.Path('.python-version').read_text().strip(); have=str(sys.version_info[0])+'.'+str(sys.version_info[1]); print('[build] !! This Python is '+have+' but CI builds with '+want+' (see .python-version)') if have!=want else None"

rem requirements.txt 도 함께 — certifi 가 빌드 환경에 없으면 PyInstaller 가 CA
rem 번들을 담지 못하고, 그렇게 나온 앱은 멀쩡한 회선에서도 HTTPS 가 전부 실패한다
rem (updater._ssl_context 참고).
echo [build] Ensuring build dependencies are installed...
"%PY%" -m pip install --upgrade pyinstaller >nul
"%PY%" -m pip install -r requirements.txt >nul

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
