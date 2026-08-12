#!/usr/bin/env bash
# ── Package Sealock into a macOS app bundle (dist/Sealock.app) ──
# build.bat 의 macOS 짝꿍. Windows 와 달리 --onefile 을 쓰지 않고 .app 번들로
# 묶는다 (Qt 앱은 onefile 로 만들면 실행이 느리고 아이콘/번들 정보가 빠진다).
set -euo pipefail
cd "$(dirname "$0")"

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

# 로컬과 CI 의 파이썬이 갈리면 결과물도 갈린다. 3.9 로 빌드하던 시절의 .app 은
# macOS 자체 LibreSSL 을 쓰는데 CI 의 3.13 은 OpenSSL 을 통째로 안고 나가서,
# 인증서 문제가 로컬에서는 재현되지 않고 릴리즈에서만 터졌다. 버전은
# .python-version 하나로 관리한다 (CI 는 release.yml 에서 같은 값을 쓴다).
"$PY" -c "$(cat <<'CHECK'
import pathlib, sys
want = pathlib.Path(".python-version").read_text().strip()
have = "%d.%d" % sys.version_info[:2]
if have != want:
    print(f"[build] !! 이 파이썬은 {have} 인데 CI 는 {want} 로 빌드합니다.")
    print(f"[build]    맞추려면: rm -rf .venv && python{want} -m venv .venv")
CHECK
)"

# requirements.txt too, not just PyInstaller: certifi has to be importable at
# *build* time or PyInstaller has no CA bundle to pack, and the app that comes
# out fails every HTTPS call on a machine that is perfectly online — the bug
# updater._ssl_context() exists to prevent.
echo "[build] Ensuring build dependencies are installed..."
"$PY" -m pip install --upgrade pyinstaller >/dev/null
"$PY" -m pip install -r requirements.txt >/dev/null

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
