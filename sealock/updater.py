"""Manual update — check GitHub Releases and replace this install with the
newest one. Pure logic, no Qt: the UI drives every step.

Sealock never checks on its own. Nothing here runs unless the user opens
설정 and presses 업데이트 확인 — no startup probe, no background timer.

The replacement itself cannot be done in-process: the running app owns the
files it would overwrite. So the last step writes a small helper script, starts
it detached and quits. The helper waits for this process to disappear, renames
the current install to ``.old``, unpacks the download in its place, sanity
checks the result and relaunches — restoring the backup if anything fails.

What "the install" means depends on how the app was packaged:

  * macOS   — ``Sealock.app`` bundle          (CI: --windowed)
  * Windows — ``Sealock.exe`` single file     (CI: --onefile)

Running from source (``python app.py``) has no install to replace, so the
whole feature stays disabled there — see can_self_update().
"""
from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    import certifi
except ImportError:                 # source checkout with an older venv
    certifi = None

from .version import __version__

GITHUB_OWNER = "Hyuntae-Jeong"
GITHUB_REPO = "Sealock"
# The list, not /releases/latest: a user who skipped versions needs the notes of
# every release they missed, and one list response carries them all.
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"Sealock/{__version__}"

# CI publishes exactly these two, unversioned (see .github/workflows/release.yml).
ASSETS = {"darwin": "Sealock-macOS.zip", "win32": "Sealock-Windows.zip"}

# A release body serves two audiences. Above this marker are the changes, written
# for people already running Sealock — that is what the app shows. Below it are
# the download table and Gatekeeper note, for first-time visitors of the release
# page, and the app drops them. CI writes the marker (release.yml, "Build release
# body from CHANGELOG"), so the string must stay identical on both sides.
NOTES_MARKER = "<!-- github-only -->"

# 마커 도입 전(v0.0.3 이하) 릴리즈에는 자를 지점이 없다. 그 시절 본문은 다운로드
# 표가 전부였고 — 변경 사항은 CHANGELOG 에만 있었다 — 마커를 못 찾으면 본문이
# 통째로 "변경 사항" 으로 올라와, 노트를 열어 보면 플랫폼 표와 Gatekeeper 안내가
# 나온다. 그 시절 본문도 이 제목으로 시작하므로 여기서 끊는다. 남는 게 없으면
# _collect_notes 가 빈 섹션을 걸러 그 버전은 목록에서 조용히 빠진다 — 보여줄
# 변경 사항이 애초에 없던 버전이니 그게 맞다.
LEGACY_TAIL = re.compile(r"^##\s*다운로드\s*$", re.M)


@dataclass(frozen=True)
class Release:
    tag: str            # "v0.0.4"
    version: str        # "0.0.4"
    notes: str          # changes only — see NOTES_MARKER and _collect_notes()
    published: str      # "2026-07-29"
    asset_url: str      # direct download for this platform
    asset_name: str
    asset_size: int     # bytes, from the API — used to verify the download


@dataclass(frozen=True)
class FetchError:
    """Why the check failed, kept structured so the UI can say something useful.

    A flat "네트워크를 확인하세요" is wrong for a rate limit (the network is
    fine) and for a missing asset (the release exists but has no build).
    """
    kind: str           # network | rate_limit | http | no_release | no_asset | parse
    detail: str = ""
    retry_after: int | None = None      # rate_limit only: seconds until reset


# ── certificate trust ───────────────────────────────────────────────────
def _ssl_context() -> ssl.SSLContext | None:
    """Trust store for every request to GitHub.

    A packaged build carries its own OpenSSL, and that copy looks for CA
    certificates where it was told at compile time — for the macOS build, a path
    inside the *build machine's* Python framework that exists on no user's disk.
    PyInstaller copies the library but nothing to put there, so verification
    fails, urllib raises URLError exactly as a dead network would, and the app
    blames a connection that was never the problem. certifi puts the CA bundle
    inside the app, so point OpenSSL at that instead of at the empty default.

    None means "use the interpreter's own store": running from source, where the
    system Python resolves certificates on its own, and where certifi may not be
    installed yet.
    """
    if certifi is None:
        return None
    return ssl.create_default_context(cafile=certifi.where())


