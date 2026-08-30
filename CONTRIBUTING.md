# 기여 가이드

Sealock 를 고칠 때 알아야 할 것들입니다. 앱을 쓰는 방법은 [README.md](README.md) 를 보세요.

## 개발 환경

Python 은 [.python-version](.python-version) 의 버전(3.13)에 맞춥니다. CI 도 같은 값을 쓰고, `build.sh` 는 로컬 파이썬이 다르면 경고합니다. 버전이 갈리면 결과물도 갈립니다 — 3.9 로 빌드하던 시절의 `.app` 은 macOS 의 LibreSSL 을 쓰는데 CI 의 3.13 은 OpenSSL 을 안고 나가서, 인증서 문제가 로컬에서는 재현되지 않고 릴리즈에서만 터진 적이 있습니다.

```bash
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python app.py
```

## 검사

```bash
python -m pytest tests          # 단위 테스트 (파일별 단독 실행도 됩니다)
python scripts/smoke_ui.py      # 오프스크린 UI 스모크 — UI 가 조립되고 그려지는지
python scripts/pii_check.py     # 커밋 전 PII/시크릿 스캐너 (아래 참조)
```

`smoke_ui.py` 는 화면도 DB도 없이 전체 UI 를 조립해 데모 데이터를 렌더합니다. 위젯을 건드렸다면 이걸 돌려보세요 — 눈으로만 확인하기 어려운 것들(설정 패널의 바깥 클릭 닫기, 스냅샷 팝업, 페이징 이후의 누적 렌더)을 실제로 눌러 봅니다.

## 스크린샷

README 의 이미지는 `docs/screenshots/` 에 있고, **데모 모드("샘플 데이터로 둘러보기")** 로 찍습니다. UI 를 바꿨다면 낡은 장면이 없는지 확인하고 다시 찍어 함께 커밋하세요.

찍기 전에 연결 폼이 비어 있는지 확인하세요. `config.local.json` 을 만들어 뒀다면 폼이 실제 접속 정보로 채워진 채 열리고, 그대로 찍으면 공개 저장소에 그 값이 남습니다.

## 보안 / 개인정보

이 저장소는 **공개(public)** 입니다. 다음을 **절대 커밋하지 마세요**: 실제 DB 자격증명·접속 문자열, 회사/내부 호스트명, 실제 테이블/컬럼명이나 데이터 샘플, 고객·직원 개인정보(PII).

- 모든 예시·스크린샷·테스트는 합성(synthetic) 데이터(`example.com` 등)를 씁니다.
- 커밋 전에 `python scripts/pii_check.py` 로 스테이징된 변경분의 자격증명·이메일·외부 IP·`config.local.json` 등을 검사하세요.

## CHANGELOG 쓰는 법

[CHANGELOG.md](CHANGELOG.md) 가 **릴리즈 노트의 원천**입니다. 태그를 푸시하면 CI 가 해당 버전 섹션을 그대로 GitHub 릴리즈 본문으로 옮기고, 앱의 **설정 → 릴리즈 노트 보기** 와 업데이트 안내 창도 같은 글을 보여줍니다.

- 작업하면서 `## [미출시]` 아래에 한 줄씩 쌓고, 태그를 따기 직전에 제목만 `## [0.0.4] — 2026-08-06` 으로 바꿉니다. 태그 `v0.0.4` ↔ 섹션 `[0.0.4]` 로 맞춰지며, 섹션이 없으면 릴리즈가 실패합니다.
- 커밋 메시지를 옮겨 붓지 말고 **사용자에게 무엇이 달라졌는지** 씁니다.
  `fix: 스냅샷 팝업 모서리 계단 현상 제거` → `스냅샷 팝업 모서리가 매끄럽게 보입니다.`
