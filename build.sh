#!/usr/bin/env bash
# ── Package Sealock into a macOS app bundle (dist/Sealock.app) ──
# build.bat 의 macOS 짝꿍. Windows 와 달리 --onefile 을 쓰지 않고 .app 번들로
# 묶는다 (Qt 앱은 onefile 로 만들면 실행이 느리고 아이콘/번들 정보가 빠진다).
set -euo pipefail
cd "$(dirname "$0")"

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "[build] Ensuring PyInstaller is installed..."
"$PY" -m pip install --upgrade pyinstaller >/dev/null

echo "[build] Building Sealock.app..."
# --add-data 구분자는 macOS/Linux 가 ':' (Windows 는 ';') 이라 build.bat 과 다르다.
"$PY" -m PyInstaller --noconfirm --clean --windowed \
  --name Sealock \
  --icon icons/icon_mac.icns \
  --osx-bundle-identifier com.sealock.app \
  --add-data "sealock/assets:sealock/assets" \
  app.py

echo
echo "[build] Done -> dist/Sealock.app"
echo "[build] 실행: open dist/Sealock.app"