# ── version comparison ──────────────────────────────────────────────────
def is_dev_build(version: str = __version__) -> bool:
    """A PEP 440 local part ("+dev") marks a build that CI did not stamp."""
    return "+" in version


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("+", 1)[0].split("."))


def is_newer(current: str, latest: str) -> bool:
    """Whether ``latest`` is a higher version than ``current``.

    Only compares the release numbers — "0.0.3+dev" counts as 0.0.3. Whether an
    update may actually be *applied* is a separate question (can_self_update).
    """
    try:
        return _parts(latest) > _parts(current)
    except ValueError:
        return False


# ── how this copy was installed ─────────────────────────────────────────
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def can_self_update() -> bool:
    """Only a CI-stamped, packaged build may replace itself."""
    return is_frozen() and not is_dev_build() and sys.platform in ASSETS


def blocked_reason() -> str | None:
    """User-facing reason the update action is unavailable, or None if it is."""
    if not is_frozen():
        return "소스에서 실행 중입니다 — git pull 로 최신 코드를 받으세요."
    if is_dev_build():
        return f"개발 빌드({__version__})입니다 — 릴리즈 빌드에서만 업데이트할 수 있습니다."
    if sys.platform not in ASSETS:
        return f"이 플랫폼({sys.platform})용 릴리즈가 없습니다."
    return None


def install_target() -> Path:
    """The path the helper will replace.

    macOS is the ``.app`` bundle, so walk up from the executable
    (``Sealock.app/Contents/MacOS/Sealock``) until the bundle directory shows
    up. Windows ships one file, so the executable *is* the target.

    Meaningless unless can_self_update() — from source this resolves to the
    Python interpreter.
    """
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent
    return exe


# ── release lookup ──────────────────────────────────────────────────────
def _asset_name() -> str:
    return ASSETS[sys.platform]


def _version_key(tag: str) -> tuple[int, ...]:
    """Sort key for a tag. Anything unparseable sorts last, never crashes."""
    try:
        return _parts(tag.lstrip("v"))
    except ValueError:
        return ()


def _changes_of(payload: dict) -> str:
    """The user-facing part of one release body (see NOTES_MARKER, LEGACY_TAIL)."""
    body = payload.get("body") or ""
    if NOTES_MARKER in body:
        return body.split(NOTES_MARKER, 1)[0].strip()
    return LEGACY_TAIL.split(body, maxsplit=1)[0].strip()


def _collect_notes(ranked: list[dict], current: str) -> str:
    """Notes for the newest release plus every skipped one, newest first.

    The app only ever installs the newest build, so someone on 0.0.2 jumping to
    0.0.4 would otherwise never learn what 0.0.3 changed. The newest release is
    always included even when it is not newer than ``current`` — 릴리즈 노트 보기
    has to show something to a user who is already up to date.

    Version headings appear only when there is more than one section; for a
    single release the sheet header already names the version.
    """
    sections = [(str(ranked[0].get("tag_name") or ""), _changes_of(ranked[0]))]
    for release in ranked[1:]:
        tag = str(release.get("tag_name") or "")
        if not is_newer(current, tag.lstrip("v")):
            break                       # ranked descending — the rest are older
        sections.append((tag, _changes_of(release)))

    sections = [(tag, body) for tag, body in sections if body]
    if len(sections) == 1:
        return sections[0][1]
    return "\n\n".join(f"## {tag}\n\n{body}" for tag, body in sections)