- 그룹은 `새로운 기능` / `개선` / `수정` 셋. 해당 없으면 뺍니다.
- 리팩터링·빌드 스크립트·문서 수정은 적지 않습니다. 사용자가 볼 수 있는 변화만.
- 버전당 5~8줄. 앱 안에서는 460px 폭의 좁은 창에 렌더링되므로 **표·이미지·HTML 은 쓰지 않습니다**(원격 이미지는 불러오지 못해 깨져 보입니다). 목록·굵게·인라인 코드·링크까지만.

## 릴리즈

`v` 로 시작하는 태그를 푸시하면 [release.yml](.github/workflows/release.yml) 이 Windows·macOS 앱을 빌드해 릴리즈에 첨부합니다.

```bash
git tag v1.0.0
git push origin v1.0.0
```

- **첨부물** — `Sealock-Windows.zip`(단일 `.exe`) · `Sealock-macOS.zip`(`.app` 번들, Apple Silicon)
- **버전** — 저장소에 커밋된 [sealock/version.py](sealock/version.py) 의 값은 `+dev` 자리표시자이고, CI 가 태그에서 뽑은 값으로 덮어씁니다. `+dev` 상태에서는 앱 내 업데이트가 비활성화됩니다.
- **아이콘** — Windows `icons/icon_win.ico`, macOS `icons/icon_mac.icns`
- macOS 빌드는 Apple Silicon(arm64) 용입니다. Intel Mac 용이 필요하면 `runs-on: macos-13` 잡을 추가하세요.
- 태그 없이 Actions 탭에서 **수동 실행(workflow_dispatch)** 하면 릴리즈는 건너뛰고 빌드 결과물만 확인합니다.

업데이트 흐름을 시험할 때는 `version.py` 를 고치지 말고 환경변수로 한 번만 덮어씁니다 (자세한 사용법은 그 파일의 docstring 에 있습니다).

```bash
export SEALOCK_VERSION=0.0.2
dist/Sealock.app/Contents/MacOS/Sealock     # → "새 버전이 있습니다"
unset SEALOCK_VERSION
```

## 프로젝트 구조

```
app.py                 진입점 — QApplication, 테마 적용, 스플래시 → 메인 윈도우
sealock/
  db.py                PyMySQL 연결/쿼리 (자격증명은 메모리에만 존재)
  introspect.py        스키마 분석 + Envers 컬럼 분류, REVINFO 탐지
  history.py           감사 행 → 이전→이후 변경 타임라인 빌더
  services.py          UI-비의존 서비스 함수 + AppState (DB/데모 분기)
  demo.py              합성 데모 데이터 (DB 없이 둘러보기)
  updater.py           GitHub 릴리즈 확인 + 자기 교체 (Qt 비의존)
  settings.py          QSettings 에 저장하는 UI 설정 (테마)
  version.py           버전 단일 출처 — 릴리즈 빌드는 CI 가 태그로 덮어씀
  resources.py         번들 에셋 탐색 (개발 실행 / PyInstaller 양쪽)
  assets/              런타임 이미지 에셋
  ui/
    theme.py           라이트·다크 팔레트 + 전역 QSS
    widgets.py         재사용 위젯 (스텝퍼, 타임라인 노드, 값 pill, 비동기 워커)
    window.py          메인 윈도우 + 3단계 페이지
    macos.py           macOS 창 꾸밈 — 제목표시줄을 지우고 신호등만 남긴다
    splash.py          시작 스플래시
    update.py          설정 패널 + 업데이트/릴리즈 노트 창
scripts/
  pii_check.py         커밋 전 PII/시크릿 스캐너
  smoke_ui.py          오프스크린 UI 스모크 테스트
tests/                 단위 테스트 (데모 데이터, 타임라인, 기간, 업데이터)
docs/screenshots/      README 이미지 (데모 모드로 촬영)
icons/                 앱 아이콘 원본 + 생성 스크립트
run.vbs / run.bat      Windows 원클릭 실행
build.bat / build.sh   패키징 (Windows .exe / macOS .app)
```