def fetch_latest(timeout: float = 5.0) -> tuple[Release | None, FetchError | None]:
    """Read the newest published release, with the notes of any skipped ones.

    The list endpoint includes drafts and pre-releases, so unlike
    ``/releases/latest`` this has to filter them out itself.
    """
    req = urllib.request.Request(
        RELEASES_API,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    # Transport and parsing are kept apart on purpose. Reading the body inside
    # this block would fold a 200 that is not JSON — a captive portal login
    # page, a proxy's error page — into the same "network" verdict as a dead
    # connection, and send whoever reads it looking at the wrong layer.
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        # A spent rate limit also arrives as 403, but the network is fine and
        # the fix is "wait", not "check your connection" — tell them apart.
        if exc.code == 403 and exc.headers.get("X-RateLimit-Remaining") == "0":
            try:
                wait = int(exc.headers.get("X-RateLimit-Reset", 0)) - int(time.time())
            except (TypeError, ValueError):
                wait = None
            return None, FetchError("rate_limit", str(exc), max(0, wait) if wait else None)
        return None, FetchError("http", f"HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return None, FetchError("network", str(exc.reason))
    except OSError as exc:                # socket timeout, connection cut mid-read
        return None, FetchError("network", str(exc))

    try:
        # UnicodeDecodeError is a ValueError too — a body that is not even utf-8
        # is the same "this is not the API talking" case as bad JSON.
        payload = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        return None, FetchError("parse", str(exc))

    try:
        published = [r for r in payload
                     if not r.get("draft") and not r.get("prerelease") and r.get("tag_name")]
        ranked = sorted(published, key=lambda r: _version_key(str(r["tag_name"])), reverse=True)
        if not ranked:
            # Understood perfectly — there is simply nothing published yet, which
            # is not the same as a response we could not read.
            return None, FetchError("no_release")

        newest = ranked[0]
        tag = str(newest["tag_name"])
        wanted = _asset_name()
        asset = next((a for a in newest.get("assets", []) if a.get("name") == wanted), None)
        if asset is None:
            return None, FetchError("no_asset", f"{tag} 릴리즈에 {wanted} 가 없습니다.")
        return Release(
            tag=tag,
            version=tag.lstrip("v"),
            notes=_collect_notes(ranked, __version__),
            published=(newest.get("published_at") or "")[:10],
            asset_url=asset["browser_download_url"],
            asset_name=asset["name"],
            asset_size=int(asset.get("size") or 0),
        ), None
    # AttributeError included because this endpoint returns a list: an error
    # object would come back as a dict, and iterating it yields plain strings.
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return None, FetchError("parse", str(exc))


FETCH_MESSAGES = {
    "network": "네트워크에 연결할 수 없어 최신 버전을 확인하지 못했습니다.",
    "rate_limit": "GitHub 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
    "http": "GitHub 응답이 올바르지 않아 최신 버전을 확인하지 못했습니다.",
    "no_release": "아직 발행된 릴리즈가 없습니다.",
    "no_asset": "최신 릴리즈에 이 플랫폼용 파일이 없습니다.",
    "parse": "GitHub 응답을 해석하지 못했습니다.",
}


# Kinds whose sentence cannot say what actually went wrong: "network" reads the
# same for a dead wifi, a five second timeout and a certificate that would not
# verify — and only the last one means the build itself is broken. The other
# kinds already name their cause, so repeating the raw detail only adds noise.
DETAILED = ("network", "http", "parse")


def describe(err: FetchError) -> str:
    base = FETCH_MESSAGES.get(err.kind, err.detail or "최신 버전을 확인하지 못했습니다.")
    if err.kind == "rate_limit" and err.retry_after:
        return f"{base} (약 {max(1, err.retry_after // 60)}분 후)"
    if err.kind in DETAILED and err.detail:
        detail = err.detail if len(err.detail) <= 140 else err.detail[:139] + "…"
        return f"{base}\n({detail})"
    return base


# ── download ────────────────────────────────────────────────────────────
def _work_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "sealock-update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_path(release: Release) -> Path:
    return _work_dir() / release.asset_name


# Returned by download() when the caller's cancel callback asked it to stop —
# distinct from a failure message so the UI can close quietly instead of
# reporting an error the user caused on purpose.
CANCELLED = "__cancelled__"


def download(release: Release, dest: Path,
             on_progress: Callable[[int, int], None] | None = None,
             cancel: Callable[[], bool] | None = None,
             chunk: int = 128 * 1024) -> str | None:
    """Stream the asset to ``dest``. Returns None on success, else a message.

    Cancelling or failing removes the partial file — a half-written zip must
    never be left where a later run could mistake it for a finished download.
    """
    req = urllib.request.Request(release.asset_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as resp:
            total = int(resp.headers.get("Content-Length") or release.asset_size or 0)
            done = 0
            with open(dest, "wb") as fh:
                while True:
                    if cancel is not None and cancel():
                        raise InterruptedError
                    block = resp.read(chunk)
                    if not block:
                        break
                    fh.write(block)
                    done += len(block)
                    if on_progress is not None:
                        on_progress(done, total)
    except InterruptedError:
        dest.unlink(missing_ok=True)
        return CANCELLED
    except (urllib.error.URLError, OSError, ValueError) as exc:
        dest.unlink(missing_ok=True)
        return f"내려받지 못했습니다: {exc}"

    # The API tells us the exact size; a mismatch means a truncated transfer.
    if release.asset_size and dest.stat().st_size != release.asset_size:
        actual = dest.stat().st_size
        dest.unlink(missing_ok=True)
        return f"내려받은 파일 크기가 맞지 않습니다 ({actual:,} / {release.asset_size:,} bytes)."
    return None


# ── swap helpers ────────────────────────────────────────────────────────
# Both scripts take: 1=main pid, 2=install path, 3=new zip, 4=error log.
# They report failures as ASCII tokens only — the log is read back by Python
# and translated below, so a console codepage can never mangle the message.

_MACOS_SH = r"""#!/bin/bash
MAIN_PID="$1"; TARGET="$2"; NEW_ZIP="$3"; ERR_LOG="$4"
OLD="${TARGET}.old"

TRIES=0
while kill -0 "$MAIN_PID" 2>/dev/null; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 30 ]; then
        echo "ERR_WAIT_TIMEOUT pid=$MAIN_PID" > "$ERR_LOG"; exit 1
    fi
    sleep 1
done
sleep 1

[ -e "$OLD" ] && rm -rf "$OLD"
if ! mv "$TARGET" "$OLD"; then
    echo "ERR_BACKUP target=$TARGET" > "$ERR_LOG"; exit 1
fi

# ditto, never unzip: CI packs the bundle with `ditto -c -k --keepParent`, which
# carries symlinks / exec bits / xattrs that unzip would flatten into a broken app.
PARENT="$(dirname "$TARGET")"
if ! ditto -xk "$NEW_ZIP" "$PARENT"; then
    echo "ERR_EXTRACT zip=$NEW_ZIP" > "$ERR_LOG"
    rm -rf "$TARGET"; mv "$OLD" "$TARGET"; exit 1
fi

if [ ! -x "$TARGET/Contents/MacOS/Sealock" ]; then
    echo "ERR_MISSING_APP" > "$ERR_LOG"
    rm -rf "$TARGET"; mv "$OLD" "$TARGET"; exit 1
fi

# Sealock is not code signed, so a quarantined copy would be refused on launch.
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null

open "$TARGET"
rm -rf "$OLD"; rm -f "$NEW_ZIP"; rm -f "$0"
exit 0
"""

# Windows ships one file, so the swap is file-level: back up Sealock.exe and
# unpack the zip (which holds Sealock.exe at its root) beside it.
_WINDOWS_CMD = r"""@echo off
setlocal EnableDelayedExpansion

REM Absolute system paths on purpose: a user PATH carrying Git Bash / MSYS2
REM versions of find/tar would change these commands' behaviour entirely.
set "WIN_TASKLIST=%SystemRoot%\System32\tasklist.exe"
set "WIN_FIND=%SystemRoot%\System32\find.exe"
set "WIN_PING=%SystemRoot%\System32\ping.exe"
set "WIN_TAR=%SystemRoot%\System32\tar.exe"

set "MAIN_PID=%~1"
set "TARGET=%~2"
set "NEW_ZIP=%~3"
set "ERR_LOG=%~4"
set "OLD=%TARGET%.old"

REM Step out of the install folder: holding it as cwd makes Windows refuse the
REM rename below with a sharing violation.
cd /d "%TEMP%"
for %%I in ("%TARGET%") do set "TARGET_DIR=%%~dpI"

set /a TRIES=0
:wait
"%WIN_TASKLIST%" /FI "PID eq %MAIN_PID%" 2>NUL | "%WIN_FIND%" "%MAIN_PID%" >NUL
if errorlevel 1 goto exited
set /a TRIES+=1
if !TRIES! GEQ 30 (
    >"%ERR_LOG%" echo ERR_WAIT_TIMEOUT pid=%MAIN_PID%
    exit /b 1
)
REM ping as sleep: timeout.exe quits immediately when stdin is redirected.
"%WIN_PING%" -n 2 127.0.0.1 >NUL
goto wait

:exited
"%WIN_PING%" -n 2 127.0.0.1 >NUL

if exist "%OLD%" del /q "%OLD%"
move "%TARGET%" "%OLD%" >NUL
if errorlevel 1 (
    >"%ERR_LOG%" echo ERR_BACKUP target=%TARGET%
    exit /b 1
)

"%WIN_TAR%" -xf "%NEW_ZIP%" -C "%TARGET_DIR%"
if errorlevel 1 (
    >"%ERR_LOG%" echo ERR_EXTRACT zip=%NEW_ZIP%
    goto rollback
)

if not exist "%TARGET%" (
    >"%ERR_LOG%" echo ERR_MISSING_APP
    goto rollback
)

start "" "%TARGET%"
del /q "%OLD%"
del /q "%NEW_ZIP%"
(goto) 2>nul & del "%~f0"
exit /b 0

:rollback
if exist "%TARGET%" del /q "%TARGET%"
move "%OLD%" "%TARGET%" >NUL
exit /b 1
"""

SWAP_MESSAGES = {
    "ERR_WAIT_TIMEOUT": "앱이 30초 안에 종료되지 않아 업데이트를 중단했습니다.",
    "ERR_BACKUP": "기존 파일의 이름을 바꾸지 못했습니다. 설치 위치에 쓰기 권한이 있는지 확인하세요.",
    "ERR_EXTRACT": "내려받은 파일의 압축을 풀지 못했습니다.",
    "ERR_MISSING_APP": "새 설치본에서 실행 파일을 찾지 못했습니다. 이전 버전으로 되돌렸습니다.",
}


def explain_swap_error(log: str) -> str:
    if not log:
        return ""
    return SWAP_MESSAGES.get(log.split(None, 1)[0], log)


def _error_log() -> Path:
    return _work_dir() / "last-error.log"


def _pending_marker() -> Path:
    return _work_dir() / "pending-version"


def launch_swap(zip_path: Path, target: Path | None = None) -> None:
    """Write the helper, start it detached, and return. The caller must quit
    immediately — the helper is already waiting for this process to exit."""
    target = target or install_target()
    log = _error_log()
    log.unlink(missing_ok=True)

    if sys.platform == "darwin":
        script = _work_dir() / "sealock-update.sh"
        script.write_text(_MACOS_SH, encoding="utf-8")
        script.chmod(0o755)
        argv = ["/bin/bash", str(script)]
        flags = {"start_new_session": True}
    elif sys.platform == "win32":
        script = _work_dir() / "sealock-update.cmd"
        script.write_text(_WINDOWS_CMD, encoding="utf-8")
        argv = ["cmd.exe", "/c", str(script)]
        # NO_WINDOW keeps the console hidden; NEW_PROCESS_GROUP lets the helper
        # outlive the app that started it.
        flags = {"creationflags": 0x08000000 | 0x00000200}
    else:
        raise RuntimeError(f"지원되지 않는 플랫폼: {sys.platform}")

    subprocess.Popen(
        argv + [str(os.getpid()), str(target), str(zip_path), str(log)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, **flags,
    )


# ── result of the previous attempt (read once, at startup) ──────────────
def mark_pending(version: str) -> None:
    """Record the version being installed so the next run can confirm it.

    Best effort: failing to write this must not stop the update itself.
    """
    try:
        _pending_marker().write_text(version, encoding="utf-8")
    except OSError:
        pass


def take_pending() -> str | None:
    """Version the last attempt aimed at, cleared as it is read.

    Callers compare it with the running version — after a rollback the app
    comes back as the old one, and then there is nothing to celebrate.
    """
    return _take(_pending_marker())


def take_error() -> str | None:
    """Raw helper failure token from the last attempt, cleared as it is read."""
    return _take(_error_log())


def _take(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    try:
        path.unlink()
    except OSError:
        pass
    return text or None
